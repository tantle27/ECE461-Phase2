# lambda_handler.py
import logging
import awsgi
from app.app import create_app

flask_app = create_app()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def handler(event, context):
    log.info("Lambda URL event: %s", event.get("rawPath"))
    return awsgi.response(flask_app, event, context)
