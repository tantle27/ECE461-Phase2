from typing import Any, Dict

from app.app import create_app
import awsgi  # type: ignore[import-untyped]

# Cold-start initialization (keeps app warm)
flask_app = create_app()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda entrypoint translating API Gateway requests to Flask WSGI."""
    return awsgi.response(flask_app, event, context)