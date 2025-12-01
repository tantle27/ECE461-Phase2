import logging
from typing import Any

import awsgi  # type: ignore[import-untyped]

from app.app import create_app

flask_app = create_app()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _transform_lambda_function_url_event(event: dict[str, Any]) -> dict[str, Any]:
    """Transform Lambda Function URL event format to API Gateway format for awsgi.
    Lambda Function URLs use a different event structure than API Gateway:
    - requestContext.http.method instead of httpMethod
    - rawPath instead of path
    - No multiValueHeaders, etc.
    """
    if "requestContext" in event and "http" in event.get("requestContext", {}):
        # This is a Lambda Function URL event, transform it to API Gateway format
        http = event["requestContext"]["http"]
        return {
            "httpMethod": http.get("method", "GET"),
            "path": event.get("rawPath", "/"),
            "queryStringParameters": event.get("queryStringParameters"),
            "headers": event.get("headers", {}),
            "body": event.get("body"),
            "isBase64Encoded": event.get("isBase64Encoded", False),
            "requestContext": event.get("requestContext", {}),
        }
    # Already in API Gateway format
    return event


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler that adapts API Gateway/Function URL events to Flask WSGI."""
    log.info("Lambda invocation: %s", event.get("rawPath") or event.get("path", "/"))
    # Transform Lambda Function URL events to API Gateway format
    transformed_event = _transform_lambda_function_url_event(event)
    return awsgi.response(flask_app, transformed_event, context)
