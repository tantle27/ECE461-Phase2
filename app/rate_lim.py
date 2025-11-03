"""Rate limiting middleware for app using Flask-Limiter."""
from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _limiter_key_func() -> str:
    """Return a string key for rate-limiting: bearer token or IP."""
    token_hdr = (
        request.headers.get("X-Authorization", "")
        or request.headers.get("Authorization", "")
    )
    if token_hdr:
        v = token_hdr.strip()
        if v.lower().startswith("bearer "):
            return v.split(" ", 1)[1].strip()
        return v
    return get_remote_address()


def init_rate_limiter(app) -> None:
    """Initialize Flask-Limiter on the given Flask app.

    Config keys consumed (optional):
      - RATE_LIMIT_MAX: requests per window (default 60)
      - RATE_LIMIT_WINDOW: window seconds (default 60)
      - RATE_LIMIT_DEFAULT: explicit default limits string (overrides the two above)
    """
    app.config.setdefault("RATE_LIMIT_MAX", 360)
    app.config.setdefault("RATE_LIMIT_WINDOW", 60)
    app.config.setdefault(
        "RATE_LIMIT_DEFAULT",
        f"{app.config['RATE_LIMIT_MAX']} per {app.config['RATE_LIMIT_WINDOW']} seconds",
    )
    app.config.setdefault("MAX_CONTENT_LENGTH", 1_048_576)  # 1 MB

    default_limits = app.config.get("RATE_LIMIT_DEFAULT")

    # Attach limiter to app. Using app=app is fine for small single-process apps.
    try:
        Limiter(
            key_func=_limiter_key_func,
            app=app,
            default_limits=[default_limits],
            headers_enabled=True,
        )
    except Exception:
        import logging
        logging.exception("Failed to initialize Flask-Limiter")
