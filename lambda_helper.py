import awsgi

from app.core import create_app

app = create_app({"UPLOAD_DIR": "/tmp/uploads"})


def handler(event, context):
    # Supports API Gateway (REST/HTTP v2) and Lambda Function URLs
    return awsgi.response(app, event, context)
