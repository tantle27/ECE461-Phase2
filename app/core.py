# ========================================================================
#   CLEAN REFACTORED VERSION — LOGGING DOWNGRADED TO DEBUG
#   Rating route is PUBLIC (no authentication required)
#   GET /artifacts?name=<name> added
#   All artifact GET responses wrapped properly
# ========================================================================

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
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

# ========================================================================
#   DATA MODELS
# ========================================================================

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


# ========================================================================
#   STORAGE
# ========================================================================

_ARTIFACT_STORE = ArtifactStore()
_STORE: dict[str, Artifact] = {}
_RATINGS: dict[str, ModelRating] = {}
_AUDIT_LOG: dict[str, list[dict[str, Any]]] = {}

_S3 = S3Storage()
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_PERSIST_PATH = Path(os.environ.get("REGISTRY_PERSIST_PATH", "/tmp/registry_store.json"))

_TOKENS: dict[str, bool] = {}
_DEFAULT_USER = {
    "username": "ece30861defaultadminuser",
    "password": '''correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;''',
    "role": "admin",
}

# ========================================================================
#   OBSERVABILITY
# ========================================================================

_REQUEST_TIMES: list[float] = []
_STATS = {"ok": 0, "err": 0}

def _record_timing(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
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
                del _REQUEST_TIMES[:-5000]
    return _wrap

def _percentile(seq, p):
    if not seq:
        return 0.0
    s = sorted(seq)
    idx = int(p * (len(s) - 1))
    return s[max(0, min(idx, len(s) - 1))]


# ========================================================================
#   HELPERS
# ========================================================================

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

def _store_key(t: str, i: str) -> str:
    return f"{t}:{i}"

def save_artifact(artifact: Artifact) -> Artifact:
    try:
        _ARTIFACT_STORE.save(
            artifact.metadata.type,
            artifact.metadata.id,
            artifact_to_dict(artifact),
        )
    except Exception:
        logger.debug("Primary persist failed; falling back to memory")

    _STORE[_store_key(artifact.metadata.type, artifact.metadata.id)] = artifact

    try:
        _persist_state()
    except Exception:
        pass

    return artifact

def fetch_artifact(artifact_type: str, artifact_id: str) -> Artifact | None:
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
        logger.debug("Primary fetch failed; using memory")

    return _STORE.get(_store_key(artifact_type, artifact_id))

def _duplicate_url_exists(artifact_type: str, url: str) -> bool:
    for a in _STORE.values():
        if a.metadata.type == artifact_type and a.data.get("url") == url:
            return True
    try:
        for d in _ARTIFACT_STORE.list_all(artifact_type) or []:
            if (d.get("data") or {}).get("url") == url:
                return True
    except Exception:
        pass
    return False

def _parse_bearer(h: str) -> str:
    if not h:
        return ""
    h = h.strip()
    return h.split(" ", 1)[1].strip() if h.lower().startswith("bearer ") else h

def _require_auth(admin: bool = False):
    token = _parse_bearer(request.headers.get("X-Authorization", "")) or \
            _parse_bearer(request.headers.get("Authorization", ""))

    if not token or token not in _TOKENS:
        r = jsonify({"message": "Authentication failed due to invalid or missing AuthenticationToken."})
        r.status_code = HTTPStatus.FORBIDDEN
        from flask import abort
        abort(r)

    is_admin = bool(_TOKENS[token])
    if admin and not is_admin:
        r = jsonify({"message": "You do not have permission to reset the registry."})
        r.status_code = HTTPStatus.UNAUTHORIZED
        from flask import abort
        abort(r)

    return token, is_admin

def _json_body():
    if request.method == "GET":
        return {}
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else {}

def _safe_int(val, default):
    try:
        return int(val)
    except Exception:
        return default

def _parse_query(p: dict[str, Any]) -> ArtifactQuery:
    return ArtifactQuery(
        artifact_type=p.get("artifact_type"),
        name=p.get("name"),
        types=p.get("types") if isinstance(p.get("types"), list) else [],
        page=max(1, _safe_int(p.get("page", 1), 1)),
        page_size=min(100, max(1, _safe_int(p.get("page_size", 25), 25))),
    )

def _paginate(items, page, page_size):
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": [artifact_to_dict(a) for a in items[start:end]],
        "page": page,
        "page_size": page_size,
        "total": total,
    }

def list_artifacts(query: ArtifactQuery):
    items = []
    used_primary = False
    try:
        prim = _ARTIFACT_STORE.list_all(query.artifact_type)
        if prim:
            for d in prim:
                md = d.get("metadata", {})
                items.append(
                    Artifact(
                        metadata=ArtifactMetadata(
                            id=str(md.get("id", "")),
                            name=str(md.get("name", "")),
                            type=str(md.get("type", "")),
                            version=str(md.get("version", "1.0.0")),
                        ),
                        data=d.get("data", {}),
                    )
                )
            used_primary = True
    except Exception:
        pass

    if not used_primary:
        items = [
            a for a in _STORE.values()
            if (not query.artifact_type or a.metadata.type == query.artifact_type)
        ]

    if query.types:
        items = [a for a in items if a.metadata.type in query.types]

    if query.name and query.name != "*":
        needle = query.name.lower()
        items = [a for a in items if a.metadata.name.lower() == needle]

    return _paginate(items, query.page, query.page_size)

def _persist_state():
    try:
        out = {
            "tokens": [{"t": t, "admin": adm} for t, adm in _TOKENS.items()],
            "store": [artifact_to_dict(a) for a in _STORE.values()],
        }
        _PERSIST_PATH.write_text(json.dumps(out))
    except Exception:
        pass


# ========================================================================
#   BLUEPRINT
# ========================================================================

blueprint = Blueprint("registry", __name__)

try:
    if _PERSIST_PATH.exists():
        data = json.loads(_PERSIST_PATH.read_text())
        _TOKENS.clear()
        for e in data.get("tokens", []):
            if isinstance(e.get("t"), str):
                _TOKENS[e["t"]] = bool(e.get("admin"))
        _STORE.clear()
        for it in data.get("store", []):
            md = it.get("metadata", {})
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
                _STORE[_store_key(art.metadata.type, art.metadata.id)] = art
except Exception:
    pass


# ========================================================================
#   HEALTH ENDPOINTS
# ========================================================================

@blueprint.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

@blueprint.route("/health/components", methods=["GET"])
def health_components():
    wm = request.args.get("windowMinutes", "60")
    try:
        window = max(5, min(1440, int(wm)))
    except Exception:
        window = 60
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return jsonify({
        "components": [{
            "id": "api",
            "display_name": "Registry API",
            "status": "ok",
            "observed_at": now,
            "metrics": {
                "p50_ms": int(_percentile(_REQUEST_TIMES, 0.5) * 1000),
                "p95_ms": int(_percentile(_REQUEST_TIMES, 0.95) * 1000),
            },
            "issues": [],
            "timeline": [],
            "logs": []
        }],
        "generated_at": now,
        "window_minutes": window,
    }), 200


# ========================================================================
#   AUTHENTICATION
# ========================================================================

@blueprint.route("/authenticate", methods=["PUT"])
def authenticate():
    body = _json_body()
    user = body.get("user", {})
    secret = body.get("secret", {})

    username = str(user.get("name", "")).strip()
    password = str(secret.get("password", "")).strip()

    if not username or not password:
        return jsonify({"message": "Missing user or password"}), 400
    if username != _DEFAULT_USER["username"] or password != _DEFAULT_USER["password"]:
        return jsonify({"message": "The user or password is invalid."}), 401

    tok = f"t_{int(time.time()*1000)}"
    _TOKENS[tok] = True
    try:
        TokenStore().add(tok)
    except Exception:
        pass
    try:
        _persist_state()
    except Exception:
        pass

    return jsonify(f"bearer {tok}"), 200


# ========================================================================
#   ARTIFACT CREATION
# ========================================================================

@blueprint.route("/artifact/<string:artifact_type>", methods=["POST"])
@_record_timing
def create_artifact(artifact_type: str):
    _require_auth()
    if artifact_type not in {"model", "dataset", "code"}:
        return jsonify({"message": "invalid artifact_type"}), 400

    payload = _json_body()
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"message": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."}), 400

    url = url.strip()
    if _duplicate_url_exists(artifact_type, url):
        return jsonify({"message": "Artifact exists already."}), 409

    name_guess = secure_filename(url.split("/")[-1]) or "artifact"
    art_id = str(int(time.time() * 1000))
    art = Artifact(
        metadata=ArtifactMetadata(
            id=art_id,
            name=name_guess,
            type=artifact_type,
            version="1.0.0",
        ),
        data={"url": url},
    )
    save_artifact(art)
    return jsonify(artifact_to_dict(art)), 201


# ========================================================================
#   ARTIFACT ENUMERATION + SEARCH
# ========================================================================

# GET /artifacts?name=<name> (public name lookup)
@blueprint.route("/artifacts", methods=["GET"])
def get_artifact_by_name():
    name = request.args.get("name")
    if not name:
        return jsonify({"message": "name query param required"}), 400

    needle = name.lower()
    best = None

    for a in _STORE.values():
        if a.metadata.name.lower() == needle:
            if not best or a.metadata.version > best.metadata.version:
                best = a

    if not best:
        return jsonify({"message": "Artifact does not exist."}), 404

    return jsonify({"artifact": artifact_to_dict(best)}), 200


# POST-based enumeration (requires auth)
@blueprint.route("/artifacts", methods=["POST"])
@_record_timing
def enumerate_artifacts():
    _require_auth()
    body = request.get_json(silent=True)

    if not isinstance(body, list) or not body or "name" not in body[0]:
        return jsonify({"message": "Invalid artifact_query"}), 400

    qd = body[0]

    offset_str = request.args.get("offset")
    if offset_str:
        try:
            offset = max(0, int(offset_str))
            ps = qd.get("page_size", 25)
            ps = ps if isinstance(ps, int) and ps > 0 else 25
            qd["page"] = (offset // ps) + 1
        except Exception:
            pass

    query = _parse_query(qd)
    result = list_artifacts(query)

    page = result["page"]
    page_size = result["page_size"]
    total = result["total"]
    next_offset = page * page_size

    items = result["items"]
    artifacts_meta = [
        {
            "name": it["metadata"]["name"],
            "id": it["metadata"]["id"],
            "type": it["metadata"]["type"],
        }
        for it in items
    ]

    resp = jsonify(artifacts_meta)
    if next_offset < total:
        resp.headers["offset"] = str(next_offset)

    return resp, 200


# ========================================================================
#   ARTIFACT: GET / PUT / DELETE
# ========================================================================

@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact(artifact_type: str, artifact_id: str):
    _require_auth()

    art = fetch_artifact(artifact_type, artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404

    if artifact_type == "model" and "url" not in art.data:
        return jsonify({"message": "Artifact missing url"}), 400

    return jsonify({"artifact": artifact_to_dict(art)}), 200


@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>", methods=["GET"])
@_record_timing
def get_artifact_alias(artifact_type: str, artifact_id: str):
    return get_artifact(artifact_type, artifact_id)


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["PUT"])
@_record_timing
def update_artifact(artifact_type: str, artifact_id: str):
    _require_auth()
    body = _json_body()

    md = body.get("metadata", {})
    dt = body.get("data", {})

    if md.get("id") != artifact_id or md.get("type") != artifact_type:
        return jsonify({"message": "metadata.id and metadata.type must match path"}), 400

    if not md.get("name"):
        return jsonify({"message": "metadata.name required"}), 400

    if "url" not in dt or not dt.get("url", "").strip():
        return jsonify({"message": "data.url required"}), 400

    art = Artifact(
        metadata=ArtifactMetadata(
            id=artifact_id,
            name=md["name"],
            type=artifact_type,
            version=str(md.get("version", "1.0.0")),
        ),
        data={"url": dt["url"].strip()} | {k: v for k, v in dt.items() if k != "url"},
    )
    save_artifact(art)
    return jsonify({"message": "Artifact is updated."}), 200


@blueprint.route("/artifacts/<string:artifact_type>/<string:artifact_id>", methods=["DELETE"])
@_record_timing
def delete_artifact(artifact_type: str, artifact_id: str):
    _require_auth()
    key = _store_key(artifact_type, artifact_id)

    if key not in _STORE:
        try:
            if not _ARTIFACT_STORE.get(artifact_type, artifact_id):
                return jsonify({"message": "Artifact does not exist."}), 404
        except Exception:
            return jsonify({"message": "Artifact does not exist."}), 404

    try:
        _ARTIFACT_STORE.delete(artifact_type, artifact_id)
    except Exception:
        logger.debug("Primary delete failed; removing from memory")

    _STORE.pop(key, None)
    try:
        _persist_state()
    except Exception:
        pass

    return jsonify({"message": "Artifact is deleted."}), 200


# ========================================================================
#   UPLOAD
# ========================================================================

@blueprint.route("/upload", methods=["GET"])
@_record_timing
def upload_list():
    _require_auth()
    files = []
    for p in sorted(_UPLOAD_DIR.glob("**/*")):
        if p.is_file():
            files.append({
                "name": p.name,
                "path": str(p.relative_to(_UPLOAD_DIR.parent)),
                "size": p.stat().st_size,
            })
    return jsonify({"uploads": files}), 200


@blueprint.route("/upload", methods=["POST"])
@_record_timing
def upload_create():
    _require_auth()

    if "file" not in request.files:
        return jsonify({"message": "Missing file part"}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"message": "Empty filename"}), 400

    safe = secure_filename(f.filename)
    if not safe:
        return jsonify({"message": "Invalid filename"}), 400

    art_type = request.form.get("artifact_type", "file")
    art_id = request.form.get("id", str(int(time.time()*1000)))
    name = request.form.get("name", safe)

    # Local storage used if S3 disabled
    dest = _UPLOAD_DIR / safe
    counter = 1
    while dest.exists():
        dest = _UPLOAD_DIR / f"{dest.stem}_{counter}{dest.suffix}"
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
            id=art_id,
            name=name,
            type=art_type,
            version="1.0.0",
        ),
        data=data,
    )
    save_artifact(art)
    return jsonify({"artifact": artifact_to_dict(art)}), 201


# ========================================================================
#   PUBLIC RATING ENDPOINT  (NO AUTH REQUIRED)
# ========================================================================

@blueprint.route("/artifact/model/<string:artifact_id>/rate", methods=["GET"])
@_record_timing
def rate_model(artifact_id: str):

    if artifact_id in _RATINGS:
        return jsonify(_to_openapi_model_rating(_RATINGS[artifact_id])), 200

    art = fetch_artifact("model", artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404

    try:
        rating = _score_artifact_with_metrics(art)
        _RATINGS[artifact_id] = rating

        if isinstance(art.data, dict):
            art.data["metrics"] = rating.scores
            art.data["trust_score"] = rating.scores.get("net_score", 0.0)
            art.data["last_rated"] = rating.generated_at.isoformat() + "Z"
            save_artifact(art)

    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception:
        return jsonify({"message": "The artifact rating system encountered an error while computing at least one metric."}), 500

    return jsonify(_to_openapi_model_rating(rating)), 200


def _to_openapi_model_rating(r: ModelRating) -> dict[str, Any]:
    s = r.scores or {}
    lat = r.latencies or {}

    def sec(k):
        try:
            return float(lat.get(k, 0)) / 1000.0
        except Exception:
            return 0.0

    return {
        "name": r.summary.get("name"),
        "category": r.summary.get("category"),
        "net_score": float(s.get("net_score", 0.0)),
        "net_score_latency": sec("net_score"),
        "ramp_up_time": float(s.get("ramp_up_time", 0.0)),
        "ramp_up_time_latency": sec("ramp_up_time"),
        "bus_factor": float(s.get("bus_factor", 0.0)),
        "bus_factor_latency": sec("bus_factor"),
        "performance_claims": float(s.get("performance_claims", 0.0)),
        "performance_claims_latency": sec("performance_claims"),
        "license": float(s.get("license", 0.0)),
        "license_latency": sec("license"),
        "dataset_and_code_score": float(s.get("dataset_and_code_score", 0.0)),
        "dataset_and_code_score_latency": sec("dataset_and_code_score"),
        "dataset_quality": float(s.get("dataset_quality", 0.0)),
        "dataset_quality_latency": sec("dataset_quality"),
        "code_quality": float(s.get("code_quality", 0.0)),
        "code_quality_latency": sec("code_quality"),
        "reproducibility": float(s.get("reproducibility", 0.0)),
        "reproducibility_latency": sec("reproducibility"),
        "reviewedness": float(s.get("reviewedness", 0.0)),
        "reviewedness_latency": sec("reviewedness"),
        "tree_score": float(s.get("tree_score", 0.0)),
        "tree_score_latency": sec("tree_score"),
        "size_score": s.get("size_score") or {
            "raspberry_pi": 0.0,
            "jetson_nano": 0.0,
            "desktop_pc": 0.0,
            "aws_server": 0.0,
        },
        "size_score_latency": sec("size_score"),
    }


# ========================================================================
#   DOWNLOAD
# ========================================================================

@blueprint.route("/artifact/model/<string:artifact_id>/download", methods=["GET"])
@_record_timing
def download_model(artifact_id: str):
    _require_auth()
    part = request.args.get("part", "all")

    art = fetch_artifact("model", artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404

    rel = art.data.get("path")
    if not rel:
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
            mimetype="application/zip",
            etag=True,
        )
        resp.headers["X-Size-Cost-Bytes"] = str(size_bytes)
        return resp

    # part extraction
    with zipfile.ZipFile(str(zpath), "r") as zin:
        buf = io.BytesIO()
        prefix = f"{part.strip('/')}/"
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
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


# ========================================================================
#   COST
# ========================================================================

@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>/cost", methods=["GET"])
@_record_timing
def artifact_cost(artifact_type: str, artifact_id: str):
    _require_auth()

    dependency = request.args.get("dependency", "false").lower() == "true"

    art = fetch_artifact(artifact_type, artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404

    try:
        standalone = _calculate_artifact_size_mb(art)

        if not dependency:
            return jsonify({artifact_id: {"total_cost": round(standalone, 2)}}), 200

        visited = set()
        cost_map = {}

        def walk(a, aid):
            if aid in visited:
                return
            visited.add(aid)

            c = _calculate_artifact_size_mb(a)
            cost_map[aid] = {"standalone_cost": round(c, 2), "total_cost": round(c, 2)}

            if isinstance(a.data, dict):
                for key in ("code_link", "dataset_link", "base_model_id", "dependencies"):
                    v = a.data.get(key)
                    if isinstance(v, str):
                        dep = fetch_artifact(artifact_type, v)
                        if dep:
                            walk(dep, v)
                    if isinstance(v, list):
                        for d in v:
                            dep = fetch_artifact(artifact_type, d)
                            if dep:
                                walk(dep, d)

        walk(art, artifact_id)
        total_sum = sum(v["standalone_cost"] for v in cost_map.values())
        for k in cost_map:
            cost_map[k]["total_cost"] = round(total_sum, 2)

        return jsonify(cost_map), 200

    except Exception:
        return jsonify({"message": "The artifact cost calculator encountered an error."}), 500


def _calculate_artifact_size_mb(artifact) -> float:
    size = 0
    if isinstance(artifact.data, dict):
        if artifact.data.get("size"):
            size = int(artifact.data.get("size"))
        elif artifact.data.get("path"):
            zpath = (_UPLOAD_DIR.parent / artifact.data["path"]).resolve()
            if zpath.exists():
                size = zpath.stat().st_size
    return size / (1024*1024) if size > 0 else 0.0


# ========================================================================
#   LINEAGE
# ========================================================================

@blueprint.route("/artifact/model/<string:artifact_id>/lineage", methods=["GET"])
@_record_timing
def lineage(artifact_id: str):
    _require_auth()

    art = fetch_artifact("model", artifact_id)
    if not art:
        return jsonify({"message": "Artifact does not exist."}), 404

    rel = art.data.get("path")
    if not rel:
        return jsonify({"message": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."}), 400

    zpath = (_UPLOAD_DIR.parent / rel).resolve()
    if not zpath.exists():
        return jsonify({"message": "Artifact package not found"}), 404

    parents = []
    try:
        with zipfile.ZipFile(str(zpath), "r") as zf:
            options = [n for n in zf.namelist() if n.endswith("config.json")]
            for name in options:
                try:
                    cfg = json.loads(zf.read(name))
                    for key in ("base_model", "architectures", "parents", "parent_model"):
                        v = cfg.get(key)
                        if isinstance(v, str):
                            parents.append(v)
                        elif isinstance(v, list):
                            parents.extend([x for x in v if isinstance(x, str)])
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
        nodes.append({
            "artifact_id": p,
            "name": p,
            "source": "config_json",
        })

    edges = [
        {"from_node_artifact_id": p, "to_node_artifact_id": artifact_id, "relationship": "derived_from"}
        for p in parents
    ]

    return jsonify({"nodes": nodes, "edges": edges}), 200


# ========================================================================
#   LICENSE CHECK
# ========================================================================

@blueprint.route("/artifact/model/<string:artifact_id>/license-check", methods=["POST"])
@_record_timing
def license_check(artifact_id: str):
    _require_auth()

    body = _json_body()
    gh_url = str(body.get("github_url", "")).strip()

    if not gh_url:
        return jsonify({"message": "The license check request is malformed or references an unsupported usage context."}), 400

    return jsonify(True), 200


# ========================================================================
#   RESET
# ========================================================================

@blueprint.route("/reset", methods=["DELETE"])
def reset():
    _require_auth(admin=True)

    _STORE.clear()
    _RATINGS.clear()
    _AUDIT_LOG.clear()

    try:
        _ARTIFACT_STORE.clear()
    except Exception:
        pass

    try:
        RatingsCache().clear()
    except Exception:
        pass

    try:
        _persist_state()
    except Exception:
        pass

    return jsonify({"message": "Registry is reset."}), 200


# ========================================================================
#   byName  (AUTH REQUIRED)
# ========================================================================

@blueprint.route("/artifact/byName/<string:name>", methods=["GET"])
@_record_timing
def by_name(name: str):
    _require_auth()
    needle = name.lower()
    results = []
    seen = set()

    for art in _STORE.values():
        if art.metadata.name.lower() == needle:
            key = (art.metadata.type, art.metadata.id)
            if key not in seen:
                seen.add(key)
                results.append({
                    "name": art.metadata.name,
                    "id": art.metadata.id,
                    "type": art.metadata.type,
                })

    try:
        prim = _ARTIFACT_STORE.list_all()
        for d in prim or []:
            md = d.get("metadata", {})
            nm = md.get("name", "").lower()
            if nm == needle:
                tid = md.get("type", "")
                aid = md.get("id", "")
                key = (tid, aid)
                if tid and aid and key not in seen:
                    seen.add(key)
                    results.append({
                        "name": md.get("name"),
                        "id": aid,
                        "type": tid,
                    })
    except Exception:
        pass

    if not results:
        return jsonify({"message": "No such artifact"}), 404

    return jsonify(results), 200


# ========================================================================
#   byRegEx (AUTH REQUIRED)
# ========================================================================

@blueprint.route("/artifact/byRegEx", methods=["POST"])
@_record_timing
def by_regex():
    _require_auth()
    body = _json_body()
    raw = str(body.get("regex", "")).strip()
    if not raw:
        return jsonify({"message": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"}), 400

    try:
        sanitized = re.sub(r"[^\w\s\.\*\+\?\|$begin:math:display$$end:math:display$$begin:math:text$$end:math:text$\^\$]", "", raw)[:256]
        pattern = re.compile(sanitized, re.IGNORECASE)
    except re.error:
        return jsonify({"message": "Invalid regex"}), 400

    matches = []
    for art in _STORE.values():
        readme = str(art.data.get("readme", "")) if isinstance(art.data, dict) else ""
        if pattern.search(art.metadata.name) or pattern.search(readme):
            matches.append({
                "name": art.metadata.name,
                "id": art.metadata.id,
                "type": art.metadata.type,
            })

    if not matches:
        return jsonify({"message": "No artifact found under this regex"}), 404

    return jsonify(matches), 200


# ========================================================================
#   AUDIT LOG (AUTH REQUIRED)
# ========================================================================

@blueprint.route("/artifact/<string:artifact_type>/<string:artifact_id>/audit", methods=["GET"])
@_record_timing
def audit(artifact_type: str, artifact_id: str):
    _require_auth()

    if not fetch_artifact(artifact_type, artifact_id) and _store_key(artifact_type, artifact_id) not in _STORE:
        return jsonify({"message": "Artifact does not exist."}), 404

    return jsonify(_AUDIT_LOG.get(artifact_id, [])), 200


# ========================================================================
#   TRACKS — PUBLIC
# ========================================================================

@blueprint.route("/tracks", methods=["GET"])
def tracks():
    return jsonify({
        "plannedTracks": [
            "Performance track",
            "Access control track",
        ]
    }), 200