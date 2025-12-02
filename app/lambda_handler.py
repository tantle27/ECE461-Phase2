import logging
from typing import Any

try:
    import awsgi  # type: ignore[import-untyped]
    USING_AWSGI = True
    AWSGI_HAS_RESPONSE = hasattr(awsgi, 'response')
    AWSGI_ATTRS = [x for x in dir(awsgi) if not x.startswith('_')]
except ImportError:
    USING_AWSGI = False
    AWSGI_HAS_RESPONSE = False
    AWSGI_ATTRS = []
    logging.warning("awsgi not available, using direct WSGI invocation")

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
    
    if not USING_AWSGI:
        log.error("awsgi module not available - cannot process request")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": '{"message": "WSGI adapter not configured"}'
        }
    
    if not AWSGI_HAS_RESPONSE:
        log.error(f"awsgi loaded but missing 'response' attribute. Available: {AWSGI_ATTRS}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": '{"message": "WSGI adapter incomplete - awsgi.response not found"}'
        }
    
    # awsgi.response expects (app, event, context) and returns response dict
    try:
        return awsgi.response(flask_app, transformed_event, context)
    except Exception as e:
        log.error("awsgi.response failed: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": '{"message": "Internal server error during request processing"}'
        }
