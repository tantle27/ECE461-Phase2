"""Small runtime secrets loader for the model registry.

If the environment variable REGISTRY_SECRET_ARN is present, this module
will attempt to read it from AWS Secrets Manager and set GH_TOKEN and
GENAI_API_KEY in os.environ so other modules can read them normally.

The loader is intentionally non-fatal: failure to read secrets will be
logged but will not stop the application from starting (useful for local
development where Secrets Manager isn't available).
"""
from __future__ import annotations

import json
import logging
import os

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:  # pragma: no cover - optional dependency
    boto3 = None  # type: ignore
    BotoCoreError = Exception
    ClientError = Exception


def load_registry_secrets() -> None:
    secret_arn = os.environ.get("REGISTRY_SECRET_ARN")
    if not secret_arn:
        return

    if not boto3:
        logging.warning("boto3 not installed; cannot retrieve secrets from Secrets Manager")
        return

    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_arn)
    except (BotoCoreError, ClientError) as exc:
        logging.exception("Failed to fetch secret %s: %s", secret_arn, str(exc))
        return

    secret_string = resp.get("SecretString")
    if not secret_string:
        logging.warning("Secret %s has no SecretString; skipping", secret_arn)
        return

    try:
        data = json.loads(secret_string)
    except json.JSONDecodeError:
        logging.exception("Secret %s is not valid JSON", secret_arn)
        return

    gh = data.get("GH_TOKEN")
    genai = data.get("GENAI_API_KEY")

    if gh:
        os.environ.setdefault("GH_TOKEN", gh)
    if genai:
        os.environ.setdefault("GENAI_API_KEY", genai)


# Run loader at import time
try:
    load_registry_secrets()
except Exception:
    logging.exception("Unexpected error while loading registry secrets")
