import logging
from typing import Any, Dict

import aws_wsgi  # type: ignore
from app.app import create_app

# Create Flask app using your factory pattern
flask_app = create_app()

# Configure structured logging for Lambda
log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for Flask app via aws-wsgi.
    Converts API Gateway or Lambda Function URL events into WSGI requests.
    """
    path = event.get("rawPath") or event.get("path") or "/"
    log.info(f"Incoming request path: {path}")
    log.info(f"HTTP method: {event.get('requestContext', {}).get('http', {}).get('method')}")
    try:
        response = aws_wsgi.response(flask_app, event, context)
        log.info(f"Response status: {response.get('statusCode')}")
        return response
    except Exception as e:
        log.exception("Error handling request: %s", e)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": '{"error": "Internal Server Error"}',
        }
