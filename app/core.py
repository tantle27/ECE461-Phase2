from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast, BinaryIO

from flask import Blueprint, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

from app.db_adapter import ArtifactStore, RatingsCache, TokenStore
from app.s3_adapter import S3Storage
from app.scoring import ModelRating, _score_artifact_with_metrics

logger = logging.getLogger(__name__)

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
_RATINGS_CACHE: dict[str, ModelRating] = {}
# Optional S3 blob store (enabled via USE_S3=true)
_S3 = S3Storage()
# Lambda: Only /tmp is writable, so default to /tmp/uploads instead of ./uploads
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Simple bearer-token store for default user
_TOKENS: set[str] = set()
_DEFAULT_USER = {
    "username": "ece30861defaultadminuser",
    "password": "correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages",
    "role": "admin",
}

# ---------------------------------------------------------------------------
# Observability helpers
# ---------------------------------------------------------------------------

_REQUEST_TIMES: list[float] = []
_STATS = {"ok": 0, "err": 0}
ps_start_time = time.time()


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


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    return {
        "metadata": {
            "id": artifact.metadata.id,
            "name": artifact.metadata.name,
            "type": artifact.metadata.type,
            "version": artifact.metadata.version,
        },
        "data": artifact.data,
    }


def _store_key(artifact_type: str, artifact_id: str) -> str:
    return f"{artifact_type}:{artifact_id}"


def save_artifact(artifact: Artifact) -> Artifact:
    logger.info("Saving artifact %s/%s", artifact.metadata.type, artifact.metadata.id)
    # Persist via adapter (writes to DynamoDB if enabled)
    try:
        _ARTIFACT_STORE.save(
            artifact.metadata.type,
            artifact.metadata.id,
            artifact_to_dict(artifact),
        )
    except Exception:
        logger.exception("Failed to persist artifact via adapter; keeping in memory only")
    # Always keep in-memory copy (fallback)
    _STORE[_store_key(artifact.metadata.type, artifact.metadata.id)] = artifact
    return artifact


def fetch_artifact(artifact_type: str, artifact_id: str) -> Artifact | None:
    logger.info("Fetching artifact %s/%s", artifact_type, artifact_id)
    # Try primary store first
    try:
        data = _ARTIFACT_STORE.get(artifact_type, artifact_id)
        if data:
            md = data.get("metadata", {})
            return Artifact(
                metadata=ArtifactMetadata(
                    id=str(md.get("id", artifact_id)),
                    name=str(md.get("name", "")),
                    type=str(md.get("type", artifact_type)),
                    version=str(md.get("version", "1.0.0")),
                ),
                data=data.get("data", {}),
            )
    except Exception:
        logger.exception("Primary store fetch failed; falling back to memory")
    # Fallback to in-memory
    return _STORE.get(_store_key(artifact_type, artifact_id))


def list_artifacts(query: ArtifactQuery) -> dict[str, Any]:
    logger.info("Listing artifacts page=%s size=%s", query.page, query.page_size)
    items: list[Artifact] = []
    used_primary = False
    try:
        # Prefer primary store (DynamoDB if enabled)
        primary_items = _ARTIFACT_STORE.list_all(query.artifact_type)
        if primary_items:
            for data in primary_items:
                md = data.get("metadata", {})
                items.append(
                    Artifact(
                        metadata=ArtifactMetadata(
                            id=str(md.get("id", "")),
                            name=str(md.get("name", "")),
                            type=str(md.get("type", "")),
                            version=str(md.get("version", "1.0.0")),
                        ),
                        data=data.get("data", {}),
                    )
                )
            used_primary = True
    except Exception:
        logger.exception("Primary store list failed; falling back to memory")
    if not used_primary:
        # Sort in two steps to keep line-length under limits and improve readability
        store_vals = sorted(_STORE.values(), key=lambda art: (art.metadata.type, art.metadata.name))
        items = [
            item
            for item in store_vals
            if (not query.artifact_type or item.metadata.type == query.artifact_type)
        ]
    # Apply types filter if provided (OpenAPI spec requirement)
    if query.types:
        items = [item for item in items if item.metadata.type in query.types]
    if query.name:
        name_lower = query.name.lower()
        items = [item for item in items if name_lower in item.metadata.name.lower()]
    return _paginate_artifacts(items, query.page, query.page_size)


def reset_storage() -> None:
    logger.warning("Resetting in-memory artifact store")
    _STORE.clear()
    _RATINGS_CACHE.clear()
    _TOKENS.clear()


def _require_auth(admin: bool = False) -> None:
    # Allow X-Authorization quick path
    token = request.headers.get("X-Authorization")

    # Also allow Authorization: Bearer <token> from /login
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            bearer = auth.split(" ", 1)[1].strip()
            if bearer in _TOKENS:
                token = "user"  # normalize

    if not token:
        logger.warning("Missing authorization")
        raise_error(HTTPStatus.UNAUTHORIZED, "Missing authorization")

    if admin and token != "admin":
        # If bearer token was provided, accept as admin for the default seeded user
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer ") and any(True for _ in _TOKENS):
            return
        logger.warning("Admin access required")
        raise_error(HTTPStatus.FORBIDDEN, "Admin access required")


def _json_body() -> dict[str, Any]:
    if not request.is_json:
        raise_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Expected application/json body")
    payload = request.get_json(silent=True)
    if payload is None:
        raise_error(HTTPStatus.BAD_REQUEST, "Invalid JSON payload")
    if not isinstance(payload, dict):
        raise_error(HTTPStatus.BAD_REQUEST, "Expected JSON object")
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


def _parse_query_args(args: Mapping[str, Any]) -> ArtifactQuery:
    page = _safe_int(args.get("page", 1), 1)
    page_size = _safe_int(args.get("page_size", 25), 25)
    return ArtifactQuery(
        artifact_type=args.get("artifact_type"),
        name=args.get("name"),
        page=page if page > 0 else 1,
        page_size=page_size if 1 <= page_size <= 100 else 25,
    )


def raise_error(status: HTTPStatus, message: str) -> None:
    response = jsonify({"message": message})
    response.status_code = status
    from flask import abort

    abort(response)


def _sanitize_search_pattern(raw_pattern: str) -> str:
    if len(raw_pattern) > 128:
        raw_pattern = raw_pattern[:128]
    allowed = re.sub(r"[^\w\s\.\*\+\?\|\[\]\(\)\^\$]", "", raw_pattern)
    return allowed or ".*"


def _prefix_match(hay: str, needle: str) -> bool:
    return hay.lower().startswith(needle.lower())


def _substring_match(hay: str, needle: str) -> bool:
    return needle.lower() in hay.lower()


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


def _search_artifacts(
    pattern: re.Pattern[str] | None,
    artifact_type: str | None,
    mode: str,
    query_text: str,
) -> list[Artifact]:
    matches: list[Artifact] = []
    for artifact in _STORE.values():
        if artifact_type and artifact.metadata.type != artifact_type:
            continue
        name = artifact.metadata.name
        readme = artifact.data.get("readme") if isinstance(artifact.data, dict) else None
        readme_text = readme if isinstance(readme, str) else ""

        ok = False
        if mode == "regex" and pattern is not None:
            ok = bool(pattern.search(name) or pattern.search(readme_text))
        elif mode == "prefix":
            ok = _prefix_match(name, query_text)
        else:  # substring (default)
            ok = _substring_match(name, query_text) or _substring_match(readme_text, query_text)

        if ok:
            matches.append(artifact)
    matches.sort(key=lambda art: (art.metadata.type, art.metadata.name))
    return matches


def _validate_artifact_data(artifact_type: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise_error(
            HTTPStatus.BAD_REQUEST,
            "Artifact 'data' must be a JSON object",
        )
    normalized: dict[str, Any] = dict(data)

    # Support OpenAPI spec format: {"url": "..."}
    if "url" in normalized and not normalized.get("model_link"):
        url = normalized.get("url")
        if isinstance(url, str) and url.strip():
            # Map url to the appropriate link field based on artifact_type
            if artifact_type == "model":
                normalized["model_link"] = url.strip()
            elif artifact_type == "code":
                normalized["code_link"] = url.strip()
            elif artifact_type == "dataset":
                normalized["dataset_link"] = url.strip()
    if artifact_type == "model":
        model_link_raw = (
            normalized.get("model_link") or normalized.get("model_url") or normalized.get("model")
        )
        if not isinstance(model_link_raw, str) or not model_link_raw.strip():
            raise_error(
                HTTPStatus.BAD_REQUEST,
                "Model artifacts must include a non-empty 'model_link' field or 'url' field",
            )
        # Type narrowing: model_link_raw is guaranteed to be str here
        model_link_str = cast(str, model_link_raw)
        normalized["model_link"] = model_link_str.strip()
        for key in ("code_link", "code", "dataset_link", "dataset"):
            if key in normalized:
                value = normalized[key]
                if value is None or value == "":
                    normalized.pop(key)
                    continue
                if not isinstance(value, str):
                    raise_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Field '{key}' must be a string when provided",
                    )
                normalized[key] = value.strip()
    return normalized


# ------------------ SemVer helpers for version search ------------------

_SEMVER_RE = re.compile(r"^v?(?P<maj>0|[1-9]\d*)\.(?P<min>0|[1-9]\d*)\.(?P<pat>0|[1-9]\d*)$")


def _parse_semver(v: str) -> tuple[int, int, int] | None:
    m = _SEMVER_RE.match(v.strip())
    if not m:
        return None
    return int(m["maj"]), int(m["min"]), int(m["pat"])


def _cmp_ver(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a > b) - (a < b)


def _in_version_range(v: str, spec: str) -> bool:
    pv = _parse_semver(v)
    if not pv:
        return False
    s = spec.strip()
    if "-" in s and not s.startswith(("~", "^")):
        lo, hi = s.split("-", 1)
        plo, phi = _parse_semver(lo), _parse_semver(hi)
        if not plo or not phi:
            return False
        return _cmp_ver(plo, pv) <= 0 <= _cmp_ver(pv, phi)
    if s.startswith("~"):
        base = _parse_semver(s[1:])
        if not base:
            return False
        maj, minr, pat = base
        return pv[0] == maj and pv[1] == minr and pv[2] >= pat
    if s.startswith("^"):
        base = _parse_semver(s[1:])
        if not base:
            return False
        maj, minr, pat = base
        if maj > 0:
            return pv[0] == maj and (pv[1], pv[2]) >= (minr, pat)
        if maj == 0 and minr > 0:
            return pv[0] == 0 and pv[1] == minr and pv[2] >= pat
        return pv == (0, 0, pat) or (pv[0] == 0 and pv[1] == 0 and pv[2] >= pat)
    ev = _parse_semver(s)
    return bool(ev and ev == pv)


# ---------------------------------------------------------------------------
# Flask blueprint and routes
# ---------------------------------------------------------------------------

blueprint = Blueprint("registry", __name__)

# -------------------- Auth & health & OpenAPI --------------------


@blueprint.route("/login", methods=["POST"])
def login_route() -> tuple[Response, int] | Response:
    body = _json_body()
    u, p = body.get("username"), body.get("password")
    if u == _DEFAULT_USER["username"] and p == _DEFAULT_USER["password"]:
        tok = f"t_{int(time.time()*1000)}"
        _TOKENS.add(tok)
        return jsonify({"access_token": tok, "token_type": "bearer"}), 200
    return jsonify({"message": "invalid credentials"}), 401


@blueprint.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    return jsonify({"ok": True}), 200


_OPENAPI = {
    "openapi": "3.0.2",
    "info": {"title": "ECE 461 - Fall 2025 - Project Phase 2", "version": "3.3.1"},
    "paths": {
        "/artifact/{artifact_type}": {"post": {"summary": "Create artifact"}},
        "/artifacts": {"post": {"summary": "Enumerate artifacts"}},
        "/directory": {"get": {"summary": "List artifacts"}},
        "/search": {"get": {"summary": "Search artifacts"}},
        "/artifact/model/{artifact_id}/rate": {"get": {"summary": "Rate model"}},
        "/artifact/model/{artifact_id}/download": {"get": {"summary": "Download model"}},
        "/artifact/model/{artifact_id}/lineage": {"get": {"summary": "Lineage graph"}},
        "/artifact/model/{artifact_id}/license-check": {"post": {"summary": "License check"}},
        "/artifact/byRegEx": {"post": {"summary": "Artifacts by RegEx"}},
        "/artifact/byName/{name}": {"get": {"summary": "Artifacts by Name"}},
        "/authenticate": {"put": {"summary": "Create auth token"}},
        "/ingest/hf": {"post": {"summary": "Gate and ingest HF model"}},
        "/license/check": {"post": {"summary": "License compatibility"}},
        "/reset": {"delete": {"summary": "Reset system"}},
        "/health": {"get": {"summary": "System health"}},
        "/login": {"post": {"summary": "Obtain bearer token"}},
    },
}


@blueprint.route("/openapi", methods=["GET"])
def openapi_route() -> tuple[Response, int] | Response:
    return jsonify(_OPENAPI), 200


# -------------------- Core CRUD / list / search --------------------


@blueprint.route("/artifact/<string:artifact_type>", methods=["POST"])
@_record_timing
def create_artifact(artifact_type: str) -> tuple[Response, int] | Response:
    """Register a new artifact from ArtifactData {"url": "..."}; returns Artifact.

    Per spec, request body contains only ArtifactData with a single url.
    """
    _require_auth()
    payload = _json_body()
    # Validate/normalize data according to artifact_type; supports {"url": "..."}
    data = _validate_artifact_data(artifact_type, payload)

    # Derive basic metadata (name from URL if possible, generated id)
    url = (payload or {}).get("url") if isinstance(payload, dict) else None
    name_guess = "example"
    try:
        if isinstance(url, str) and url.strip():
            # Use last path segment as name
            name_guess = url.rstrip("/").split("/")[-1] or name_guess
    except Exception:
        pass
    metadata = ArtifactMetadata(
        id=str(int(time.time() * 1000)),
        name=name_guess,
        type=artifact_type,
        version="1.0.0",
    )
    artifact = save_artifact(Artifact(metadata=metadata, data=data))
    # Return Artifact at root (not wrapped)
    return jsonify(artifact_to_dict(artifact)), 201


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    artifact = fetch_artifact(artifact_type, artifact_id)
    if artifact is None:
        return jsonify({"message": "Artifact not found"}), 404
    # Return Artifact at root to match spec
    return jsonify(artifact_to_dict(artifact)), 200


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["PUT"])
@_record_timing
def update_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    payload = _json_body()
    metadata_dict = payload.get("metadata") or {}
    data = _validate_artifact_data(artifact_type, payload.get("data") or {})
    metadata = ArtifactMetadata(
        id=artifact_id,
        name=str(metadata_dict.get("name", "example")),
        type=artifact_type,
        version=str(metadata_dict.get("version", "1.0.1")),
    )
    artifact = save_artifact(Artifact(metadata=metadata, data=data))
    # Return Artifact at root to match spec
    return jsonify(artifact_to_dict(artifact)), 200


# Non-baseline: Delete an artifact (implemented for convenience)
@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["DELETE"])
@_record_timing
def delete_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    # Delete from primary store and in-memory
    try:
        ArtifactStore().delete(artifact_type, artifact_id)
    except Exception:
        logger.exception("Primary delete failed; will still remove from memory if present")
    _STORE.pop(_store_key(artifact_type, artifact_id), None)
    return jsonify({"message": "Artifact deleted"}), 200


@blueprint.route("/artifacts", methods=["POST"])
@_record_timing
def enumerate_artifacts_route() -> tuple[Response, int] | Response:
    """Enumerate artifacts matching ArtifactQuery; returns list w/ offset header for pagination.
    OpenAPI spec expects an array of ArtifactQuery objects with optional offset parameter.
    """
    _require_auth()
    payload = _json_body()

    # Support both single query object and array of queries (OpenAPI spec uses array)
    if isinstance(payload, list):
        # OpenAPI spec format: array of queries
        # For simplicity, use the first query if multiple provided
        if not payload:
            return jsonify({"message": "Query array cannot be empty"}), 400
        query_dict = payload[0]
    else:
        # Legacy format: single query object
        query_dict = payload
    # Parse offset from query args if provided
    offset_str = request.args.get("offset")
    if offset_str:
        try:
            offset = int(offset_str)
            # Convert offset to page number
            page_size = query_dict.get("page_size", 25)
            query_dict["page"] = (offset // page_size) + 1 if page_size > 0 else 1
        except (ValueError, TypeError):
            pass
    query = _parse_query(query_dict)
    result = list_artifacts(query)

    # If query requests everything by name "*" and total is very large, indicate too many results
    if (str(query_dict.get("name", "")).strip() == "*") and result.get("total", 0) > 500:
        return jsonify({"message": "Too many artifacts returned"}), 413

    # Calculate offset for next page (OpenAPI spec requirement)
    current_page = int(result.get("page", 1))
    page_size = int(result.get("page_size", 25))
    total = int(result.get("total", 0))
    next_offset = current_page * page_size

    # Spec expects array of ArtifactMetadata
    items = result.get("items", [])
    artifacts_meta = [
        {
            "name": (it.get("metadata") or {}).get("name"),
            "id": (it.get("metadata") or {}).get("id"),
            "type": (it.get("metadata") or {}).get("type"),
        }
        for it in items
    ]

    response = jsonify(artifacts_meta)
    if next_offset < total:
        response.headers["offset"] = str(next_offset)
    return response, 200


@blueprint.route("/directory", methods=["GET"])
@_record_timing
def directory_route() -> tuple[Response, int] | Response:
    _require_auth()
    query = _parse_query_args(request.args)
    result = list_artifacts(query)
    return jsonify(result), 200


@blueprint.route("/search", methods=["GET"])
@_record_timing
def search_route() -> tuple[Response, int] | Response:
    _require_auth()
    raw_query = request.args.get("q", "")
    if not raw_query.strip():
        return jsonify({"message": "Missing search query"}), 400
    mode = request.args.get("mode", "substring").lower()
    if mode not in {"regex", "prefix", "substring"}:
        mode = "substring"
    version_spec = request.args.get("version_spec")

    query = _parse_query_args(request.args)
    pattern = None
    sanitized = None
    if mode == "regex":
        sanitized = _sanitize_search_pattern(raw_query)
        try:
            pattern = re.compile(sanitized, re.IGNORECASE)
        except re.error:
            return jsonify({"message": "Invalid search pattern"}), 400

    matches = _search_artifacts(pattern, query.artifact_type, mode, raw_query)
    if version_spec:
        matches = [a for a in matches if _in_version_range(a.metadata.version, version_spec)]
    result = _paginate_artifacts(matches, query.page, query.page_size)
    if sanitized is not None:
        result["pattern"] = sanitized
    result["mode"] = mode
    result["q"] = raw_query
    if version_spec:
        result["version_spec"] = version_spec
    return jsonify(result), 200


# -------------------- Upload --------------------


@blueprint.route("/upload", methods=["GET"])
@_record_timing
def upload_list_route() -> tuple[Response, int] | Response:
    _require_auth()
    files = []
    for p in sorted(_UPLOAD_DIR.glob("**/*")):
        if p.is_file():
            files.append(
                {
                    "name": p.name,
                    "path": str(p.relative_to(_UPLOAD_DIR.parent)),
                    "size": p.stat().st_size,
                }
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

    safe_name = secure_filename(f.filename)
    if not safe_name:
        return jsonify({"message": "Invalid filename"}), 400

    artifact_name = request.form.get("name", safe_name)
    artifact_type = request.form.get("artifact_type", "file")
    artifact_id = request.form.get("id", safe_name)

    data: dict[str, Any]
    # If S3 is enabled, upload directly to S3; else save to /tmp/uploads
    if _S3.enabled:
        key_rel = f"{artifact_type}/{artifact_id}/{safe_name}"
        try:
            # Use stream without loading full file in memory when possible
            meta = _S3.put_file(
                cast(BinaryIO, f.stream), key_rel, f.mimetype or "application/octet-stream"
            )
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
            # Fall back to local disk
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
        metadata=ArtifactMetadata(
            id=artifact_id,
            name=artifact_name,
            type=artifact_type,
            version="1.0.0",
        ),
        data=data,
    )
    save_artifact(art)
    return jsonify({"artifact": artifact_to_dict(art)}), 201


# -------------------- Rating --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/rate", methods=["GET"])
@_record_timing
def rate_model_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    if artifact_id in _RATINGS_CACHE:
        rating = _RATINGS_CACHE[artifact_id]
        # Return in OpenAPI 3.3.1 compatible flattened structure
        return jsonify(_to_openapi_model_rating(rating)), 200
    artifact = fetch_artifact("model", artifact_id)
    if artifact is None:
        return jsonify({"message": "Artifact not found"}), 404
    try:
        rating = _score_artifact_with_metrics(artifact)
        _RATINGS_CACHE[artifact_id] = rating

        # Persist metrics and scores back to the artifact
        if isinstance(artifact.data, dict):
            artifact.data["metrics"] = rating.scores
            artifact.data["trust_score"] = rating.scores.get("net_score", 0.0)
            artifact.data["last_rated"] = rating.generated_at.isoformat() + "Z"
            save_artifact(artifact)
            logger.info(
                f"Saved metrics for {artifact_id}: trust_score={artifact.data[
                    'trust_score']}"
            )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception:
        logger.exception("Failed to score artifact %s", artifact_id)
        return jsonify({"message": "Failed to compute model rating"}), 500
    return jsonify(_to_openapi_model_rating(rating)), 200


def _to_openapi_model_rating(rating: ModelRating) -> dict[str, Any]:
    """Convert internal ModelRating to the flattened schema required by the spec."""
    scores = rating.scores or {}
    lat_ms = rating.latencies or {}
    # Convert milliseconds to seconds (float)

    def sec(key: str) -> float:
        v = lat_ms.get(key, 0)
        try:
            return float(v) / 1000.0
        except Exception:
            return 0.0

    # size_score is an object
    size_score = scores.get("size_score") or {
        "raspberry_pi": 0.0,
        "jetson_nano": 0.0,
        "desktop_pc": 0.0,
        "aws_server": 0.0,
    }

    return {
        "name": rating.summary.get("name"),
        "category": rating.summary.get("category"),
        "net_score": float(scores.get("net_score", 0.0) or 0.0),
        "net_score_latency": sec("net_score"),
        "ramp_up_time": float(scores.get("ramp_up_time", 0.0) or 0.0),
        "ramp_up_time_latency": sec("ramp_up_time"),
        "bus_factor": float(scores.get("bus_factor", 0.0) or 0.0),
        "bus_factor_latency": sec("bus_factor"),
        "performance_claims": float(scores.get("performance_claims", 0.0) or 0.0),
        "performance_claims_latency": sec("performance_claims"),
        "license": float(scores.get("license", 0.0) or 0.0),
        "license_latency": sec("license"),
        "dataset_and_code_score": float(scores.get("dataset_and_code_score", 0.0) or 0.0),
        "dataset_and_code_score_latency": sec("dataset_and_code_score"),
        "dataset_quality": float(scores.get("dataset_quality", 0.0) or 0.0),
        "dataset_quality_latency": sec("dataset_quality"),
        "code_quality": float(scores.get("code_quality", 0.0) or 0.0),
        "code_quality_latency": sec("code_quality"),
        "reproducibility": float(scores.get("reproducibility", 0.0) or 0.0),
        "reproducibility_latency": sec("reproducibility"),
        "reviewedness": float(scores.get("reviewedness", 0.0) or 0.0),
        "reviewedness_latency": sec("reviewedness"),
        "tree_score": float(scores.get("tree_score", 0.0) or 0.0),
        "tree_score_latency": sec("tree_score"),
        "size_score": size_score,
        "size_score_latency": sec("size_score"),
    }


# -------------------- Download (full/parts) & size cost --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/download", methods=["GET"])
@_record_timing
def download_model_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    part = request.args.get("part", "all")  # all|weights|dataset
    art = fetch_artifact("model", artifact_id)
    if art is None:
        return jsonify({"message": "Artifact not found"}), 404
    # Prefer S3 if present in artifact metadata
    if isinstance(art.data, dict) and _S3.enabled:
        s3_key = art.data.get("s3_key")
        s3_bucket = art.data.get("s3_bucket")
        if isinstance(s3_key, str) and s3_bucket:
            key = s3_key
            ver = art.data.get("s3_version_id")
            try:
                if part == "all":
                    # Stream original object (assumed zip) to client
                    body, meta = _S3.get_object(key, ver)
                    resp = send_file(
                        io.BytesIO(body),
                        as_attachment=True,
                        download_name=f"{artifact_id}.zip",
                        mimetype=meta.get("content_type") or "application/zip",
                    )
                    resp.headers["X-Size-Cost-Bytes"] = str(int(meta.get("size", len(body))))
                    return resp
                    # For parts, load zip into memory and filter
                    body, meta = _S3.get_object(key, ver)
                    size_bytes = int(meta.get("size", len(body)))
                    with zipfile.ZipFile(io.BytesIO(body), "r") as zin:
                        buf = io.BytesIO()
                        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                            prefix = f"{part.strip('/')}/"
                            for info in zin.infolist():
                                if info.filename.startswith(prefix):
                                    zout.writestr(info, zin.read(info))
                        buf.seek(0)
                    resp = send_file(
                        buf,
                        as_attachment=True,
                        download_name=f"{artifact_id}-{part}.zip",
                        mimetype="application/zip",
                    )
                    resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
                    return resp
            except Exception:
                logger.exception("Failed to serve from S3; falling back to local if available")

    # Fallback to local disk
    rel = art.data.get("path")
    if not isinstance(rel, str) or not rel:
        return jsonify({"message": "Model has no stored package path"}), 400
    zpath = (_UPLOAD_DIR.parent / rel).resolve()
    if not zpath.exists():
        return jsonify({"message": "Package not found on disk"}), 404

    size_bytes = zpath.stat().st_size

    if part == "all":
        resp = send_file(
            str(zpath),
            as_attachment=True,
            download_name=zpath.name,
            etag=True,
            mimetype="application/zip",
        )
        resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
        return resp

    # Build a filtered zip in-memory for weights/ or dataset/
    with zipfile.ZipFile(str(zpath), "r") as zin:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            prefix = f"{part.strip('/')}/"
            for info in zin.infolist():
                if info.filename.startswith(prefix):
                    zout.writestr(info, zin.read(info))
        buf.seek(0)

    resp = send_file(
        buf,
        as_attachment=True,
        download_name=f"{artifact_id}-{part}.zip",
        mimetype="application/zip",
    )
    resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
    return resp


@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>/cost", methods=["GET"])
@_record_timing
def artifact_cost_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    """Calculate storage cost for artifact in MB. Supports ?dependency=true for recursive cost."""
    _require_auth()
    dependency = request.args.get("dependency", "false").lower() == "true"

    art = fetch_artifact(artifact_type, artifact_id)
    if art is None:
        return jsonify({"message": "Artifact not found"}), 404
    try:
        # Calculate standalone cost for this artifact
        standalone_cost_mb = _calculate_artifact_size_mb(art)

        if not dependency:
            # Simple case: just return total_cost
            return jsonify({artifact_id: {"total_cost": round(standalone_cost_mb, 2)}}), 200
        # Complex case: calculate costs for all dependencies
        visited: set[str] = set()
        cost_map: dict[str, dict[str, float]] = {}

        def _collect_costs(current_art, current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            # Calculate standalone cost
            size_mb = _calculate_artifact_size_mb(current_art)
            cost_map[current_id] = {
                "standalone_cost": round(size_mb, 2),
                "total_cost": round(size_mb, 2),  # Will update after traversal
            }
            # Find dependencies (look for references in data)
            if isinstance(current_art.data, dict):
                for key in ("code_link", "dataset_link", "base_model_id", "dependencies"):
                    dep_val = current_art.data.get(key)
                    if isinstance(dep_val, str) and dep_val.strip():
                        # Try to resolve as artifact_id
                        dep_art = fetch_artifact(artifact_type, dep_val)
                        if dep_art:
                            _collect_costs(dep_art, dep_val)
                    elif isinstance(dep_val, list):
                        for dep_id in dep_val:
                            if isinstance(dep_id, str):
                                dep_art = fetch_artifact(artifact_type, dep_id)
                                if dep_art:
                                    _collect_costs(dep_art, dep_id)

        # Traverse dependency tree
        _collect_costs(art, artifact_id)
        # Calculate total costs (sum all dependencies)
        total_sum = sum(c["standalone_cost"] for c in cost_map.values())
        for aid in cost_map:
            cost_map[aid]["total_cost"] = round(total_sum, 2)
        return jsonify(cost_map), 200
    except Exception:
        logger.exception("Failed to calculate artifact cost for %s", artifact_id)
        return jsonify({"message": "The artifact cost calculator encountered an error"}), 500


# -------------------- License check (per-spec endpoint) --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/license-check", methods=["POST"])
@_record_timing
def model_license_check_route(artifact_id: str) -> tuple[Response, int] | Response:
    """Assess license compatibility for fine-tune and inference usage.

    Spec expects boolean response. Return True for now (stub).
    """
    _require_auth()
    # Validate body contains github_url
    body = _json_body()
    gh_url = str(body.get("github_url", "")).strip()
    if not gh_url:
        return jsonify({"message": "github_url is required"}), 400
    # TODO: integrate license analysis; for now, optimistic stub
    return jsonify(True), 200


def _calculate_artifact_size_mb(artifact) -> float:
    """Calculate artifact size in MB from S3 metadata or local file."""
    size_bytes = 0
    # Try S3 metadata first
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
        # Fallback to local file
        if size_bytes == 0 and artifact.data.get("path"):
            rel = artifact.data.get("path")
            if isinstance(rel, str) and rel:
                zpath = (_UPLOAD_DIR.parent / rel).resolve()
                if zpath.exists():
                    size_bytes = zpath.stat().st_size
    # Convert bytes to MB
    return size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0


# -------------------- HF ingest gate --------------------
@blueprint.route("/ingest", methods=["POST"])
def ingest_route() -> tuple[Response, int] | Response:
    """Ingest a model artifact into the registry."""
    _require_auth()
    payload = _json_body()
    artifact_type = str(payload.get("artifact_type", "model")).lower()
    metadata = payload.get("metadata") or {}
    data = payload.get("data") or {}

    # Validate & normalize
    normalized = _validate_artifact_data(artifact_type, data)
    artifact = Artifact(
        metadata=ArtifactMetadata(
            id=str(metadata.get("id", "generated-id")),
            name=str(metadata.get("name", "example")),
            type=artifact_type,
            version=str(metadata.get("version", "1.0.0")),
        ),
        data=normalized,
    )

    save_artifact(artifact)
    return jsonify({"artifact": artifact_to_dict(artifact)}), 201


@blueprint.route("/ingest/hf", methods=["POST"])
@_record_timing
def ingest_hf_route() -> tuple[Response, int] | Response:
    _require_auth()
    payload = _json_body()
    hf_id = str(payload.get("hf_model_id", "")).strip()
    if not hf_id:
        return jsonify({"message": "Missing hf_model_id"}), 400

    temp = Artifact(
        metadata=ArtifactMetadata(id=hf_id, name=hf_id, type="model", version="0.0.0"),
        data={"model_link": f"https://huggingface.co/{hf_id}"},
    )
    try:
        rating = _score_artifact_with_metrics(temp)
    except Exception as e:
        logger.exception("HF score failed")
        return jsonify({"message": f"Failed to score model: {e}"}), 502

    non_latency = [
        "bus_factor",
        "code_quality",
        "dataset_quality",
        "dataset_and_code_score",
        "license",
        "performance_claims",
        "ramp_up_time",
    ]
    failures = {
        k: rating.scores.get(k, 0.0)
        for k in non_latency
        if (rating.scores.get(k, 0.0) or 0.0) < 0.5
    }
    if failures:
        return jsonify({"ingestible": False, "scores": rating.scores, "failures": failures}), 200

    art = Artifact(
        metadata=ArtifactMetadata(
            id=hf_id.replace("/", "_"),
            name=hf_id,
            type="model",
            version="1.0.0",
        ),
        data={
            "model_link": f"https://huggingface.co/{hf_id}",
            "path": f"uploads/{hf_id.replace('/', '_')}.zip",
        },
    )
    save_artifact(art)
    return (
        jsonify({"ingestible": True, "artifact": artifact_to_dict(art), "scores": rating.scores}),
        201,
    )


# -------------------- Authentication (per-spec) --------------------


@blueprint.route("/authenticate", methods=["PUT"])
def authenticate_route() -> tuple[Response, int] | Response:
    """Create an access token per spec.

    Accepts {"user": {"name": ... , "is_admin": bool}, "secret": {"password": ...}}
    Returns AuthenticationToken string, including the 'bearer ' prefix.
    """
    body = _json_body()
    user = (body.get("user") or {}) if isinstance(body, dict) else {}
    secret = (body.get("secret") or {}) if isinstance(body, dict) else {}
    username = str(user.get("name", "")).strip()
    password = str(secret.get("password", "")).strip()
    if username == _DEFAULT_USER["username"] and password == _DEFAULT_USER["password"]:
        tok = f"t_{int(time.time()*1000)}"
        _TOKENS.add(tok)
        TokenStore().add(tok)
        return jsonify(f"bearer {tok}"), 200
    return jsonify({"message": "invalid credentials"}), 401


# -------------------- Lineage graph --------------------


@blueprint.route("/artifact/model/<string:artifact_id>/lineage", methods=["GET"])
@_record_timing
def lineage_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    art = fetch_artifact("model", artifact_id)
    if not art:
        return jsonify({"message": "Artifact not found"}), 404
    # Support S3-backed blobs
    s3_key = art.data.get("s3_key") if isinstance(art.data, dict) else None
    s3_ver = art.data.get("s3_version_id") if isinstance(art.data, dict) else None
    zbody: bytes | None = None
    if s3_key and _S3.enabled:
        try:
            zbody, _meta = _S3.get_object(s3_key, s3_ver)
        except Exception:
            logger.exception("Failed to fetch S3 object for lineage")
            zbody = None
    if zbody is None:
        rel = art.data.get("path")
        if not rel:
            return jsonify({"message": "No package path"}), 400
        zpath = (_UPLOAD_DIR.parent / rel).resolve()
        if not zpath.exists():
            return jsonify({"message": "Package not found"}), 404

    parents: list[str] = []
    try:
        zf_ctx = (
            zipfile.ZipFile(io.BytesIO(zbody), "r")
            if zbody is not None
            else zipfile.ZipFile(str(zpath), "r")
        )
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
    # Build objects per spec
    nodes = [
        {
            "artifact_id": artifact_id,
            "name": art.metadata.name,
            "source": "config_json",
        }
    ]
    for p in parents:
        nodes.append(
            {
                "artifact_id": p,
                "name": p,
                "source": "config_json",
            }
        )
    edges = [
        {
            "from_node_artifact_id": p,
            "to_node_artifact_id": artifact_id,
            "relationship": "derived_from",
        }
        for p in parents
    ]
    return jsonify({"nodes": nodes, "edges": edges}), 200


# -------------------- License compatibility (stubbed API) --------------------


@blueprint.route("/license/check", methods=["POST"])
@_record_timing
def license_check_route() -> tuple[Response, int] | Response:
    """Legacy license check endpoint; returns structured result for compatibility."""
    _require_auth()
    body = _json_body()
    gh_url = str(body.get("github_url", "")).strip()
    model_id = str(body.get("model_id", "")).strip()
    if not gh_url or not model_id:
        return jsonify({"message": "github_url and model_id required"}), 400

    result = {
        "github_url": gh_url,
        "model_id": model_id,
        "compatible": True,  # placeholder
        "reason": "Stub: implement ModelGo-like policy check",
        "details": {"repo_license": "MIT", "model_license": "Apache-2.0"},
    }
    return jsonify({"result": result}), 200


# -------------------- Reset --------------------


@blueprint.route("/reset", methods=["DELETE"])
def reset_route() -> tuple[Response, int] | Response:
    _require_auth(admin=True)
    scope = str(request.args.get("scope", "memory")).lower()
    reset_storage()

    # Optional hard reset: clear DynamoDB-backed stores as well
    if scope in {"all", "db", "dynamodb"}:
        try:
            ArtifactStore().clear()
        except Exception:
            logger.exception("Failed to clear ArtifactStore (DynamoDB)")
        try:
            TokenStore().clear()
        except Exception:
            logger.exception("Failed to clear TokenStore (DynamoDB)")
        try:
            RatingsCache().clear()
        except Exception:
            logger.exception("Failed to clear RatingsCache (DynamoDB)")

    return jsonify({"message": "Registry reset successful", "scope": scope}), 200


# -------------------- Name and RegEx lookups (per-spec) --------------------


@blueprint.route("/artifact/byName/<string:name>", methods=["GET"])
@_record_timing
def by_name_route(name: str) -> tuple[Response, int] | Response:
    _require_auth()
    needle = name.strip().lower()
    results = []
    for art in _STORE.values():
        if art.metadata.name.lower() == needle:
            results.append(
                {
                    "name": art.metadata.name,
                    "id": art.metadata.id,
                    "type": art.metadata.type,
                }
            )
    if not results:
        return jsonify({"message": "No such artifact"}), 404
    return jsonify(results), 200


@blueprint.route("/artifact/byRegEx", methods=["POST"])
@_record_timing
def by_regex_route() -> tuple[Response, int] | Response:
    _require_auth()
    body = _json_body()
    regex = str(body.get("regex", "")).strip()
    if not regex:
        return jsonify({"message": "Missing regex"}), 400
    try:
        sanitized = _sanitize_search_pattern(regex)
        pattern = re.compile(sanitized, re.IGNORECASE)
    except re.error:
        return jsonify({"message": "Invalid regex"}), 400
    matches = []
    for art in _STORE.values():
        if pattern.search(art.metadata.name) or (
            isinstance(art.data, dict) and pattern.search(str(art.data.get("readme", "")))
        ):
            matches.append(
                {
                    "name": art.metadata.name,
                    "id": art.metadata.id,
                    "type": art.metadata.type,
                }
            )
    if not matches:
        return jsonify({"message": "No artifact found under this regex"}), 404
    return jsonify(matches), 200
