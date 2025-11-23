from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import re

# Load registry secrets early so GH_TOKEN / GENAI_API_KEY are available
# to modules that import configuration during startup. This import is
# optional and failures are logged — we don't want missing boto3 or
# IAM perms to prevent the app from starting.

try:
    from app.secrets_loader import load_registry_secrets
    load_registry_secrets()
except Exception:
    import logging
    logging.exception("secrets_loader failed - continuing without Secrets Manager")

from app.core import blueprint


def create_app(config=None):
    app = Flask(__name__)
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["500 per minute"]
    )

    # Enable CORS for React frontend (local + Amplify)
    # Allow overriding via env var ALLOWED_ORIGINS (comma-separated)
    allowed_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if allowed_env:
        allowed_origins = [o.strip() for o in allowed_env.split(",") if o.strip()]
    else:
        # Default: local dev and any Amplify app domain
        allowed_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # Use regex to allow any Amplify subdomain
            re.compile(r"^https://.*\.amplifyapp\.com$"),
        ]

    CORS(
        app,
        resources={r"/*": {"origins": allowed_origins}},
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Authorization"],
        expose_headers=["offset", "X-Size-Cost-Bytes"],
        supports_credentials=True,
        max_age=600,
    )

    app.register_blueprint(blueprint)
    if config:
        app.config.update(config)
    if not app.logger.handlers:
        import logging

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
        app.logger.addHandler(handler)
    app.logger.setLevel("INFO")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)
