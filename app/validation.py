"""Lightweight input validation middleware.

Provides conservative checks that are safe for existing endpoints:
- Enforces MAX_CONTENT_LENGTH (redundant with Flask but explicit)
- Detects malformed JSON early for JSON requests
- Limits query parameter and view-arg lengths
- Limits string lengths inside JSON payloads to avoid overly large fields

These checks are intentionally conservative so they don't change existing
endpoint contracts. Configure limits via app.config:
"""
from typing import Any

from flask import request, jsonify
from http import HTTPStatus


def _iter_strings(obj: Any):
    """Yield all string values nested within obj (dict/list/str).

This helps enforce a maximum string length in JSON payloads without
fully validating schemas.
"""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)


def init_validation(app):
    max_qlen = int(app.config.get("MAX_QUERY_PARAM_LENGTH", 512))
    max_jslen = int(app.config.get("MAX_JSON_STRING_LENGTH", 2048))

    @app.before_request
    def _validate_request():
        # Enforce content length explicitly (Werkzeug may also enforce this)
        cl = request.content_length
        if cl is not None and cl > app.config.get("MAX_CONTENT_LENGTH", 1_048_576):
            resp = jsonify({"message": "Request payload too large"})
            resp.status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            return resp

        # Basic query param length checks
        for k, v in request.args.items():
            if v is not None and len(v) > max_qlen:
                resp = jsonify({"message": f"Query parameter '{k}' is too long"})
                resp.status_code = HTTPStatus.BAD_REQUEST
                return resp

        # View args (path parameters) length checks
        for k, v in (request.view_args or {}).items():
            if isinstance(v, str) and len(v) > 256:
                resp = jsonify({"message": f"Path parameter '{k}' is too long"})
                resp.status_code = HTTPStatus.BAD_REQUEST
                return resp

        # If this looks like a JSON request, attempt to parse and do light checks
        if request.method in ("POST", "PUT", "PATCH") and (
            request.content_type and "application/json" in request.content_type
        ):
            payload = request.get_json(silent=True)
            # If content-length indicates there's a body but parsing failed -> malformed JSON
            if (cl and cl > 0) and payload is None:
                resp = jsonify({"message": "Malformed JSON payload"})
                resp.status_code = HTTPStatus.BAD_REQUEST
                return resp
            if isinstance(payload, (dict, list)):
                # iterate strings and enforce max length
                for s in _iter_strings(payload):
                    if s is not None and len(s) > max_jslen:
                        resp = jsonify({"message": "JSON field too long"})
                        resp.status_code = HTTPStatus.BAD_REQUEST
                        return resp

    # expose init as a no-op return
    return None
