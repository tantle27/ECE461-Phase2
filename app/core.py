from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
import threading
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import Any, BinaryIO, cast

import yaml
from flask import Blueprint, Response, jsonify, request, send_file, redirect
from werkzeug.utils import secure_filename
import requests

from app.db_adapter import ArtifactStore, RatingsCache, TokenStore
from app.s3_adapter import S3Storage
from app.scoring import ModelRating, _score_artifact_with_metrics, rate_artifacts_concurrently

logger = logging.getLogger(__name__)
try:
    from app.audit_logging import audit_event, security_alert
except Exception:
    # fall back to no-op functions if audit logging not available
    def audit_event(message: str, **fields: Any) -> None:  # type: ignore
        logger.debug("audit_event noop: %s %s", message, fields)

    def security_alert(message: str, **fields: Any) -> None:  # type: ignore
        logger.warning("security_alert noop: %s %s", message, fields)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ArtifactMetadata:
    id: str
    name: str
    type: str
    version: str


@dataclass
class Artifact:
    metadata: ArtifactMetadata
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactQuery:
    artifact_type: str | None = None
    name: str | None = None
    types: list[str] = field(default_factory=list)
    page: int = 1
    page_size: int = 25


# ---------------------------------------------------------------------------
# Storage (DynamoDB-backed with in-memory fallback)
# ---------------------------------------------------------------------------

_ARTIFACT_STORE = ArtifactStore()
_STORE: dict[str, Artifact] = {}
_ARTIFACT_ORDER: list[str] = []
_RATINGS_CACHE: dict[str, ModelRating] = {}
_AUDIT_LOG: dict[str, list[dict[str, Any]]] = {}
_S3 = S3Storage()
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_LOCAL_PERSIST_PATH = Path(os.environ.get("REGISTRY_PERSIST_FILE", "/tmp/registry_state.json"))
_LOCAL_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)

# Cache TTL in seconds for previously computed ratings. Set to 0 to always recompute.
_RATING_CACHE_TTL_SECONDS = max(0, int(os.environ.get("RATING_CACHE_TTL_SECONDS", "1800")))

# S3-based persistence for dev reloads (tokens + artifacts)
_PERSIST_S3_KEY = os.environ.get("REGISTRY_PERSIST_S3_KEY", "registry/registry_store.json")

# token -> is_admin
_TOKENS: dict[str, bool] = {}
_DEFAULT_USER = {
    "username": "ece30861defaultadminuser",
    "password": """correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;""",
    "role": "admin",
}
_AUTH_SECRET = os.environ.get("AUTH_SECRET", _DEFAULT_USER["password"])
# print("core.py: Using AUTH_SECRET of length", len(_AUTH_SECRET))
# print(_AUTH_SECRET)
_REGEX_MAX_PATTERN_LENGTH = 500
_REGEX_MAX_TIME_SECONDS = 2.0
_REGEX_MAX_ARTIFACTS = 1000
_REGEX_MAX_MATCHES = 100
_REGEX_README_TRUNCATE = 10000
_DANGEROUS_REGEX_SNIPPETS: list[re.Pattern[str]] = [
    re.compile(r"\((?:[^()\\]|\\.)+\)[*+]\s*[*+]+"),  # e.g., (.+)+, (.*)+, (\w+)+
    re.compile(r"\(\?:\.\+\)\+"),  # (?:.+)+ (explicit non-capturing)
    re.compile(r"\(\?:\.\*\)\+"),  # (?:.*)+
    re.compile(r"^\((?:[^()\\]|\\.)+\)\+$"),  # ^(a+)+$-like
    re.compile(r"\([^)]+\+\)\{3,\}"),  # Three or more (something+)
    re.compile(r"\([^)]+\+\)\+.*\([^)]+\+\)\+"),  # Multiple nested quantifier groups
    re.compile(r"\([^|)]+\|[^)]+\)[*+]+"),  # (a|aa)*, (a|ab)+, etc.
    re.compile(r"\([^|)]+\|[^)]+\)\*$"),  # (a|aa)*$ anchored
    re.compile(r"\(\?:[^|)]+\|[^)]+\)[*+]+"),  # Non-capturing alternation loops
    re.compile(r"\(\?:[^|)]+\|[^)]+\)\*$"),  # Non-capturing alternation anchored
    # Nested counted quantifiers: (a{1,99999}){1,99999}
    re.compile(r"\([^\)]+\{\d+(?:,\d+)?\}[^\)]*\)\s*\{\d+(?:,\d+)?\}"),
]
_LARGE_QUANTIFIER_THRESHOLD = 1000
_LARGE_QUANTIFIER_RE = re.compile(r"\{(\d+)(?:,(\d+))?\}")

_REGEX_MAX_README_CHARS = 4000
_REGEX_SEGMENT_SIZE = 1500
_SAFE_REGEX_TIMEOUT_MS = 200

# ---------------------------------------------------------------------------
# Observability helpers
# ---------------------------------------------------------------------------

_REQUEST_TIMES: list[float] = []
_STATS = {"ok": 0, "err": 0}
ps_start_time = time.time()


def _persist_state() -> None:
    """Persist tokens and in-memory artifacts to S3 for dev reloads."""
    try:
        data = {
            "tokens": [{"t": t, "admin": admin} for t, admin in _TOKENS.items()],
            "store": [artifact_to_dict(a) for a in _STORE.values()],
            "order": list(_ARTIFACT_ORDER),
        }
        json_data = json.dumps(data)

        if _S3.enabled:
            # Use S3 for persistence
            import io

            _S3.put_file(io.BytesIO(json_data.encode("utf-8")), _PERSIST_S3_KEY, "application/json")
            logger.info(
                "Persisted state to S3 s3://%s/%s (artifacts=%d, tokens=%d)",
                _S3.bucket,
                _S3._key(_PERSIST_S3_KEY),
                len(_STORE),
                len(_TOKENS),
            )
        else:
            _LOCAL_PERSIST_PATH.write_text(json_data)
            logger.info(
                "Persisted state locally to %s (artifacts=%d, tokens=%d)",
                _LOCAL_PERSIST_PATH,
                len(_STORE),
                len(_TOKENS),
            )
    except Exception:
        logger.exception("Failed to persist registry state to S3")


def _load_state() -> None:
    """Load tokens and artifacts from S3 if present (best-effort)."""
    try:
        if _S3.enabled:
            try:
                body, meta = _S3.get_object(_PERSIST_S3_KEY)
            except Exception as exc:  # gracefully handle missing objects
                message = str(exc)
                if "NoSuchKey" in message or "Not Found" in message:
                    logger.info(
                        "S3 persist key %s missing in bucket %s; continuing with empty state",
                        _PERSIST_S3_KEY,
                        _S3.bucket,
                    )
                    return
                raise
            content = body.decode("utf-8").strip()
            source_desc = f"s3://{_S3.bucket}/{_S3._key(_PERSIST_S3_KEY)}"
        else:
            if not _LOCAL_PERSIST_PATH.exists():
                logger.info("Local persist file %s missing; starting with empty state", _LOCAL_PERSIST_PATH)
                return
            content = _LOCAL_PERSIST_PATH.read_text().strip()
            source_desc = str(_LOCAL_PERSIST_PATH)

        if not content:
            logger.info("Persist file %s is empty, skipping load", source_desc)
            return

        data = json.loads(content) or {}
        # Load tokens
        _TOKENS.clear()
        for ent in data.get("tokens", []) or []:
            t = ent.get("t")
            admin = bool(ent.get("admin", False))
            if isinstance(t, str) and t:
                _TOKENS[t] = admin
        # Load artifacts
        _STORE.clear()
        order_hint = data.get("order")
        if isinstance(order_hint, list):
            _ARTIFACT_ORDER.extend([key for key in order_hint if isinstance(key, str)])
        for it in data.get("store", []) or []:
            md = it.get("metadata") or {}
            art = Artifact(
                metadata=ArtifactMetadata(
                    id=str(md.get("id", "")),
                    name=str(md.get("name", "")),
                    type=str(md.get("type", "")),
                    version=str(md.get("version", "1.0.0")),
                ),
                data=it.get("data", {}),
            )
            if art.metadata.id and art.metadata.type:
                store_key = _store_key(art.metadata.type, art.metadata.id)
                _STORE[store_key] = art
                if store_key not in _ARTIFACT_ORDER:
                    _ARTIFACT_ORDER.append(store_key)
                # Keep adapter's memory store in sync for list/get fallbacks
                try:
                    _ARTIFACT_STORE._memory_store[f"{art.metadata.type}:{art.metadata.id}"] = artifact_to_dict(art)
                except Exception:
                    pass
        if not _ARTIFACT_ORDER:
            _ARTIFACT_ORDER.extend(list(_STORE.keys()))
        logger.warning(
            "Loaded persisted state from %s (artifacts=%d, tokens=%d)", source_desc, len(_STORE), len(_TOKENS)
        )
    except Exception:
        logger.exception("Failed to load persisted registry state (this is normal on first run)")


def _record_timing(f):
    @wraps(f)
    def _w(*args, **kwargs):
        t0 = time.time()
        try:
            resp = f(*args, **kwargs)
            _STATS["ok"] += 1
            return resp
        except Exception:
            _STATS["err"] += 1
            raise
        finally:
            _REQUEST_TIMES.append(time.time() - t0)
            if len(_REQUEST_TIMES) > 5000:
                del _REQUEST_TIMES[: len(_REQUEST_TIMES) - 5000]

    return _w


def _percentile(seq: list[float], p: float) -> float:
    if not seq:
        return 0.0
    s = sorted(seq)
    idx = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
    return s[idx]


# Field normalization helpers -------------------------------------------------

_METADATA_SECTION_KEYS = (
    "metadata",
    "Metadata",
    "artifact_metadata",
    "artifactMetadata",
    "package_metadata",
    "packageMetadata",
)
_DATA_SECTION_KEYS = (
    "data",
    "Data",
    "artifact_data",
    "artifactData",
    "package_data",
    "packageData",
)
_METADATA_FIELD_NAMES = {
    "name",
    "Name",
    "artifact_name",
    "artifactName",
    "version",
    "Version",
    "id",
    "ID",
    "artifact_id",
    "artifactId",
    "type",
    "Type",
    "artifact_type",
    "artifactType",
}
_TYPE_URL_ALIASES = {
    # Ensure broad alias coverage so persisted/retrieved artifacts always expose data.url
    "model": [
        "model_link",
        "modelLink",
        "model_url",
        "modelUrl",
        # Common generic download aliases that may appear for models
        "download_url",
        "downloadUrl",
        "DownloadURL",
        "link",
    ],
    "dataset": [
        "dataset_link",
        "datasetLink",
        "dataset_url",
        "datasetUrl",
        # Generic aliases
        "download_url",
        "downloadUrl",
        "DownloadURL",
        "link",
    ],
    "code": [
        "code_link",
        "codeLink",
        "repo_url",
        "repoUrl",
        # Generic aliases
        "download_url",
        "downloadUrl",
        "DownloadURL",
        "link",
    ],
}


def _payload_sections(payload: Mapping[str, Any] | None) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Split a payload into metadata/data dicts while always including the root."""
    metadata_sections: list[Mapping[str, Any]] = []
    data_sections: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        metadata_sections.append(payload)
        data_sections.append(payload)
        for key in _METADATA_SECTION_KEYS:
            section = payload.get(key)
            if isinstance(section, Mapping):
                metadata_sections.append(section)
        for key in _DATA_SECTION_KEYS:
            section = payload.get(key)
            if isinstance(section, Mapping):
                data_sections.append(section)
    return metadata_sections, data_sections


def _coalesce_str(sections: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> str | None:
    """Return the first truthy string/int value for the provided keys."""
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        for key in keys:
            if key in section:
                value = section[key]
                if isinstance(value, (str, int, float)):
                    text = str(value).strip()
                    if text:
                        return text
    return None


def _derive_name_from_url(url: str | None) -> str:
    """Generate a stable artifact name from a URL when no explicit name is provided."""
    if not url:
        return "artifact"
    candidate = url.rstrip("/").split("/")[-1] if "/" in url else url
    safe = secure_filename(candidate) or candidate or "artifact"
    return safe


def _ensure_metadata_aliases(meta: ArtifactMetadata) -> dict[str, Any]:
    """Return metadata dict with spec-style casing aliases."""
    return {
        "id": meta.id,
        "ID": meta.id,
        "name": meta.name,
        "Name": meta.name,
        "type": meta.type,
        "Type": meta.type,
        "version": meta.version,
        "Version": meta.version,
    }


def _ensure_data_aliases(
    artifact_type: str, data: Mapping[str, Any] | None, preferred_url: str | None = None,
) -> dict[str, Any]:
    """Provide consistent url/download/model_link aliases for stored artifact data."""
    normalized: dict[str, Any] = {}
    if isinstance(data, Mapping):
        normalized.update(data)
    url_keys = ["url", "URL", "link", "download_url", "downloadUrl", "DownloadURL"]
    url_keys.extend(_TYPE_URL_ALIASES.get(artifact_type, []))
    url = preferred_url or _coalesce_str([normalized], url_keys)
    if not url:
        s3_key = normalized.get("s3_key")
        s3_bucket = normalized.get("s3_bucket")
        if isinstance(s3_key, str) and s3_key and isinstance(s3_bucket, str) and s3_bucket:
            url = f"s3://{s3_bucket}/{s3_key}"
        else:
            path = normalized.get("path")
            if isinstance(path, str) and path:
                url = f"file://{path}"
    if url:
        normalized["url"] = url
        normalized["URL"] = url
        normalized.setdefault("link", url)
        normalized.setdefault("download_url", url)
        normalized.setdefault("downloadUrl", url)
        normalized.setdefault("DownloadURL", url)
        for alias in _TYPE_URL_ALIASES.get(artifact_type, []):
            normalized.setdefault(alias, url)
            camel = alias[0].upper() + alias[1:]
            normalized.setdefault(camel, url)
    return normalized


def _normalize_artifact_request(
    artifact_type: str, payload: Mapping[str, Any] | None, enforced_id: str | None = None,
) -> tuple[ArtifactMetadata, dict[str, Any]]:
    """Normalize arbitrary artifact payloads into canonical metadata/data."""
    metadata_sections, data_sections = _payload_sections(payload)

    name = _coalesce_str(metadata_sections, ["name", "Name", "artifact_name", "artifactName"])
    version = _coalesce_str(metadata_sections, ["version", "Version"]) or "1.0.0"
    artifact_id = enforced_id or _coalesce_str(metadata_sections, ["id", "ID", "artifact_id", "artifactId"])

    url_keys = ["url", "URL", "link", "download_url", "downloadUrl", "DownloadURL"]
    url_keys.extend(_TYPE_URL_ALIASES.get(artifact_type, []))
    url = _coalesce_str(data_sections, url_keys)
    if not url:
        url = _coalesce_str(metadata_sections, url_keys)

    merged_data: dict[str, Any] = {}
    for section in data_sections:
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if key in _METADATA_FIELD_NAMES:
                continue
            merged_data[key] = value

    if not artifact_id:
        artifact_id = str(int(time.time() * 1000))
    if not name:
        name = _derive_name_from_url(url)

    normalized_data = _ensure_data_aliases(artifact_type, merged_data, url)

    metadata = ArtifactMetadata(id=artifact_id, name=name, type=artifact_type, version=version,)
    return metadata, normalized_data


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    metadata_block = _ensure_metadata_aliases(artifact.metadata)
    data_block = _ensure_data_aliases(artifact.metadata.type, artifact.data)
    # Per spec, always provide an internal download_url for retrieving stored bundles
    try:
        internal_dl = f"/artifacts/{artifact.metadata.type}/{artifact.metadata.id}/download"
        data_block["download_url"] = internal_dl
        data_block["downloadUrl"] = internal_dl
        data_block["DownloadURL"] = internal_dl
    except Exception:
        pass
    artifact.data = data_block  # keep in-memory copy normalized for future lookups
    return {
        "id": artifact.metadata.id,
        "name": artifact.metadata.name,
        "type": artifact.metadata.type,
        "metadata": metadata_block,
        "data": data_block,
    }


def _store_key(artifact_type: str, artifact_id: str) -> str:
    return f"{artifact_type}:{artifact_id}"


def save_artifact(artifact: Artifact) -> Artifact:
    logger.info("Saving artifact %s/%s", artifact.metadata.type, artifact.metadata.id)
    artifact.data = _ensure_data_aliases(artifact.metadata.type, artifact.data)
    artifact_dict = artifact_to_dict(artifact)
    try:
        _ARTIFACT_STORE.save(
            artifact.metadata.type, artifact.metadata.id, artifact_dict,
        )
    except Exception:
        logger.exception("Failed to persist artifact via adapter; keeping in memory only")
    # Always keep adapter's memory store in sync for non-DynamoDB environments
    try:
        _ARTIFACT_STORE._memory_store[f"{artifact.metadata.type}:{artifact.metadata.id}"] = artifact_dict
    except Exception:
        logger.exception("Failed to sync adapter memory store")
    store_key = _store_key(artifact.metadata.type, artifact.metadata.id)
    _STORE[store_key] = artifact
    if store_key not in _ARTIFACT_ORDER:
        _ARTIFACT_ORDER.append(store_key)
    # Persist new state for dev reload resiliency
    try:
        _persist_state()
    except Exception:
        pass
    return artifact


def _artifact_from_raw(raw: Mapping[str, Any], default_type: str, default_id: str) -> Artifact:
    """Convert stored dict representation into an Artifact with normalized data."""
    metadata_dict = raw.get("metadata", {}) if isinstance(raw, Mapping) else {}
    data_dict = raw.get("data", {}) if isinstance(raw, Mapping) else {}
    metadata = ArtifactMetadata(
        id=str(metadata_dict.get("id", metadata_dict.get("ID", default_id))),
        name=str(metadata_dict.get("name", metadata_dict.get("Name", ""))),
        type=str(metadata_dict.get("type", metadata_dict.get("Type", default_type))),
        version=str(metadata_dict.get("version", metadata_dict.get("Version", "1.0.0"))),
    )
    artifact = Artifact(metadata=metadata, data=data_dict if isinstance(data_dict, dict) else {})
    artifact.data = _ensure_data_aliases(metadata.type, artifact.data)
    return artifact


def fetch_artifact(artifact_type: str, artifact_id: str) -> Artifact | None:
    logger.info("Fetching artifact %s/%s", artifact_type, artifact_id)
    try:
        data = _ARTIFACT_STORE.get(artifact_type, artifact_id)
        if data:
            art = _artifact_from_raw(data, artifact_type, artifact_id)
            logger.warning(
                "FETCH: Found in primary store type=%s id=%s has_url=%s",
                artifact_type,
                artifact_id,
                isinstance(art.data, dict) and bool(art.data.get("url")),
            )
            return art
    except Exception:
        logger.exception("Primary store fetch failed; falling back to memory")
    art = _STORE.get(_store_key(artifact_type, artifact_id))
    if art:
        art.data = _ensure_data_aliases(art.metadata.type, art.data)
        logger.warning(
            "FETCH: Found in memory store type=%s id=%s has_url=%s",
            artifact_type,
            artifact_id,
            isinstance(art.data, dict) and bool(art.data.get("url")),
        )
    else:
        logger.warning("FETCH: Not found in primary nor memory type=%s id=%s", artifact_type, artifact_id)
    return art


def _duplicate_url_exists(artifact_type: str, url: str) -> bool:
    for a in _STORE.values():
        if a.metadata.type == artifact_type and str((a.data or {}).get("url")) == url:
            return True
    try:
        items = _ARTIFACT_STORE.list_all(artifact_type)
        for d in items or []:
            if (d.get("metadata", {}) or {}).get("type") == artifact_type and (d.get("data", {}) or {}).get(
                "url"
            ) == url:
                return True
    except Exception:
        pass
    return False


def list_artifacts(query: ArtifactQuery) -> dict[str, Any]:
    logger.info("Listing artifacts page=%s size=%s", query.page, query.page_size)
    logger.warning(
        "LIST: artifact_type=%s name=%s types=%s page=%s page_size=%s",
        query.artifact_type,
        query.name,
        query.types,
        query.page,
        query.page_size,
    )
    items: list[Artifact] = []

    def _from_order(artifact_type: str | None) -> list[Artifact]:
        ordered: list[Artifact] = []
        for key in _ARTIFACT_ORDER:
            art = _STORE.get(key)
            if not art:
                continue
            if artifact_type and art.metadata.type != artifact_type:
                continue
            ordered.append(art)
        if not ordered:
            for art in _STORE.values():
                if artifact_type and art.metadata.type != artifact_type:
                    continue
                ordered.append(art)
        return ordered

    items = _from_order(query.artifact_type)
    if not items:
        try:
            primary_items = _ARTIFACT_STORE.list_all(query.artifact_type)
        except Exception:
            primary_items = []
            logger.exception("Primary store list failed; falling back to memory only")
        for data in primary_items or []:
            md = data.get("metadata", {})
            art = Artifact(
                metadata=ArtifactMetadata(
                    id=str(md.get("id", "")),
                    name=str(md.get("name", "")),
                    type=str(md.get("type", "")),
                    version=str(md.get("version", "1.0.0")),
                ),
                data=data.get("data", {}),
            )
            items.append(art)
            store_key = _store_key(art.metadata.type, art.metadata.id)
            _STORE.setdefault(store_key, art)
            if store_key not in _ARTIFACT_ORDER:
                _ARTIFACT_ORDER.append(store_key)

    # Filter by types[]
    if query.types:
        items = [item for item in items if item.metadata.type in query.types]
        logger.warning("LIST: After types filter count=%d", len(items))

    # Filter by name
    if query.name and query.name != "*":
        needle = query.name.lower()
        items = [item for item in items if item.metadata.name.lower() == needle]
        logger.warning("LIST: After exact-name filter '%s' count=%d", needle, len(items))
    elif query.name == "*":
        logger.warning("LIST: Wildcard '*' requested; forcing single-page response")
        query.page = 1
        desired_size = len(items) or query.page_size or 25
        query.page_size = max(query.page_size, desired_size)

    return _paginate_artifacts(items, query.page, query.page_size)


def reset_storage() -> None:
    logger.warning("Resetting in-memory artifact store")
    try:
        _ARTIFACT_STORE.clear()
    except Exception:
        logger.exception("Primary artifact store clear failed; continuing with in-memory reset")
    _STORE.clear()
    _ARTIFACT_ORDER.clear()
    _RATINGS_CACHE.clear()
    _AUDIT_LOG.clear()
    try:
        _persist_state()
    except Exception:
        logger.exception("Failed to persist state after reset")


def _parse_bearer(header_value: str) -> str:
    if not header_value:
        return ""
    v = header_value.strip()
    if v.lower().startswith("bearer "):
        return v.split(" ", 1)[1].strip()
    return v


def _mint_token(username: str, is_admin: bool) -> str:
    payload = json.dumps({"u": username, "adm": is_admin, "ts": int(time.time())})
    sig = hmac.new(_AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{sig}"


def _decode_token(token: str) -> tuple[str, bool] | None:
    if not token or "." not in token:
        return None
    payload_part, sig = token.rsplit(".", 1)
    padding = "=" * (-len(payload_part) % 4)
    try:
        payload_json = base64.urlsafe_b64decode((payload_part + padding).encode("ascii")).decode("utf-8")
        data = json.loads(payload_json)
    except Exception:
        return None
    expected = hmac.new(_AUTH_SECRET.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    username = str(data.get("u", ""))
    is_admin = bool(data.get("adm"))
    return username, is_admin


def _require_auth(admin: bool = False) -> tuple[str, bool]:
    # Per spec, use X-Authorization; Authorization required in your system
    token_hdr = request.headers.get("X-Authorization", "")
    auth_hdr = request.headers.get("Authorization", "")
    token = _parse_bearer(token_hdr) or _parse_bearer(auth_hdr)
    token_store = TokenStore()

    # Record an audit event for the auth check start (mask token)
    audit_event(
        "auth_check_started",
        x_authorization=(token_hdr[:16] + "...") if token_hdr else "",
        authorization=(auth_hdr[:16] + "...") if auth_hdr else "",
        parsed_token=(token[:8] + "...") if token else "",
        admin_required=admin,
    )

    token_known = bool(token and token in _TOKENS)
    if token and not token_known:
        try:
            if token_store.contains(token):
                # All issued tokens represent admin user; store for future reuse
                _TOKENS[token] = True
                token_known = True
        except Exception:
            logger.exception("AUTH: TokenStore check failed")
        if not token_known:
            parsed = _decode_token(token)
            if parsed:
                _TOKENS[token] = bool(parsed[1])
                token_known = True

    if not token or not token_known:
        # spec: 403 for invalid or missing AuthenticationToken
        security_alert(
            "auth_failed",
            reason="missing_or_invalid_token",
            token_present=bool(token),
            token=(token[:8] + "...") if token else "",
        )
        response = jsonify({"message": "Authentication failed due to invalid or missing AuthenticationToken."})
        response.status_code = HTTPStatus.FORBIDDEN
        from flask import abort

        abort(response)

    is_admin = bool(_TOKENS[token])
    audit_event("auth_validated", token=(token[:8] + "..."), is_admin=is_admin)

    if admin and not is_admin:
        # spec: 401 when you do not have permission to reset
        security_alert(
            "auth_failed", reason="admin_required", token=(token[:8] + "...") if token else "",
        )
        response = jsonify({"message": "You do not have permission to reset the registry."})
        response.status_code = HTTPStatus.UNAUTHORIZED
        from flask import abort

        abort(response)

    audit_event("auth_success", token=(token[:8] + "..."), is_admin=is_admin)
    return token, is_admin


def _json_body() -> dict[str, Any]:
    if request.method in ("GET",):
        return {}
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return {}
    return cast(dict[str, Any], payload)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_query(payload: dict[str, Any]) -> ArtifactQuery:
    page = _safe_int(payload.get("page", 1), 1)
    page_size = _safe_int(payload.get("page_size", 25), 25)
    types_raw = payload.get("types", [])
    types_list = types_raw if isinstance(types_raw, list) else []
    return ArtifactQuery(
        artifact_type=payload.get("artifact_type"),
        name=payload.get("name"),
        types=types_list,
        page=page if page > 0 else 1,
        page_size=page_size if 1 <= page_size <= 100 else 25,
    )


def raise_error(status: HTTPStatus, message: str) -> None:
    response = jsonify({"message": message})
    response.status_code = status
    from flask import abort

    abort(response)


def _is_dangerous_regex(raw_pattern: str) -> bool:
    text = (raw_pattern or "").strip()
    if not text:
        return False
    for bomb in _DANGEROUS_REGEX_SNIPPETS:
        if bomb.search(text):
            return True
    for match in _LARGE_QUANTIFIER_RE.finditer(text):
        try:
            lower = int(match.group(1))
            upper_str = match.group(2)
            upper = int(upper_str) if upper_str else None
        except ValueError:
            continue
        numbers = [lower]
        if upper is not None:
            numbers.append(upper)
        if any(num >= _LARGE_QUANTIFIER_THRESHOLD for num in numbers):
            return True
    return False


def _safe_eval_with_timeout(fn: Callable[[], Any], timeout_ms: int) -> tuple[bool, Any | None]:
    """Execute callable within timeout returning (completed, result)."""
    result: dict[str, Any] = {}
    done = threading.Event()

    def _runner() -> None:
        try:
            result["value"] = fn()
        finally:
            done.set()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout_ms / 1000.0)
    if not done.is_set():
        return False, None
    return True, result.get("value")


def _safe_name_match(
    pattern: re.Pattern[str], candidate: str, *, exact_match: bool, raw_pattern: str, context: str,
) -> bool:
    """Match helper with timeout + descriptive errors."""
    if not candidate:
        return False
    matcher = pattern.fullmatch if exact_match else pattern.search
    ok, matched = _safe_eval_with_timeout(lambda: matcher(candidate) is not None, timeout_ms=500)
    if not ok:
        logger.warning(
            "REGEX_TIMEOUT: pattern='%s' candidate='%s' context=%s", raw_pattern, candidate[:120], context,
        )
        raise_error(HTTPStatus.BAD_REQUEST, "Regex pattern too complex and may cause excessive backtracking.")
    return bool(matched)


def _safe_text_search(pattern: re.Pattern[str], text: str, *, raw_pattern: str, context: str,) -> bool:
    if not text:
        return False
    segments = _regex_segments(text)
    if not segments:
        return False
    for idx, segment in enumerate(segments):
        ok, matched = _safe_eval_with_timeout(
            lambda: pattern.search(segment) is not None, timeout_ms=_SAFE_REGEX_TIMEOUT_MS
        )
        if not ok:
            logger.warning(
                "REGEX_TIMEOUT: pattern='%s' context=%s segment_idx=%d segment_preview='%s'",
                raw_pattern,
                context,
                idx,
                segment[:120],
            )
            raise_error(HTTPStatus.BAD_REQUEST, "Regex pattern too complex and may cause excessive backtracking.")
        if matched:
            return True
    return False


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


def _extract_readme_snippet(data: Mapping[str, Any] | None) -> str:
    if not isinstance(data, Mapping):
        return ""
    for key in ("readme", "readme_text", "README", "README_text"):
        candidate = _coerce_text(data.get(key))
        if candidate:
            return candidate

    hf_entries: list[Any] = []
    hf_data = data.get("hf_data")
    if isinstance(hf_data, list):
        hf_entries = hf_data
    elif isinstance(hf_data, str):
        try:
            parsed = json.loads(hf_data)
            if isinstance(parsed, list):
                hf_entries = parsed
            elif isinstance(parsed, Mapping):
                hf_entries = [parsed]
        except Exception:
            hf_entries = []

    for entry in hf_entries:
        if not isinstance(entry, Mapping):
            continue
        candidate = _coerce_text(entry.get("readme_text") or entry.get("readme"))
        if candidate:
            return candidate
        card_data = entry.get("card_data") or entry.get("cardData")
        if isinstance(card_data, Mapping):
            candidate = _coerce_text(card_data.get("readme_text") or card_data.get("readme"))
            if candidate:
                return candidate
    return ""


_REGEX_META_CHAR_RE = re.compile(r"(?<!\\)[.^*+?{}\[\]|()]")

# URL extraction patterns for link inference
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^\s)]+)\)")
_CODE_URL_HINTS = ("github.com", "gitlab.com", "bitbucket.org", "huggingface.co/spaces")
_DATA_URL_HINTS = ("huggingface.co/datasets", "kaggle.com", "openml.org", "datasets/")


def _regex_segments(text: str) -> list[str]:
    if not text:
        return []
    trimmed = text[:_REGEX_MAX_README_CHARS]
    segments: list[str] = []
    for start in range(0, len(trimmed), _REGEX_SEGMENT_SIZE):
        segment = trimmed[start : start + _REGEX_SEGMENT_SIZE]
        if segment:
            segments.append(segment)
    return segments


def _is_plain_name_pattern(raw_pattern: str) -> bool:
    """Return True for regex patterns that are simple ^literal$ without operators."""
    if not raw_pattern.startswith("^") or not raw_pattern.endswith("$"):
        return False
    body = raw_pattern[1:-1]
    if not body:
        return False
    return _REGEX_META_CHAR_RE.search(body) is None


def _paginate_artifacts(items: list[Artifact], page: int, page_size: int) -> dict[str, Any]:
    page = page if page > 0 else 1
    page_size = page_size if 1 <= page_size <= 100 else 25
    total = len(items)
    start = max((page - 1) * page_size, 0)
    end = start + page_size
    page_items = items[start:end]
    return {
        "items": [artifact_to_dict(artifact) for artifact in page_items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


# ---------------------------------------------------------------------------
# URL extraction and link inference helpers
# ---------------------------------------------------------------------------


def _extract_urls(text: str) -> list[str]:
    """Extract URLs from text including markdown links."""
    if not text:
        return []
    urls: list[str] = []
    # Extract markdown links first
    for match in _MARKDOWN_LINK_RE.findall(text):
        urls.append(match)
    # Extract plain URLs
    for match in _URL_RE.findall(text):
        urls.append(match)
    # Deduplicate and normalize
    cleaned: list[str] = []
    for url in urls:
        normalized = _normalize_url(url)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _normalize_url(url: str | None) -> str | None:
    """Normalize URLs by adding scheme and cleaning punctuation."""
    if not url:
        return None
    trimmed = url.strip().strip("()[]{}<>")
    if not trimmed:
        return None
    # Add scheme for common hosts
    if trimmed.startswith("www."):
        trimmed = f"https://{trimmed}"
    if trimmed.startswith("huggingface.co/"):
        trimmed = f"https://{trimmed}"
    if trimmed.startswith("github.com/"):
        trimmed = f"https://{trimmed}"
    # Strip trailing punctuation
    while trimmed and trimmed[-1] in ",.;:)":
        trimmed = trimmed[:-1]
    return trimmed


def _classify_url(url: str, context: str) -> str | None:
    """Classify a URL as 'code' or 'dataset' based on URL and context."""
    low = url.lower()
    ctx = context.lower()
    
    # Check for dataset URLs
    if any(hint in low for hint in _DATA_URL_HINTS):
        return "dataset"
    # Check for code URLs
    if any(hint in low for hint in _CODE_URL_HINTS):
        return "code"
    # Context-based fallback
    if "dataset" in ctx or "data" in ctx:
        return "dataset"
    if "code" in ctx or "repository" in ctx:
        return "code"
    return None


def _infer_related_links(artifact: Artifact) -> None:
    """Extract and infer code_link and dataset_link from README-like fields."""
    if not isinstance(artifact.data, dict):
        return
    
    code_link = _coerce_text(artifact.data.get("code_link"))
    dataset_link = _coerce_text(artifact.data.get("dataset_link"))
    if code_link and dataset_link:
        return  # Already have both
    
    # Collect text sources
    texts: list[str] = []
    for key in ("readme", "README", "description", "summary", "card_data"):
        content = _coerce_text(artifact.data.get(key))
        if content:
            texts.append(content)
    
    # Check HuggingFace data
    hf_blob = artifact.data.get("hf_data")
    if isinstance(hf_blob, str):
        texts.append(hf_blob)
    elif isinstance(hf_blob, Mapping):
        try:
            texts.append(json.dumps(hf_blob))
        except Exception:
            pass
    
    # Also check model_link itself - and infer code/dataset directly for HF URLs
    model_url = _coerce_text(artifact.data.get("model_link") or artifact.data.get("url"))
    if model_url:
        texts.append(model_url)
        lower = model_url.lower()
        if "huggingface.co" in lower:
            if "/datasets/" in lower and not dataset_link:
                dataset_link = model_url
            elif "/spaces/" not in lower and not code_link:
                # Treat regular HF model pages as code sources for metrics
                code_link = model_url
    
    # Extract and classify URLs
    candidates: list[tuple[str, str]] = []
    for text in texts:
        for url in _extract_urls(text):
            candidates.append((url, text))
    
    for url, ctx in candidates:
        classification = _classify_url(url, ctx)
        if not code_link and classification == "code":
            code_link = url
        if not dataset_link and classification == "dataset":
            dataset_link = url
        if code_link and dataset_link:
            break
    
    # Update artifact if we found links
    updated: list[str] = []
    if code_link and not artifact.data.get("code_link"):
        artifact.data["code_link"] = code_link
        updated.append("code_link")
    if dataset_link and not artifact.data.get("dataset_link"):
        artifact.data["dataset_link"] = dataset_link
        updated.append("dataset_link")
    
    if updated:
        logger.info("Inferred links for %s: %s", artifact.metadata.id, updated)
        # Optionally defer persistence during high-concurrency rating to reduce contention
        defer = str(os.environ.get("DEFER_PERSIST_DURING_RATING", "true")).lower() in ("true", "1", "yes")
        if not defer:
            try:
                save_artifact(artifact)
            except Exception:
                logger.exception("Failed to save inferred links")


def _ensure_phase_two_metrics(artifact: Artifact, rating: ModelRating) -> ModelRating:
    """Add reproducibility, reviewedness, and tree_score if missing."""
    scores = rating.scores
    latencies = rating.latencies
    
    # Clamp any known scalar scores into [0.0, 1.0]
    for key in (
        "bus_factor",
        "code_quality",
        "dataset_quality",
        "dataset_and_code_score",
        "license",
        "performance_claims",
        "ramp_up_time",
        "reproducibility",
        "reviewedness",
        "tree_score",
        "net_score",
    ):
        if key in scores and isinstance(scores[key], (int, float)):
            try:
                val = float(scores[key])
                if val < 0.0:
                    val = 0.0
                elif val > 1.0:
                    val = 1.0
                scores[key] = val
            except Exception:
                pass

    # Reproducibility
    if "reproducibility" not in scores:
        dataset_and_code = scores.get("dataset_and_code_score", 0.0)
        if dataset_and_code >= 0.8:
            scores["reproducibility"] = 1.0
        elif dataset_and_code >= 0.4:
            scores["reproducibility"] = 0.5
        else:
            scores["reproducibility"] = 0.0
        latencies.setdefault("reproducibility", 0)
    
    # Reviewedness
    data = artifact.data if isinstance(artifact.data, dict) else {}
    code_link = _coerce_text(data.get("code_link") or data.get("url") or "")
    if "reviewedness" not in scores:
        if code_link and "github.com" in code_link.lower():
            scores["reviewedness"] = 0.5
        else:
            scores["reviewedness"] = 0.0
        latencies.setdefault("reviewedness", 0)
    else:
        # Normalize any negative reviewedness to a reasonable baseline
        try:
            rv = float(scores.get("reviewedness", 0.0))
            if rv < 0.0:
                scores["reviewedness"] = 0.5 if (code_link and "github.com" in code_link.lower()) else 0.0
        except Exception:
            pass
    
    # Tree score (simplified - no parent lookup for speed)
    if "tree_score" not in scores:
        scores["tree_score"] = 0.0
        latencies.setdefault("tree_score", 0)
    
    return rating


# ---------------------------------------------------------------------------
# Flask blueprint and routes
# ---------------------------------------------------------------------------

blueprint = Blueprint("registry", __name__)

# Load any previously persisted dev state (tokens + artifacts) on startup
try:
    _load_state()
except Exception:
    pass

# -------------------- Health --------------------


@blueprint.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    # Autograder expects a JSON body with ok:true

    return jsonify({"ok": True}), 200


@blueprint.route("/health/components", methods=["GET"])
def health_components_route() -> tuple[Response, int] | Response:
    wm = request.args.get("windowMinutes", default="60")
    try:
        window_minutes = max(5, min(1440, int(wm)))
    except Exception:
        window_minutes = 60
    include_timeline = str(request.args.get("includeTimeline", "false")).lower() == "true"
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    components = [
        {
            "id": "api",
            "display_name": "Registry API",
            "status": "ok",
            "observed_at": now_iso,
            "metrics": {
                "p50_ms": int(_percentile(_REQUEST_TIMES, 0.50) * 1000),
                "p95_ms": int(_percentile(_REQUEST_TIMES, 0.95) * 1000),
            },
            "issues": [],
            "timeline": (
                [{"bucket": now_iso, "value": len(_REQUEST_TIMES), "unit": "req"}] if include_timeline else []
            ),
            "logs": [],
        }
    ]
    return (
        jsonify({"components": components, "generated_at": now_iso, "window_minutes": window_minutes}),
        200,
    )


@blueprint.route("/openapi", methods=["GET"])
def get_openapi_spec() -> tuple[Response, int]:
    """Return the OpenAPI specification."""
    try:
        # Load the OpenAPI specification from the YAML file
        openapi_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi.yaml")
        with open(openapi_path, encoding="utf-8") as f:
            openapi_spec = yaml.safe_load(f)
        return jsonify(openapi_spec), 200
    except Exception as e:
        logger.error("Failed to load OpenAPI specification: %s", e)
        return jsonify({"error": "OpenAPI specification not available"}), 500


# -------------------- Authentication (per-spec) --------------------


@blueprint.route("/authenticate", methods=["PUT"])
def authenticate_route() -> tuple[Response, int] | Response:
    # Minimal, non-sensitive logging
    logger.warning("AUTH: Authentication attempt received")

    body = _json_body() or {}
    keys_info = list(body.keys()) if isinstance(body, dict) else "not-dict"
    logger.warning("AUTH: Parsed body type=%s, keys=%s", type(body), keys_info)

    user = (body.get("user") or {}) if isinstance(body, dict) else {}
    secret = (body.get("secret") or {}) if isinstance(body, dict) else {}
    username = str(user.get("name", "")).strip()
    password = str(secret.get("password", "")).strip()

    logger.warning(
        "AUTH: Received authentication request for username=%s, has_password=%s", username, bool(password),
    )

    # Spec: if system supports auth, validate; else 501.
    if not username or not password:
        logger.warning("AUTH: Missing username or password")
        return jsonify({"message": "Missing user or password"}), 400
    if username != _DEFAULT_USER["username"] or password != _DEFAULT_USER["password"]:
        logger.warning("AUTH: Invalid credentials")
        return jsonify({"message": "The user or password is invalid."}), 401

    # Default user is always admin
    is_admin = True
    tok = _mint_token(username, is_admin)
    _TOKENS[tok] = is_admin
    logger.warning(
        "AUTH: Created token for user %s, is_admin=%s, token_count=%d", username, is_admin, len(_TOKENS),
    )

    try:
        TokenStore().add(tok)
        logger.warning("AUTH: Added token to TokenStore")
    except Exception as e:
        logger.warning(f"AUTH: Failed to add token to TokenStore: {e}")
    # Persist tokens so reloader doesn't log out the session in dev
    try:
        _persist_state()
    except Exception:
        pass

    # Spec's example returns a JSON string of the token with bearer prefix
    response = jsonify(f"bearer {tok}")
    logger.warning("AUTH: Returning token response with bearer prefix")
    return response, 200


# -------------------- Audit helper --------------------


def _audit_add(artifact_type: str, artifact_id: str, action: str, name: str = "") -> None:
    aid = str(artifact_id)
    entry = {
        "user": {"name": _DEFAULT_USER["username"], "is_admin": True},
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifact": {"name": name, "id": aid, "type": artifact_type},
        "action": action,
    }
    _AUDIT_LOG.setdefault(aid, []).append(entry)


# -------------------- Create/Register artifact --------------------


@blueprint.route("/artifact/<string:artifact_type>", methods=["POST"])
@_record_timing
def create_artifact(artifact_type: str) -> tuple[Response, int] | Response:
    _require_auth()
    if artifact_type not in {"model", "dataset", "code"}:
        return jsonify({"message": "invalid artifact_type"}), 400

    payload = _json_body()
    if not isinstance(payload, Mapping):
        return jsonify({"message": "artifact_data must be an object"}), 400

    metadata, data = _normalize_artifact_request(artifact_type, payload)
    url_value = _coerce_text(data.get("url"))
    if not url_value:
        return (
            jsonify(
                {
                    "message": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
                }
            ),
            400,
        )
    data["url"] = url_value

    # Conflict if same type+url already registered
    if _duplicate_url_exists(artifact_type, url_value):
        return jsonify({"message": "Artifact exists already."}), 409

    # Best-effort ingestion: fetch from provided URL and store a zip bundle
    artifact = Artifact(metadata=metadata, data=data)
    try:
        src_url = data.get("url")
        if isinstance(src_url, str) and src_url.startswith(("http://", "https://")):
            # Download source content (lightweight scrape) and package into a zip
            resp = requests.get(src_url, timeout=20)
            resp.raise_for_status()
            html_bytes = resp.content
            meta_json = json.dumps({
                "source_url": src_url,
                "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "type": artifact_type,
                "name": metadata.name,
            }).encode("utf-8")

            # Build zip bundle in memory
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                zout.writestr("source.html", html_bytes)
                zout.writestr("metadata.json", meta_json)
            buf.seek(0)

            bundle_name = f"{secure_filename(metadata.name or 'artifact')}.zip"
            if _S3.enabled:
                key_rel = f"uploads/{artifact_type}/{metadata.id}/{bundle_name}"
                try:
                    meta = _S3.put_file(buf, key_rel, "application/zip")
                    artifact.data["s3_bucket"] = meta["bucket"]
                    artifact.data["s3_key"] = meta["key"]
                    artifact.data["s3_version_id"] = meta.get("version_id")
                    artifact.data["content_type"] = meta.get("content_type") or "application/zip"
                    artifact.data["size"] = int(meta.get("size", 0))
                except Exception:
                    logger.exception("S3 put failed during ingest; falling back to local storage")
                    dest = _UPLOAD_DIR / bundle_name
                    try:
                        with open(dest, "wb") as f:
                            f.write(buf.getvalue())
                        artifact.data["path"] = str(dest.relative_to(_UPLOAD_DIR.parent))
                        artifact.data["content_type"] = "application/zip"
                        artifact.data["size"] = dest.stat().st_size
                    except Exception:
                        logger.exception("Failed to persist bundle locally during ingest")
            else:
                dest = _UPLOAD_DIR / bundle_name
                try:
                    with open(dest, "wb") as f:
                        f.write(buf.getvalue())
                    artifact.data["path"] = str(dest.relative_to(_UPLOAD_DIR.parent))
                    artifact.data["content_type"] = "application/zip"
                    artifact.data["size"] = dest.stat().st_size
                except Exception:
                    logger.exception("Failed to persist bundle locally during ingest")
        else:
            logger.warning("CREATE: Provided url is not http(s); skipping ingestion fetch")
    except Exception:
        logger.exception("CREATE: Ingestion fetch failed; continuing with metadata-only record")
    save_artifact(artifact)
    _audit_add(artifact_type, artifact.metadata.id, "CREATE", artifact.metadata.name)
    return jsonify(artifact_to_dict(artifact)), 201


# -------------------- Enumerate artifacts --------------------


@blueprint.route("/artifacts", methods=["POST"])
@_record_timing
def enumerate_artifacts_route() -> tuple[Response, int] | Response:
    _require_auth()

    body = request.get_json(silent=True)
    if not isinstance(body, list) or not body or not isinstance(body[0], dict):
        return jsonify({"message": "Invalid artifact_query"}), 400

    qd_raw = body[0]
    # Accept both spec-style (Name) and lowercase fields
    name_val = qd_raw.get("name")
    if name_val is None:
        name_val = qd_raw.get("Name") or qd_raw.get("artifactName")
    types_val = qd_raw.get("types")
    if types_val is None:
        types_val = qd_raw.get("Types")
    artifact_type_val = (
        qd_raw.get("artifact_type") or qd_raw.get("artifactType") or qd_raw.get("type") or qd_raw.get("Type")
    )
    page_val = qd_raw.get("page") or qd_raw.get("Page")
    page_size_val = qd_raw.get("page_size") or qd_raw.get("PageSize")

    if name_val is None:
        return jsonify({"message": "Invalid artifact_query"}), 400

    qd = {
        "artifact_type": artifact_type_val,
        "name": name_val,
        "types": types_val,
        "page": page_val,
        "page_size": page_size_val,
    }
    logger.warning(
        "ARTIFACTS: Received enumerate query name=%s types=%s page=%s page_size=%s offset=%s",
        qd.get("name"),
        qd.get("types"),
        qd.get("page"),
        qd.get("page_size"),
        request.args.get("offset"),
    )
    # allow query parameter limit to override requested page_size
    limit_param = request.args.get("limit")
    if limit_param is not None:
        try:
            limit_value = max(1, min(100, int(limit_param)))
            qd["page_size"] = limit_value
        except Exception:
            logger.warning("ARTIFACTS: Invalid limit parameter=%s", limit_param)

    # handle offset pagination header semantics
    offset_str = request.args.get("offset")
    if offset_str:
        try:
            offset = max(0, int(offset_str))
            page_size = int(qd.get("page_size", 25)) if isinstance(qd.get("page_size", 25), int) else 25
            if page_size <= 0:
                page_size = 25
            qd["page"] = (offset // page_size) + 1
        except Exception:
            pass

    query = _parse_query(
        {
            "artifact_type": qd.get("artifact_type"),
            "name": qd.get("name"),
            "types": qd.get("types", []),
            "page": qd.get("page", 1),
            "page_size": qd.get("page_size", 25),
        }
    )
    result = list_artifacts(query)

    current_page = int(result.get("page", 1))
    page_size = int(result.get("page_size", 25))
    total = int(result.get("total", 0))
    next_offset = current_page * page_size
    logger.warning(
        "ARTIFACTS: Returning page=%s size=%s total=%s next_offset=%s items_on_page=%s",
        current_page,
        page_size,
        total,
        next_offset,
        len(result.get("items", [])),
    )

    response_items = result.get("items", [])
    response = jsonify(response_items)
    if next_offset < total:
        response.headers["offset"] = str(next_offset)
    return response, 200


# -------------------- Artifact by id (GET/PUT/DELETE) --------------------


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    logger.warning("GET_ARTIFACT: type=%s id=%s", artifact_type, artifact_id)
    art = fetch_artifact(artifact_type, artifact_id)
    if not art:
        logger.warning("GET_ARTIFACT: Not found")
        return jsonify({"message": "Artifact does not exist."}), 404
    # Spec: returned artifact must include data.url
    if "url" not in (art.data or {}):
        logger.warning(
            "GET_ARTIFACT: Found but missing data.url name=%s type=%s data_keys=%s",
            art.metadata.name,
            art.metadata.type,
            sorted(list((art.data or {}).keys())) if isinstance(art.data, dict) else "not-dict",
        )
        return jsonify({"message": "Artifact missing url"}), 400
    logger.warning(
        "GET_ARTIFACT: OK name=%s version=%s has_metrics=%s",
        art.metadata.name,
        art.metadata.version,
        isinstance(art.data, dict) and bool((art.data or {}).get("metrics")),
    )
    _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
    return jsonify(artifact_to_dict(art)), 200


# Alias: support singular path for fetching an artifact as well
@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact_route_alias(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    # Delegate to the primary handler to keep behavior consistent
    return get_artifact_route(artifact_type, artifact_id)


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["PUT"])
@_record_timing
def update_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    body = _json_body() or {}
    if not isinstance(body, dict):
        return jsonify({"message": "Artifact payload must be object"}), 400
    md = body.get("metadata") or {}
    dt = body.get("data") or {}
    if not isinstance(md, dict) or not isinstance(dt, dict):
        return jsonify({"message": "Missing metadata or data"}), 400
    if str(md.get("id", "")) != artifact_id or str(md.get("type", "")) != artifact_type:
        return jsonify({"message": "metadata.id and metadata.type must match path"}), 400
    if not md.get("name"):
        return jsonify({"message": "metadata.name required"}), 400
    if "url" not in dt or not isinstance(dt.get("url"), str) or not dt.get("url").strip():
        return jsonify({"message": "data.url required"}), 400

    art = Artifact(
        metadata=ArtifactMetadata(
            id=artifact_id, name=str(md["name"]), type=artifact_type, version=str(md.get("version", "1.0.0")),
        ),
        data={"url": dt["url"].strip()} | {k: v for k, v in dt.items() if k != "url"},
    )
    save_artifact(art)
    _audit_add(artifact_type, artifact_id, "UPDATE", art.metadata.name)
    return jsonify({"message": "Artifact is updated."}), 200


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["DELETE"])
@_record_timing
def delete_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    k = _store_key(artifact_type, artifact_id)
    if k not in _STORE:
        # try primary
        try:
            existing = _ARTIFACT_STORE.get(artifact_type, artifact_id)
        except Exception:
            existing = None
        if not existing:
            return jsonify({"message": "Artifact does not exist."}), 404
    try:
        _ARTIFACT_STORE.delete(artifact_type, artifact_id)
    except Exception:
        logger.exception("Primary delete failed; removing from memory only")
    _STORE.pop(k, None)
    if k in _ARTIFACT_ORDER:
        _ARTIFACT_ORDER.remove(k)
    _audit_add(artifact_type, artifact_id, "UPDATE", "")
    try:
        _persist_state()
    except Exception:
        pass
    return jsonify({"message": "Artifact is deleted."}), 200


# -------------------- Upload helpers (kept) --------------------


@blueprint.route("/upload", methods=["GET"])
@_record_timing
def upload_list_route() -> tuple[Response, int] | Response:
    _require_auth()
    files = []
    for p in sorted(_UPLOAD_DIR.glob("**/*")):
        if p.is_file():
            files.append(
                {"name": p.name, "path": str(p.relative_to(_UPLOAD_DIR.parent)), "size": p.stat().st_size,}
            )
    return jsonify({"uploads": files}), 200


@blueprint.route("/upload", methods=["POST"])
@_record_timing
def upload_create_route() -> tuple[Response, int] | Response:
    _require_auth()
    if "file" not in request.files:
        return jsonify({"message": "Missing file part"}), 400
    f = request.files["file"]
    if not f or f.filename is None or f.filename.strip() == "":
        return jsonify({"message": "Empty filename"}), 400

    original_name = f.filename
    safe_name = secure_filename(original_name)
    if not safe_name:
        return jsonify({"message": "Invalid filename"}), 400

    requested_name = request.form.get("name")
    artifact_name = (requested_name or original_name or safe_name).strip() or safe_name
    artifact_type = request.form.get("artifact_type", "file")
    artifact_id = request.form.get("id", str(int(time.time() * 1000)))

    data: dict[str, Any]
    if _S3.enabled:
        key_rel = f"uploads/{artifact_type}/{artifact_id}/{safe_name}"
        try:
            meta = _S3.put_file(cast(BinaryIO, f.stream), key_rel, f.mimetype or "application/octet-stream")
            data = {
                "s3_bucket": meta["bucket"],
                "s3_key": meta["key"],
                "s3_version_id": meta.get("version_id"),
                "original_filename": f.filename,
                "content_type": meta.get("content_type") or f.mimetype,
                "size": int(meta.get("size", 0)),
            }
        except Exception:
            logger.exception("S3 upload failed; falling back to local storage")
            dest = _UPLOAD_DIR / safe_name
            counter = 1
            base = dest.stem
            ext = dest.suffix
            while dest.exists():
                dest = _UPLOAD_DIR / f"{base}_{counter}{ext}"
                counter += 1
            f.save(dest)
            data = {
                "path": str(dest.relative_to(_UPLOAD_DIR.parent)),
                "original_filename": f.filename,
                "content_type": f.mimetype,
                "size": dest.stat().st_size,
            }
    else:
        dest = _UPLOAD_DIR / safe_name
        counter = 1
        base = dest.stem
        ext = dest.suffix
        while dest.exists():
            dest = _UPLOAD_DIR / f"{base}_{counter}{ext}"
            counter += 1
        f.save(dest)
        data = {
            "path": str(dest.relative_to(_UPLOAD_DIR.parent)),
            "original_filename": f.filename,
            "content_type": f.mimetype,
            "size": dest.stat().st_size,
        }
    art = Artifact(
        metadata=ArtifactMetadata(id=artifact_id, name=artifact_name, type=artifact_type, version="1.0.0",), data=data,
    )
    save_artifact(art)
    _audit_add(artifact_type, artifact_id, "CREATE", artifact_name)
    return jsonify({"artifact": artifact_to_dict(art)}), 201


# -------------------- Rating --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/rate", methods=["GET"])
@_record_timing
def rate_model_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    
    # Check memory cache first
    if artifact_id in _RATINGS_CACHE:
        rating = _RATINGS_CACHE[artifact_id]
        return jsonify(_to_openapi_model_rating(rating)), 200
    
    artifact = fetch_artifact("model", artifact_id)
    if artifact is None:
        return jsonify({"message": "Artifact does not exist."}), 404
    
    # Check if we have fresh cached metrics in artifact data
    cached_rating = _rating_from_artifact_data(artifact)
    if cached_rating:
        _RATINGS_CACHE[artifact_id] = cached_rating
        return jsonify(_to_openapi_model_rating(cached_rating)), 200
    
    # Only infer links if we need to compute new rating (not cached)
    _infer_related_links(artifact)
    
    try:
        # Ensure a usable model_link exists for scoring
        if isinstance(artifact.data, dict):
            logger.info(
                "RATE: Checking links for id=%s keys=%s",
                artifact_id,
                sorted([k for k in artifact.data.keys() if "link" in k.lower() or "url" in k.lower() or k in ("s3_key", "path")])
            )
            # Prefer existing model_link/model_url; else try other fields
            link_fields = ["model_link", "model_url", "model", "url", "download_url", "s3_key", "path"]
            selected: str | None = None
            selected_field: str | None = None
            for fld in link_fields:
                v = artifact.data.get(fld)
                if isinstance(v, str) and v.strip():
                    selected = v.strip()
                    selected_field = fld
                    break
            
            # Normalize into model_link
            if selected:
                # If s3 or path provided, build URI
                if artifact.data.get("s3_key") and artifact.data.get("s3_bucket"):
                    selected = f"s3://{artifact.data['s3_bucket']}/{artifact.data['s3_key']}"
                    logger.info("RATE: Using S3 URI for %s: %s", artifact_id, selected)
                elif artifact.data.get("path") and not (selected.startswith("file://") or selected.startswith("http://") or selected.startswith("https://")):
                    abs_path = (_UPLOAD_DIR.parent / artifact.data["path"]).resolve()
                    selected = f"file://{abs_path}"
                    logger.info("RATE: Using file URI for %s: %s", artifact_id, selected)
                else:
                    logger.info("RATE: Using existing link for %s from field '%s': %s", artifact_id, selected_field, selected[:100])
                
                # Always set model_link for consistency
                artifact.data["model_link"] = selected
                # Only persist if not under heavy load (optional optimization)
                if len(_RATINGS_CACHE) < 10:  # heuristic: not many concurrent ratings
                    save_artifact(artifact)
                logger.info("RATE: Derived model_link for %s -> %s", artifact_id, selected)
            else:
                logger.error("RATE: No model link found for %s (keys=%s)", artifact_id, sorted(artifact.data.keys()))
                return jsonify({"message": "Artifact missing required model link for rating"}), 400

        logger.info(
            "RATE: Computing metrics id=%s name=%s",
            artifact_id,
            artifact.metadata.name,
        )
        
        # Score the artifact (MetricsCalculator has its own internal timeouts)
        # Remove signal-based timeout as it's not thread-safe under concurrent requests
        rating = _score_artifact_with_metrics(artifact)
        
        # Ensure phase 2 metrics (reproducibility, reviewedness, tree_score)
        rating = _ensure_phase_two_metrics(artifact, rating)
        
        logger.info(
            "RATE: Completed id=%s net=%.3f",
            artifact_id,
            float((rating.scores or {}).get("net_score", 0.0) or 0.0),
        )
        _RATINGS_CACHE[artifact_id] = rating

        if isinstance(artifact.data, dict):
            artifact.data["metrics"] = dict(rating.scores)
            artifact.data["metrics_latencies"] = dict(rating.latencies)
            artifact.data["trust_score"] = rating.scores.get("net_score", 0.0)
            artifact.data["last_rated"] = rating.generated_at.isoformat() + "Z"
            save_artifact(artifact)
        _audit_add("model", artifact_id, "RATE", artifact.metadata.name)
    except ValueError as exc:
        logger.warning("RATE: ValueError for %s: %s", artifact_id, exc)
        return jsonify({"message": str(exc)}), 400
    except Exception:
        logger.exception("RATE: Failed to score artifact %s", artifact_id)
        return (
            jsonify(
                {"message": "The artifact rating system encountered an error while computing at least one metric."}
            ),
            500,
        )
    return jsonify(_to_openapi_model_rating(rating)), 200


@blueprint.route("/artifacts/models/rate", methods=["POST"])
@_record_timing
def rate_models_batch_route() -> tuple[Response, int] | Response:
    """Batch-rate multiple model artifacts concurrently.

    Request body: { "ids": ["id1", "id2", ...] }
    Response: { "ratings": [ {<openapi rating>}, ... ] } preserving input order.
    """
    _require_auth()
    try:
        body = request.get_json(silent=True) or {}
        ids = body.get("ids")
        if not isinstance(ids, list) or not ids:
            return jsonify({"message": "Provide JSON body with 'ids': [ ... ]"}), 400

        # Prepare artifacts list preserving input order; skip missing with 404 item note
        artifacts: list[Artifact] = []
        missing_indices: list[int] = []
        for idx, aid in enumerate(ids):
            if not isinstance(aid, str) or not aid.strip():
                missing_indices.append(idx)
                continue
            art = fetch_artifact("model", aid.strip())
            if art is None:
                missing_indices.append(idx)
                continue
            # Infer related links for better scoring
            _infer_related_links(art)

            if isinstance(art.data, dict):
                try:
                    # Prefer existing fields; fall back to s3/path
                    link_fields = [
                        "model_link",
                        "model_url",
                        "model",
                        "url",
                        "download_url",
                        "downloadUrl",
                        "DownloadURL",
                        "s3_key",
                        "path",
                    ]
                    selected: str | None = None
                    selected_field: str | None = None
                    for fld in link_fields:
                        v = art.data.get(fld)
                        if isinstance(v, str) and v.strip():
                            selected = v.strip()
                            selected_field = fld
                            break
                    if selected:
                        # Build S3 or file URI when applicable
                        if art.data.get("s3_key") and art.data.get("s3_bucket"):
                            selected = f"s3://{art.data['s3_bucket']}/{art.data['s3_key']}"
                        elif art.data.get("path") and not (
                            selected.startswith("file://")
                            or selected.startswith("http://")
                            or selected.startswith("https://")
                        ):
                            abs_path = (_UPLOAD_DIR.parent / art.data["path"]).resolve()
                            selected = f"file://{abs_path}"
                        art.data["model_link"] = selected
                    else:
                        logger.warning(
                            "BATCH RATE: No model link found for %s (keys=%s)",
                            art.metadata.id,
                            sorted(list(art.data.keys())),
                        )
                except Exception:
                    logger.exception("BATCH RATE: Failed to normalize model_link for %s", art.metadata.id)

            # If cached and fresh, short-circuit
            cached_rating = _rating_from_artifact_data(art)
            if cached_rating is not None:
                _RATINGS_CACHE[art.metadata.id] = cached_rating
                artifacts.append(art)
            else:
                artifacts.append(art)

        if not artifacts and missing_indices:
            return jsonify({"message": "No valid artifacts found for provided ids", "missing": missing_indices}), 404

        # Rate concurrently
        ratings: list[ModelRating] = rate_artifacts_concurrently(artifacts)

        # Persist each rating back to artifact and cache
        openapi_ratings: list[dict[str, Any]] = []
        
        # Handle length mismatch if some ratings failed
        if len(ratings) != len(artifacts):
            logger.warning(
                "BATCH RATE: Rating count mismatch: %d artifacts, %d ratings. Proceeding with successful ratings only.",
                len(artifacts),
                len(ratings),
            )
        
        for art, rating in zip(artifacts, ratings):
            # Ensure phase 2 fields
            rating = _ensure_phase_two_metrics(art, rating)
            _RATINGS_CACHE[art.metadata.id] = rating
            if isinstance(art.data, dict):
                art.data["metrics"] = dict(rating.scores)
                art.data["metrics_latencies"] = dict(rating.latencies)
                art.data["trust_score"] = rating.scores.get("net_score", 0.0)
                art.data["last_rated"] = rating.generated_at.isoformat() + "Z"
                save_artifact(art)
            _audit_add("model", art.metadata.id, "RATE", art.metadata.name)
            openapi_ratings.append(_to_openapi_model_rating(rating))

        # If no ratings succeeded, return specific error
        if not openapi_ratings:
            logger.error("BATCH RATE: All %d artifacts failed to rate", len(artifacts))
            return (
                jsonify({"message": "All artifacts failed to rate. Check artifact data and try again."}),
                500,
            )

        # Build ordered response aligned to input ids; include None for missing if desired
        return jsonify({"ratings": openapi_ratings, "missing": missing_indices}), 200
    except Exception:
        logger.exception("Batch rating failed")
        return (
            jsonify({"message": "The batch artifact rating encountered an error while computing metrics."}),
            500,
        )


def _rating_from_artifact_data(artifact: Artifact) -> ModelRating | None:
    """Rehydrate a ModelRating from stored artifact data if still fresh."""
    if not isinstance(artifact.data, dict):
        return None
    metrics = artifact.data.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return None
    last_rated_at = _parse_timestamp(artifact.data.get("last_rated"))
    if (
        _RATING_CACHE_TTL_SECONDS > 0
        and last_rated_at
        and datetime.now(timezone.utc) - last_rated_at > timedelta(seconds=_RATING_CACHE_TTL_SECONDS)
    ):
        return None
    latencies_raw = artifact.data.get("metrics_latencies")
    cleaned_latencies: dict[str, int] = {}
    if isinstance(latencies_raw, dict):
        for key, value in latencies_raw.items():
            try:
                cleaned_latencies[key] = int(value)
            except Exception:
                cleaned_latencies[key] = 0
    if "net_score" not in cleaned_latencies:
        cleaned_latencies["net_score"] = 0
    scores = dict(metrics)
    if "net_score" not in scores and isinstance(artifact.data.get("trust_score"), (int, float)):
        scores["net_score"] = float(artifact.data["trust_score"])
    summary = {
        "category": artifact.metadata.type.upper(),
        "name": artifact.metadata.name,
        "model_link": artifact.data.get("model_link"),
    }
    generated_at = last_rated_at or datetime.now(timezone.utc)
    return ModelRating(
        id=artifact.metadata.id, generated_at=generated_at, scores=scores, latencies=cleaned_latencies, summary=summary,
    )


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        sanitized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        return datetime.fromisoformat(sanitized)
    except Exception:
        return None


def _to_openapi_model_rating(rating: ModelRating) -> dict[str, Any]:
    scores = rating.scores or {}
    lat_ms = rating.latencies or {}

    def _score(key: str) -> float:
        try:
            return float(scores.get(key, 0.0) or 0.0)
        except Exception:
            return 0.0

    def _latency(key: str) -> float:
        try:
            return float(lat_ms.get(key, 0) or 0) / 1000.0
        except Exception:
            return 0.0

    size_score = scores.get("size_score") or {
        "raspberry_pi": 0.0,
        "jetson_nano": 0.0,
        "desktop_pc": 0.0,
        "aws_server": 0.0,
    }

    response: dict[str, Any] = {
        "name": rating.summary.get("name"),
        "category": rating.summary.get("category"),
        "net_score": _score("net_score"),
        "net_score_latency": _latency("net_score"),
        "ramp_up_time": _score("ramp_up_time"),
        "ramp_up_time_latency": _latency("ramp_up_time"),
        "bus_factor": _score("bus_factor"),
        "bus_factor_latency": _latency("bus_factor"),
        "performance_claims": _score("performance_claims"),
        "performance_claims_latency": _latency("performance_claims"),
        "license": _score("license"),
        "license_latency": _latency("license"),
        "dataset_and_code_score": _score("dataset_and_code_score"),
        "dataset_and_code_score_latency": _latency("dataset_and_code_score"),
        "dataset_quality": _score("dataset_quality"),
        "dataset_quality_latency": _latency("dataset_quality"),
        "code_quality": _score("code_quality"),
        "code_quality_latency": _latency("code_quality"),
        "reproducibility": _score("reproducibility"),
        "reproducibility_latency": _latency("reproducibility"),
        "reviewedness": _score("reviewedness"),
        "reviewedness_latency": _latency("reviewedness"),
        "tree_score": _score("tree_score"),
        "tree_score_latency": _latency("tree_score"),
        "size_score": size_score,
        "size_score_latency": _latency("size_score"),
    }

    # Provide additional alias fields expected by some clients
    alias_map = {
        "RampUp": "ramp_up_time",
        "Correctness": "code_quality",
        "BusFactor": "bus_factor",
        "ResponsiveMaintainer": "reviewedness",
        "LicenseScore": "license",
        "GoodPinningPractice": "dataset_and_code_score",
        "PullRequest": "performance_claims",
        "NetScore": "net_score",
    }
    for alias, internal in alias_map.items():
        response[alias] = response.get(internal, _score(internal))
        response[f"{alias}Latency"] = response.get(f"{internal}_latency", _latency(internal))

    return response


# -------------------- Download (kept) & size cost --------------------



@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>/download", methods=["GET"])
@_record_timing
def download_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    """Generic download route for any artifact type.

    Serves stored bundles from S3 or local disk. Does not redirect to external URLs.
    """
    _require_auth()
    part = request.args.get("part", "all")
    art = fetch_artifact(artifact_type, artifact_id)
    if art is None:
        return jsonify({"message": "Artifact does not exist."}), 404

    # Try S3 first
    if isinstance(art.data, dict) and _S3.enabled:
        s3_key = art.data.get("s3_key")
        s3_bucket = art.data.get("s3_bucket")
        if isinstance(s3_key, str) and s3_bucket:
            ver = art.data.get("s3_version_id")
            try:
                body, meta = _S3.get_object(s3_key, ver)
                size_bytes = int(meta.get("size", len(body)))
                if part == "all":
                    resp = send_file(
                        io.BytesIO(body),
                        as_attachment=True,
                        download_name=f"{artifact_id}.zip",
                        mimetype=meta.get("content_type") or "application/zip",
                    )
                    resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
                    _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
                    return resp
                with zipfile.ZipFile(io.BytesIO(body), "r") as zin:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        prefix = f"{part.strip('/')}/"
                        for info in zin.infolist():
                            if info.filename.startswith(prefix):
                                zout.writestr(info, zin.read(info))
                    buf.seek(0)
                resp = send_file(
                    buf, as_attachment=True, download_name=f"{artifact_id}-{part}.zip", mimetype="application/zip",
                )
                resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
                _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
                return resp
            except Exception:
                logger.exception("Failed to serve from S3; falling back to local if available")

    # Local disk
    rel = art.data.get("path") if isinstance(art.data, dict) else None
    if not isinstance(rel, str) or not rel:
        return jsonify({"message": "Artifact has no stored package path"}), 400
    zpath = (_UPLOAD_DIR.parent / rel).resolve()
    if not zpath.exists():
        return jsonify({"message": "Package not found on disk"}), 404

    size_bytes = zpath.stat().st_size
    if part == "all":
        resp = send_file(
            str(zpath), as_attachment=True, download_name=zpath.name, etag=True, mimetype="application/zip",
        )
        resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
        _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
        return resp

    with zipfile.ZipFile(str(zpath), "r") as zin:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            prefix = f"{part.strip('/')}/"
            for info in zin.infolist():
                if info.filename.startswith(prefix):
                    zout.writestr(info, zin.read(info))
        buf.seek(0)

    resp = send_file(buf, as_attachment=True, download_name=f"{artifact_id}-{part}.zip", mimetype="application/zip")
    resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
    _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
    return resp

@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>/cost", methods=["GET"])
@_record_timing
def artifact_cost_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    dependency = request.args.get("dependency", "false").lower() == "true"

    art = fetch_artifact(artifact_type, artifact_id)
    if art is None:
        return jsonify({"message": "Artifact does not exist."}), 404
    try:
        standalone_cost_mb = _calculate_artifact_size_mb(art)

        if not dependency:
            return jsonify({artifact_id: {"total_cost": round(standalone_cost_mb, 2)}}), 200

        visited: set[str] = set()
        cost_map: dict[str, dict[str, float]] = {}

        def _collect_costs(current_art, current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            size_mb = _calculate_artifact_size_mb(current_art)
            cost_map[current_id] = {
                "standalone_cost": round(size_mb, 2),
                "total_cost": round(size_mb, 2),
            }
            if isinstance(current_art.data, dict):
                for key in ("code_link", "dataset_link", "base_model_id", "dependencies"):
                    dep_val = current_art.data.get(key)
                    if isinstance(dep_val, str) and dep_val.strip():
                        dep_art = fetch_artifact(artifact_type, dep_val)
                        if dep_art:
                            _collect_costs(dep_art, dep_val)
                    elif isinstance(dep_val, list):
                        for dep_id in dep_val:
                            if isinstance(dep_id, str):
                                dep_art = fetch_artifact(artifact_type, dep_id)
                                if dep_art:
                                    _collect_costs(dep_art, dep_id)

        _collect_costs(art, artifact_id)
        total_sum = sum(c["standalone_cost"] for c in cost_map.values())
        for aid in cost_map:
            cost_map[aid]["total_cost"] = round(total_sum, 2)
        return jsonify(cost_map), 200
    except Exception:
        logger.exception("Failed to calculate artifact cost for %s", artifact_id)
        return jsonify({"message": "The artifact cost calculator encountered an error."}), 500


def _calculate_artifact_size_mb(artifact) -> float:
    size_bytes = 0
    if isinstance(artifact.data, dict):
        if artifact.data.get("size"):
            size_bytes = int(artifact.data.get("size", 0))
        elif artifact.data.get("s3_key") and _S3.enabled:
            try:
                key = artifact.data.get("s3_key")
                ver = artifact.data.get("s3_version_id")
                if isinstance(key, str):
                    _, meta = _S3.get_object(key, ver)
                    size_bytes = int(meta.get("size", 0))
            except Exception:
                logger.warning("Failed to get S3 object size for %s", artifact.metadata.id)
        if size_bytes == 0 and artifact.data.get("path"):
            rel = artifact.data.get("path")
            if isinstance(rel, str) and rel:
                zpath = (_UPLOAD_DIR.parent / rel).resolve()
                if zpath.exists():
                    size_bytes = zpath.stat().st_size
        # If still no size, and artifact has an external URL, estimate a nominal size
        if size_bytes == 0:
            url = None
            for key in (
                "url",
                "download_url",
                "downloadUrl",
                "DownloadURL",
                "model_link",
                "modelLink",
                "model_url",
                "modelUrl",
                "link",
            ):
                val = artifact.data.get(key)
                if isinstance(val, str) and val.strip() and (val.startswith("http://") or val.startswith("https://")):
                    url = val.strip()
                    break
            if url:
                # Heuristic: return a nominal cost for external URL-only artifacts (e.g., 10MB)
                return 10.0
    return size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0


# -------------------- Lineage --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/lineage", methods=["GET"])
@_record_timing
def lineage_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    art = fetch_artifact("model", artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404
    s3_key = art.data.get("s3_key") if isinstance(art.data, dict) else None
    s3_ver = art.data.get("s3_version_id") if isinstance(art.data, dict) else None
    zbody: bytes | None = None
    zpath = None
    if s3_key and _S3.enabled:
        try:
            zbody, _meta = _S3.get_object(s3_key, s3_ver)
        except Exception:
            logger.exception("Failed to fetch S3 object for lineage")
            zbody = None
    if zbody is None:
        rel = art.data.get("path")
        if not rel:
            # No S3, no local path; check if we have a URL (won't have lineage info)
            url = art.data.get("url") or art.data.get("download_url") or art.data.get("model_link")
            if isinstance(url, str) and url.strip() and (url.startswith("http://") or url.startswith("https://")):
                # URL-only artifact: no lineage data available
                nodes = [{"artifact_id": artifact_id, "name": art.metadata.name, "source": "url_only"}]
                return jsonify({"nodes": nodes, "edges": []}), 200
            return (
                jsonify(
                    {
                        "message": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."
                    }
                ),
                400,
            )
        zpath = (_UPLOAD_DIR.parent / rel).resolve()
        if not zpath.exists():
            # Check if external URL exists for fallback
            url = art.data.get("url") or art.data.get("download_url") or art.data.get("model_link")
            if isinstance(url, str) and url.strip() and (url.startswith("http://") or url.startswith("https://")):
                nodes = [{"artifact_id": artifact_id, "name": art.metadata.name, "source": "url_only"}]
                return jsonify({"nodes": nodes, "edges": []}), 200
            return jsonify({"message": "Artifact package not found"}), 404

    parents: list[str] = []
    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(zbody), "r") if zbody is not None else zipfile.ZipFile(str(zpath), "r")
        with zf_ctx as zf:
            cand = [n for n in zf.namelist() if n.endswith("config.json")]
            for name in cand:
                try:
                    cfg = json.loads(zf.read(name))
                    for key in ("base_model", "architectures", "parents", "parent_model"):
                        v = cfg.get(key)
                        if isinstance(v, str):
                            parents.append(v)
                        elif isinstance(v, list):
                            parents += [x for x in v if isinstance(x, str)]
                except Exception:
                    continue
    except Exception:
        pass
    parents = sorted(set(parents))
    nodes = [{"artifact_id": artifact_id, "name": art.metadata.name, "source": "config_json"}]
    for p in parents:
        nodes.append({"artifact_id": p, "name": p, "source": "config_json"})
    edges = [
        {"from_node_artifact_id": p, "to_node_artifact_id": artifact_id, "relationship": "derived_from",}
        for p in parents
    ]
    return jsonify({"nodes": nodes, "edges": edges}), 200


# -------------------- License check (per-spec path) --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/license-check", methods=["POST"])
@_record_timing
def model_license_check_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    body = _json_body()
    gh_url = str(body.get("github_url", "")).strip()
    if not gh_url:
        return (
            jsonify({"message": "The license check request is malformed or references an unsupported usage context."}),
            400,
        )
    # Stub OK result (your adapter could do real checks)
    return jsonify(True), 200


# -------------------- Reset --------------------


@blueprint.route("/reset", methods=["DELETE"])
def reset_route() -> tuple[Response, int] | Response:
    _require_auth(admin=True)

    # Log initial state
    logger.warning(f"RESET: Starting reset. Current _STORE has {len(_STORE)} items")
    logger.warning(f"RESET: Current _RATINGS_CACHE has {len(_RATINGS_CACHE)} items")
    logger.warning(f"RESET: Current _AUDIT_LOG has {len(_AUDIT_LOG)} items")
    logger.warning(f"RESET: Current _TOKENS has {len(_TOKENS)} items")
    logger.warning(
        f"RESET: _ARTIFACT_STORE instance id: {id(_ARTIFACT_STORE)}, use_dynamodb={_ARTIFACT_STORE.use_dynamodb}"
    )
    logger.warning(f"RESET: _ARTIFACT_STORE._memory_store has {len(_ARTIFACT_STORE._memory_store)} items")

    # Clear in-memory stores (but keep tokens)
    _STORE.clear()
    _RATINGS_CACHE.clear()
    _AUDIT_LOG.clear()

    # Also clear the global _ARTIFACT_STORE's memory
    _ARTIFACT_STORE._memory_store.clear()

    logger.warning(
        f"RESET: After clearing in-memory: _STORE={len(_STORE)}, _RATINGS_CACHE={len(_RATINGS_CACHE)}, _AUDIT_LOG={len(_AUDIT_LOG)}"
    )
    logger.warning(f"RESET: After clearing _ARTIFACT_STORE._memory_store={len(_ARTIFACT_STORE._memory_store)}")

    # Clear DynamoDB stores
    try:
        logger.warning(f"RESET: Calling _ARTIFACT_STORE.clear() with use_dynamodb={_ARTIFACT_STORE.use_dynamodb}")
        _ARTIFACT_STORE.clear()
        logger.warning("RESET: _ARTIFACT_STORE.clear() completed successfully")

        # Verify it's actually cleared
        all_artifacts = _ARTIFACT_STORE.list_all()
        logger.warning(f"RESET: After _ARTIFACT_STORE.clear(), list_all() returns {len(all_artifacts)} items")
        if all_artifacts:
            logger.error(
                f"RESET: WARNING - Artifacts still present after clear: {[a.get('metadata', {}).get('id') for a in all_artifacts[:5]]}"
            )
    except Exception as e:
        logger.exception(f"RESET: Failed to clear _ARTIFACT_STORE: {e}")

    try:
        cache = RatingsCache()
        logger.warning(f"RESET: RatingsCache use_dynamodb={cache.use_dynamodb}")
        cache.clear()
        logger.warning("RESET: RatingsCache.clear() completed successfully")
    except Exception as e:
        logger.exception(f"RESET: Failed to clear RatingsCache (DynamoDB): {e}")

    # Don't clear tokens - keep authentication working
    logger.warning(f"RESET: Keeping _TOKENS with {len(_TOKENS)} items for authentication")
    logger.warning("RESET: Reset complete!")
    # Persist the cleared store while keeping tokens
    try:
        _persist_state()
    except Exception:
        pass

    return jsonify({"message": "Registry is reset."}), 200


# -------------------- Name and RegEx lookups --------------------


@blueprint.route("/artifact/byName/<string:name>", methods=["GET"])
@_record_timing
def by_name_route(name: str) -> tuple[Response, int] | Response:
    _require_auth()
    needle = name.strip().lower()
    logger.warning(
        "BY_NAME: lookup name='%s' store_size=%d token_present=%s",
        needle,
        len(_STORE),
        bool(request.headers.get("X-Authorization") or request.headers.get("Authorization")),
    )
    # Search in-memory first
    found: list[Artifact] = [art for art in _STORE.values() if art.metadata.name.lower() == needle]
    # If not found, attempt primary store enumeration as fallback (may include duplicates)
    if not found:
        try:
            primary_items = _ARTIFACT_STORE.list_all()
        except Exception:
            primary_items = []
        logger.warning("BY_NAME: memory miss; enumerating primary count=%d", len(primary_items or []))
        for data in primary_items or []:
            md = data.get("metadata", {})
            nm = str(md.get("name", ""))
            if nm.lower() == needle:
                found.append(
                    Artifact(
                        metadata=ArtifactMetadata(
                            id=str(md.get("id", "")),
                            name=nm,
                            type=str(md.get("type", "")),
                            version=str(md.get("version", "1.0.0")),
                        ),
                        data=data.get("data", {}),
                    )
                )
    if not found:
        sample_names = sorted({a.metadata.name for a in _STORE.values()})[:10]
        logger.warning("BY_NAME: no match for '%s'. sample_names=%s", needle, sample_names)
        return jsonify({"message": "No such artifact"}), 404
    entries = []
    seen_ids: set[str] = set()
    for art in found:
        if art.metadata.id in seen_ids:
            continue
        seen_ids.add(art.metadata.id)
        entries.append(artifact_to_dict(art))
    return jsonify(entries), 200


@blueprint.route("/artifact/byRegEx", methods=["POST"])
@_record_timing
def by_regex_route() -> tuple[Response, int] | Response:
    _require_auth()
    body = _json_body()
    # Support both 'regex' and spec-stated 'RegEx'
    raw_pattern = str(body.get("regex") or body.get("RegEx") or "").strip()
    if not raw_pattern:
        return (
            jsonify(
                {"message": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"}
            ),
            400,
        )
    if len(raw_pattern) > _REGEX_MAX_PATTERN_LENGTH:
        logger.warning("BY_REGEX: Rejecting pattern exceeding length limit (%d chars)", len(raw_pattern))
        return jsonify({"message": "Regex pattern too complex and may cause excessive backtracking."}), 400
    if _is_dangerous_regex(raw_pattern):
        logger.warning("BY_REGEX: Rejecting pattern '%s' due to dangerous structure", raw_pattern)
        return jsonify({"message": "Regex pattern too complex and may cause excessive backtracking."}), 400

    name_only = _is_plain_name_pattern(raw_pattern)
    try:
        # Apply case-insensitive matching by default; callers can force sensitivity via inline flags.
        flags = re.IGNORECASE
        pattern = re.compile(raw_pattern, flags)
    except re.error:
        return jsonify({"message": "Invalid regex"}), 400

    # Runtime bomb test using timeout-protected evaluation
    test_candidate = "a" * 100 + "b"
    match_fn = pattern.fullmatch if name_only else pattern.search
    ok, _ = _safe_eval_with_timeout(lambda: match_fn(test_candidate) is not None, timeout_ms=1000)
    if not ok:
        logger.warning("BY_REGEX: Pattern '%s' failed runtime ReDoS test", raw_pattern)
        return jsonify({"message": "Regex pattern too complex and may cause excessive backtracking."}), 400

    start_time = time.time()
    deadline = start_time + _REGEX_MAX_TIME_SECONDS
    matches: list[dict[str, Any]] = []
    scanned = 0

    logger.warning(
        "BY_REGEX: raw='%s' store_size=%d exact_match=%s", raw_pattern, len(_STORE), name_only,
    )

    for art in _STORE.values():
        if scanned >= _REGEX_MAX_ARTIFACTS or time.time() > deadline:
            logger.warning("BY_REGEX: Stopping scan early (scanned=%d, matches=%d)", scanned, len(matches))
            break
        scanned += 1

        name_match = False
        try:
            name_match = _safe_name_match(
                pattern,
                art.metadata.name,
                exact_match=name_only,
                raw_pattern=raw_pattern,
                context="artifact metadata name",
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("BY_REGEX: Name match error for id=%s: %s", art.metadata.id, exc)

        readme_match = False
        if not name_only:
            readme_source = art.data if isinstance(art.data, Mapping) else None
            readme = _extract_readme_snippet(readme_source)
            if readme:
                try:
                    readme_match = _safe_text_search(
                        pattern, readme, raw_pattern=raw_pattern, context="artifact readme",
                    )
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning("BY_REGEX: README match error for id=%s: %s", art.metadata.id, exc)

        if name_match or readme_match:
            matches.append(artifact_to_dict(art))
            if len(matches) >= _REGEX_MAX_MATCHES:
                logger.warning("BY_REGEX: Collected %d matches, stopping early", len(matches))
                break

    if not matches:
        logger.warning("BY_REGEX: no matches for pattern '%s'", raw_pattern)
        return jsonify({"message": "No artifact found under this regex"}), 404

    logger.warning(
        "BY_REGEX: returning matches=%d scanned=%d elapsed=%.3fs", len(matches), scanned, time.time() - start_time,
    )
    return jsonify(matches), 200


# -------------------- Audit log --------------------


@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>/audit", methods=["GET"])
@_record_timing
def audit_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    _ = fetch_artifact(artifact_type, artifact_id)
    if not _ and _store_key(artifact_type, artifact_id) not in _STORE:
        return jsonify({"message": "Artifact does not exist."}), 404
    entries = _AUDIT_LOG.get(str(artifact_id), [])
    _audit_add(artifact_type, artifact_id, "AUDIT")
    return jsonify(entries), 200


# -------------------- Tracks --------------------


@blueprint.route("/tracks", methods=["GET"])
def tracks_route() -> tuple[Response, int] | Response:
    return jsonify({"plannedTracks": ["Performance track", "Access control track"]}), 200