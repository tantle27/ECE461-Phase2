import logging
from typing import Any, Dict

import aws_wsgi  # type: ignore[import-untyped]
from app.app import create_app

flask_app = create_app()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    log.info("Lambda event: %s", event.get("rawPath") or event.get("path"))
    return aws_wsgi.response(flask_app, event, context)
