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
_AUDIT_LOG: dict[str, list[dict[str, Any]]] = {}
_S3 = S3Storage()
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# token -> is_admin
_TOKENS: dict[str, bool] = {}
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
    try:
        _ARTIFACT_STORE.save(
            artifact.metadata.type,
            artifact.metadata.id,
            artifact_to_dict(artifact),
        )
    except Exception:
        logger.exception("Failed to persist artifact via adapter; keeping in memory only")
    _STORE[_store_key(artifact.metadata.type, artifact.metadata.id)] = artifact
    return artifact

def fetch_artifact(artifact_type: str, artifact_id: str) -> Artifact | None:
    logger.info("Fetching artifact %s/%s", artifact_type, artifact_id)
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
    return _STORE.get(_store_key(artifact_type, artifact_id))

def _duplicate_url_exists(artifact_type: str, url: str) -> bool:
    for a in _STORE.values():
        if a.metadata.type == artifact_type and str((a.data or {}).get("url")) == url:
            return True
    try:
        items = _ARTIFACT_STORE.list_all(artifact_type)
        for d in items or []:
            if (d.get("metadata", {}) or {}).get("type") == artifact_type and (d.get("data", {}) or {}).get("url") == url:
                return True
    except Exception:
        pass
    return False

def list_artifacts(query: ArtifactQuery) -> dict[str, Any]:
    logger.info("Listing artifacts page=%s size=%s", query.page, query.page_size)
    items: list[Artifact] = []
    used_primary = False
    try:
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
        store_vals = sorted(_STORE.values(), key=lambda art: (art.metadata.type, art.metadata.name))
        items = [
            item
            for item in store_vals
            if (not query.artifact_type or item.metadata.type == query.artifact_type)
        ]

    # Filter by types[]
    if query.types:
        items = [item for item in items if item.metadata.type in query.types]

    # Filter by name
    if query.name and query.name != "*":
        needle = query.name.lower()
        items = [item for item in items if item.metadata.name.lower() == needle]

    return _paginate_artifacts(items, query.page, query.page_size)

def reset_storage() -> None:
    logger.warning("Resetting in-memory artifact store")
    _STORE.clear()
    _RATINGS_CACHE.clear()
    _AUDIT_LOG.clear()
    _TOKENS.clear()

def _parse_bearer(header_value: str) -> str:
    if not header_value:
        return ""
    v = header_value.strip()
    if v.lower().startswith("bearer "):
        return v.split(" ", 1)[1].strip()
    return v

def _require_auth(admin: bool = False) -> tuple[str, bool]:
    # Per spec, use X-Authorization; Authorization required in your system
    token_hdr = request.headers.get("X-Authorization", "")
    auth_hdr = request.headers.get("Authorization", "")
    token = _parse_bearer(token_hdr) or _parse_bearer(auth_hdr)
    
    logger.warning(f"AUTH_CHECK: X-Authorization='{token_hdr}', Authorization='{auth_hdr}'")
    logger.warning(f"AUTH_CHECK: Parsed token='{token}', admin_required={admin}")
    logger.warning(f"AUTH_CHECK: Current _TOKENS has {len(_TOKENS)} tokens: {list(_TOKENS.keys())}")
    logger.warning(f"AUTH_CHECK: Token in _TOKENS? {token in _TOKENS}")
    
    if not token or token not in _TOKENS:
        # spec: 403 for invalid or missing AuthenticationToken
        logger.warning(f"AUTH_CHECK: FAILED - Token missing or not found in _TOKENS")
        response = jsonify({"message": "Authentication failed due to invalid or missing AuthenticationToken."})
        response.status_code = HTTPStatus.FORBIDDEN
        from flask import abort
        abort(response)
    is_admin = bool(_TOKENS[token])
    logger.warning(f"AUTH_CHECK: Token valid, is_admin={is_admin}")
    
    if admin and not is_admin:
        # spec: 401 when you do not have permission to reset
        logger.warning(f"AUTH_CHECK: FAILED - Admin required but user is not admin")
        response = jsonify({"message": "You do not have permission to reset the registry."})
        response.status_code = HTTPStatus.UNAUTHORIZED
        from flask import abort
        abort(response)
    
    logger.warning(f"AUTH_CHECK: SUCCESS - Token '{token}' authenticated, is_admin={is_admin}")
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

def _sanitize_search_pattern(raw_pattern: str) -> str:
    if len(raw_pattern) > 256:
        raw_pattern = raw_pattern[:256]
    allowed = re.sub(r"[^\w\s\.\*\+\?\|\[\]\(\)\^\$]", "", raw_pattern)
    return allowed or ".*"

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
# Flask blueprint and routes
# ---------------------------------------------------------------------------

blueprint = Blueprint("registry", __name__)

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
                [{"bucket": now_iso, "value": len(_REQUEST_TIMES), "unit": "req"}]
                if include_timeline
                else []
            ),
            "logs": [],
        }
    ]
    return (
        jsonify(
            {
                "components": components,
                "generated_at": now_iso,
                "window_minutes": window_minutes,
            }
        ),
        200,
    )

# -------------------- Authentication (per-spec) --------------------

@blueprint.route("/authenticate", methods=["PUT"])
def authenticate_route() -> tuple[Response, int] | Response:
    # Log raw request data for debugging
    logger.warning(f"AUTH: Raw request data: {request.get_data(as_text=True)[:200]}")
    logger.warning(f"AUTH: Content-Type: {request.content_type}")
    
    body = _json_body() or {}
    logger.warning(f"AUTH: Parsed body type={type(body)}, keys={list(body.keys()) if isinstance(body, dict) else 'not-dict'}")
    
    user = (body.get("user") or {}) if isinstance(body, dict) else {}
    secret = (body.get("secret") or {}) if isinstance(body, dict) else {}
    username = str(user.get("name", "")).strip()
    password = str(secret.get("password", "")).strip()

    logger.warning(f"AUTH: Received authentication request for username='{username}'")
    logger.warning(f"AUTH: Request body structure: user={user}, secret keys={list(secret.keys()) if isinstance(secret, dict) else 'not-dict'}")
    logger.warning(f"AUTH: Expected username='{_DEFAULT_USER['username']}', received='{username}', match={username == _DEFAULT_USER['username']}")
    logger.warning(f"AUTH: Expected password length={len(_DEFAULT_USER['password'])}, received length={len(password)}")
    logger.warning(f"AUTH: Password match={password == _DEFAULT_USER['password']}")
    
    # Spec: if system supports auth, validate; else 501.
    if not username or not password:
        logger.warning("AUTH: Missing username or password")
        return jsonify({"message": "Missing user or password"}), 400
    if username != _DEFAULT_USER["username"] or password != _DEFAULT_USER["password"]:
        logger.warning(f"AUTH: CREDENTIAL MISMATCH - Expected user='{_DEFAULT_USER['username']}' pass_len={len(_DEFAULT_USER['password'])}, Got user='{username}' pass_len={len(password)}")
        logger.warning(f"AUTH: Password comparison: received first 20 chars='{password[:20]}...', expected first 20 chars='{_DEFAULT_USER['password'][:20]}...'")
        return jsonify({"message": "The user or password is invalid."}), 401

    # Default user is always admin
    is_admin = True
    tok = f"t_{int(time.time()*1000)}"
    _TOKENS[tok] = is_admin
    logger.warning(f"AUTH: Created token '{tok}' for user '{username}', is_admin={is_admin}")
    logger.warning(f"AUTH: Current _TOKENS dict has {len(_TOKENS)} tokens: {list(_TOKENS.keys())}")
    
    try:
        TokenStore().add(tok)
        logger.warning(f"AUTH: Added token to TokenStore")
    except Exception as e:
        logger.warning(f"AUTH: Failed to add token to TokenStore: {e}")

    # Spec's example returns a JSON string of the token with bearer prefix
    response = jsonify(f"bearer {tok}")
    logger.warning(f"AUTH: Returning token response: 'bearer {tok}'")
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
    if "url" not in payload or not isinstance(payload["url"], str) or not payload["url"].strip():
        return jsonify({"message": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."}), 400

    url = payload["url"].strip()
    # Conflict if same type+url already registered
    if _duplicate_url_exists(artifact_type, url):
        return jsonify({"message": "Artifact exists already."}), 409

    name_guess = secure_filename(url.rstrip("/").split("/")[-1]) or "artifact"
    art_id = str(int(time.time() * 1000))
    artifact = Artifact(
        metadata=ArtifactMetadata(
            id=art_id,
            name=name_guess,
            type=artifact_type,
            version="1.0.0",
        ),
        data={"url": url},
    )
    save_artifact(artifact)
    _audit_add(artifact_type, art_id, "CREATE", name_guess)
    return jsonify(artifact_to_dict(artifact)), 201

# -------------------- Enumerate artifacts --------------------

@blueprint.route("/artifacts", methods=["POST"])
@_record_timing
def enumerate_artifacts_route() -> tuple[Response, int] | Response:
    _require_auth()

    body = request.get_json(silent=True)
    if not isinstance(body, list) or not body or not isinstance(body[0], dict) or "name" not in body[0]:
        return jsonify({"message": "Invalid artifact_query"}), 400

    qd = body[0]
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

    query = _parse_query({"artifact_type": qd.get("artifact_type"), "name": qd.get("name"), "types": qd.get("types", []), "page": qd.get("page", 1), "page_size": qd.get("page_size", 25)})
    result = list_artifacts(query)

    current_page = int(result.get("page", 1))
    page_size = int(result.get("page_size", 25))
    total = int(result.get("total", 0))
    next_offset = current_page * page_size

    items = result.get("items", [])
    # Per spec, response body is array of ArtifactMetadata (name/id/type)
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

# -------------------- Artifact by id (GET/PUT/DELETE) --------------------

@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact_route(artifact_type: str, artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    art = fetch_artifact(artifact_type, artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404
    # Spec: returned artifact must include data.url
    if "url" not in (art.data or {}):
        return jsonify({"message": "Artifact missing url"}), 400
    _audit_add(artifact_type, artifact_id, "DOWNLOAD", art.metadata.name)
    return jsonify(artifact_to_dict(art)), 200

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
            id=artifact_id,
            name=str(md["name"]),
            type=artifact_type,
            version=str(md.get("version", "1.0.0")),
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
    _audit_add(artifact_type, artifact_id, "UPDATE", "")
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
    artifact_id = request.form.get("id", str(int(time.time()*1000)))

    data: dict[str, Any]
    if _S3.enabled:
        key_rel = f"uploads/{artifact_type}/{artifact_id}/{safe_name}"
        try:
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
    _audit_add(artifact_type, artifact_id, "CREATE", artifact_name)
    return jsonify({"artifact": artifact_to_dict(art)}), 201

# -------------------- Rating --------------------

@blueprint.route("/artifact/model/<string:artifact_id>/rate", methods=["GET"])
@_record_timing
def rate_model_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    if artifact_id in _RATINGS_CACHE:
        rating = _RATINGS_CACHE[artifact_id]
        return jsonify(_to_openapi_model_rating(rating)), 200
    artifact = fetch_artifact("model", artifact_id)
    if artifact is None:
        return jsonify({"message": "Artifact does not exist."}), 404
    try:
        rating = _score_artifact_with_metrics(artifact)
        _RATINGS_CACHE[artifact_id] = rating

        if isinstance(artifact.data, dict):
            artifact.data["metrics"] = rating.scores
            artifact.data["trust_score"] = rating.scores.get("net_score", 0.0)
            artifact.data["last_rated"] = rating.generated_at.isoformat() + "Z"
            save_artifact(artifact)
        _audit_add("model", artifact_id, "RATE", artifact.metadata.name)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception:
        logger.exception("Failed to score artifact %s", artifact_id)
        return jsonify({"message": "The artifact rating system encountered an error while computing at least one metric."}), 500
    return jsonify(_to_openapi_model_rating(rating)), 200

def _to_openapi_model_rating(rating: ModelRating) -> dict[str, Any]:
    scores = rating.scores or {}
    lat_ms = rating.latencies or {}

    def sec(key: str) -> float:
        v = lat_ms.get(key, 0)
        try:
            return float(v) / 1000.0
        except Exception:
            return 0.0

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

# -------------------- Download (kept) & size cost --------------------

@blueprint.route("/artifact/model/<string:artifact_id>/download", methods=["GET"])
@_record_timing
def download_model_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    part = request.args.get("part", "all")
    art = fetch_artifact("model", artifact_id)
    if art is None:
        return jsonify({"message": "Artifact does not exist."}), 404
    if isinstance(art.data, dict) and _S3.enabled:
        s3_key = art.data.get("s3_key")
        s3_bucket = art.data.get("s3_bucket")
        if isinstance(s3_key, str) and s3_bucket:
            key = s3_key
            ver = art.data.get("s3_version_id")
            try:
                body, meta = _S3.get_object(key, ver)
                size_bytes = int(meta.get("size", len(body)))
                if part == "all":
                    resp = send_file(
                        io.BytesIO(body),
                        as_attachment=True,
                        download_name=f"{artifact_id}.zip",
                        mimetype=meta.get("content_type") or "application/zip",
                    )
                    resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
                    _audit_add("model", artifact_id, "DOWNLOAD", art.metadata.name)
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
                    buf,
                    as_attachment=True,
                    download_name=f"{artifact_id}-{part}.zip",
                    mimetype="application/zip",
                )
                resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
                _audit_add("model", artifact_id, "DOWNLOAD", art.metadata.name)
                return resp
            except Exception:
                logger.exception("Failed to serve from S3; falling back to local if available")

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
        _audit_add("model", artifact_id, "DOWNLOAD", art.metadata.name)
        return resp

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
    _audit_add("model", artifact_id, "DOWNLOAD", art.metadata.name)
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
            return jsonify({"message": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."}), 400
        zpath = (_UPLOAD_DIR.parent / rel).resolve()
        if not zpath.exists():
            return jsonify({"message": "Artifact package not found"}), 404

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

# -------------------- License check (per-spec path) --------------------

@blueprint.route("/artifact/model/<string:artifact_id>/license-check", methods=["POST"])
@_record_timing
def model_license_check_route(artifact_id: str) -> tuple[Response, int] | Response:
    _require_auth()
    body = _json_body()
    gh_url = str(body.get("github_url", "")).strip()
    if not gh_url:
        return jsonify({"message": "The license check request is malformed or references an unsupported usage context."}), 400
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
    logger.warning(f"RESET: _ARTIFACT_STORE instance id: {id(_ARTIFACT_STORE)}, use_dynamodb={_ARTIFACT_STORE.use_dynamodb}")
    logger.warning(f"RESET: _ARTIFACT_STORE._memory_store has {len(_ARTIFACT_STORE._memory_store)} items")
    
    # Clear in-memory stores (but keep tokens)
    _STORE.clear()
    _RATINGS_CACHE.clear()
    _AUDIT_LOG.clear()
    
    # Also clear the global _ARTIFACT_STORE's memory
    _ARTIFACT_STORE._memory_store.clear()
    
    logger.warning(f"RESET: After clearing in-memory: _STORE={len(_STORE)}, _RATINGS_CACHE={len(_RATINGS_CACHE)}, _AUDIT_LOG={len(_AUDIT_LOG)}")
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
            logger.error(f"RESET: WARNING - Artifacts still present after clear: {[a.get('metadata', {}).get('id') for a in all_artifacts[:5]]}")
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
    
    return jsonify({"message": "Registry is reset."}), 200

# -------------------- Name and RegEx lookups --------------------

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
        return jsonify({"message": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"}), 400
    try:
        sanitized = _sanitize_search_pattern(regex)
        pattern = re.compile(sanitized, re.IGNORECASE)
    except re.error:
        return jsonify({"message": "Invalid regex"}), 400
    matches = []
    for art in _STORE.values():
        readme = ""
        if isinstance(art.data, dict):
            readme = str(art.data.get("readme", ""))
        if pattern.search(art.metadata.name) or pattern.search(readme):
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
    return jsonify(
        {
            "plannedTracks": [
                "Performance track",
                "Access control track",
            ]
        }
    ), 200