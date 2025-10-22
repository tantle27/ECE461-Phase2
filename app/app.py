from flask import Flask

# Load registry secrets early so GH_TOKEN / GENAI_API_KEY are available
# to modules that import configuration during startup. This import is
# optional and failures are logged — we don't want missing boto3 or
# IAM perms to prevent the app from starting.
try:
    # Use the src package path used elsewhere in the project
    from src.core import secrets_loader  # type: ignore
except Exception:
    import logging

    logging.exception("Failed to import secrets_loader; continuing without Secrets Manager lookup")

from app.core import blueprint


def create_app(config=None):
    app = Flask(__name__)
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
