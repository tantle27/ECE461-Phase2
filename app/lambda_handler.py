import logging
from typing import Any, Dict

import awsgi  # type: ignore[import-untyped]
from app.app import create_app
import os

flask_app = create_app()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _transform_lambda_function_url_event(event: Dict[str, Any]) -> Dict[str, Any]:
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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler that adapts API Gateway/Function URL events to Flask WSGI."""
    log.info("Lambda invocation: %s", event.get("rawPath") or event.get("path", "/"))
    # Default to FAST_RATING_MODE=true on Lambda unless explicitly disabled
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        frm = os.environ.get("FAST_RATING_MODE")
        if not frm or frm.strip().lower() not in ("false", "0", "no"):
            os.environ["FAST_RATING_MODE"] = "true"
    # Transform Lambda Function URL events to API Gateway format
    transformed_event = _transform_lambda_function_url_event(event)
    
    # Check if awsgi.response is available (Lambda deployment may have incomplete awsgi package)
    if hasattr(awsgi, 'response'):
        return awsgi.response(flask_app, transformed_event, context)
    
    # Fallback: use Flask test client when awsgi.response is not available
    log.warning("awsgi.response not found - using Flask test client fallback")
    with flask_app.test_client() as client:
        method = transformed_event.get("httpMethod", "GET")
        path = transformed_event.get("path", "/")
        headers = transformed_event.get("headers", {})
        body = transformed_event.get("body")
        query_string = transformed_event.get("queryStringParameters")
        
        response = client.open(
            path=path,
            method=method,
            headers=headers,
            data=body,
            query_string=query_string
        )
        
        return {
            "statusCode": response.status_code,
            "headers": dict(response.headers),
            "body": response.get_data(as_text=True),
            "isBase64Encoded": False
        }
