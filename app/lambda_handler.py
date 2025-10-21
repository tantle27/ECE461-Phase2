# app/lambda_handler.py
from app.app import create_app
import awsgi

# Cold-start initialization (keeps app warm)
flask_app = create_app()

def handler(event, context):
    """AWS Lambda entrypoint translating API Gateway requests to Flask WSGI."""
    return awsgi.response(flask_app, event, context)
