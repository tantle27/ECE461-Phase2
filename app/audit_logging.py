import json
import logging
import time
from typing import Any

from flask import g, request


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": int(time.time() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # include any structured data passed via extra
        base = logging.LogRecord("", 0, "", "", None, (), None).__dict__
        extras = {k: v for k, v in record.__dict__.items() if k not in base}
        # common safe extras
        for k in (
            "request_id",
            "client_ip",
            "user",
            "artifact",
            "operation",
            "duration_ms",
            "alert",
        ):
            if k in extras:
                payload[k] = extras[k]
        # include any remaining items
        for k, v in extras.items():
            if k not in payload:
                try:
                    json.dumps({k: v})
                    payload[k] = v
                except Exception:
                    payload[k] = str(v)
        return json.dumps(payload)


def init_audit_logging(app) -> None:
    """Configure an `audit` logger for structured JSON logs and register
    lightweight Flask hooks to emit request-level audit entries.

    These logs are JSON on stdout and can be picked up by CloudWatch Logs
    or similar systems. Security alerts are emitted as structured logs with
    an `alert` flag which can be turned into CloudWatch Metric Filters.
    """
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    if not audit_logger.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(JSONFormatter())
        audit_logger.addHandler(sh)
        audit_logger.propagate = False

    @app.before_request
    def _audit_before():
        # mark request start time and a lightweight request id
        g._audit_start = time.time()
        g._request_id = f"r_{int(g._audit_start*1000)}"

    @app.after_request
    def _audit_after(response):
        try:
            start = getattr(g, "_audit_start", time.time())
            duration_ms = int((time.time() - start) * 1000)
            client_ip = request.remote_addr or request.headers.get("X-Forwarded-For", "")
            token_hdr = request.headers.get("X-Authorization", "") or request.headers.get("Authorization", "")
            token_present = bool(token_hdr)
            event = {
                "type": "http_request",
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "token_present": token_present,
                "request_id": getattr(g, "_request_id", None),
            }
            # Log as INFO normally
            audit_logger.info("http_request", extra=event)
            # Emit security alert for 401/403/500 as a structured alert
            if response.status_code in (401, 403, 500):
                alert = {**event, "alert": True, "alert_type": "security"}
                audit_logger.warning("security_alert", extra=alert)
        except Exception:
            audit_logger.exception("failed to emit audit log for request")
        return response


def audit_event(message: str, **fields: Any) -> None:
    logging.getLogger("audit").info(message, extra=fields)


def security_alert(message: str, **fields: Any) -> None:
    # Use WARNING level so it's easy to filter; include alert=true
    logging.getLogger("audit").warning(message, extra={**fields, "alert": True, "alert_type": "security"})


def db_audit(operation: str, **fields: Any) -> None:
    logging.getLogger("audit").info("db_operation", extra={"operation": operation, **fields})
