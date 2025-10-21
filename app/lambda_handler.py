import logging
from typing import Any, Dict

import awsgi  # type: ignore[import-untyped]
from app.app import create_app

flask_app = create_app()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler that adapts API Gateway/Function URL events to Flask WSGI."""
    log.info("Lambda invocation: %s", event.get("rawPath") or event.get("path", "/"))
    return awsgi.response(flask_app, event, context)
