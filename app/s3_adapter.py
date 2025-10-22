"""
S3 storage adapter for artifact blobs.

Features:
- Optional enablement via USE_S3 env var (default: false)
- Versioned bucket support (stores VersionId if available)
- Presigned URL generation for efficient downloads
- Simple put/get/delete operations

Env vars:
- USE_S3=true|false
- S3_BUCKET_NAME=your-bucket
- S3_REGION=us-east-2
- S3_PREFIX=optional/prefix (no leading slash)
- S3_SSE=aws:kms|AES256 (optional)
- S3_KMS_KEY_ID=arn:aws:kms:... (optional, when S3_SSE=aws:kms)
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

USE_S3 = os.environ.get("USE_S3", "false").lower() == "true"
S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
S3_REGION = os.environ.get("S3_REGION", os.environ.get("AWS_REGION", "us-east-2"))
S3_PREFIX = os.environ.get("S3_PREFIX", "uploads").strip("/")
S3_SSE = os.environ.get("S3_SSE")  # None|AES256|aws:kms
S3_KMS_KEY_ID = os.environ.get("S3_KMS_KEY_ID")
S3_ACL = os.environ.get("S3_ACL")  # e.g., bucket-owner-full-control (optional)

logger.info("S3 module init: USE_S3=%s S3_BUCKET=%s S3_REGION=%s", USE_S3, S3_BUCKET, S3_REGION)

s3_client = None
if USE_S3:
    try:
        import boto3  # type: ignore

        s3_client = boto3.client("s3", region_name=S3_REGION)
        logger.info("S3 enabled: bucket=%s region=%s prefix=%s", S3_BUCKET, S3_REGION, S3_PREFIX)
    except Exception:
        logger.exception("Failed to initialize S3 client; disabling S3 integration")
        USE_S3 = False


class S3Storage:
    def __init__(self) -> None:
        self.enabled = USE_S3 and bool(S3_BUCKET and s3_client)
        self.bucket = S3_BUCKET
        self.prefix = S3_PREFIX

    def _key(self, relpath: str) -> str:
        rel = relpath.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{rel}"
        return rel

    def put_file(self, fileobj: io.BufferedReader | io.BytesIO, key_rel: str, content_type: Optional[str] = None) -> dict[str, Any]:
        if not self.enabled or not s3_client or not self.bucket:
            logger.error("S3Storage.put_file failed precondition: enabled=%s, s3_client=%s, bucket=%s", self.enabled, s3_client is not None, self.bucket)
            raise RuntimeError("S3Storage not enabled")
        logger.info("S3Storage.put_file: bucket=%s key=%s", self.bucket, self._key(key_rel))
        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self._key(key_rel),
            "Body": fileobj,
        }
        if content_type:
            params["ContentType"] = content_type
        if S3_SSE:
            params["ServerSideEncryption"] = S3_SSE
            if S3_SSE == "aws:kms" and S3_KMS_KEY_ID:
                params["SSEKMSKeyId"] = S3_KMS_KEY_ID
        if S3_ACL:
            params["ACL"] = S3_ACL
            logger.info("S3Storage.put_file: applying ACL=%s", S3_ACL)
        try:
            resp = s3_client.put_object(**params)
            version_id = resp.get("VersionId")
            # Head the object for size and content type
            head = s3_client.head_object(Bucket=self.bucket, Key=params["Key"], VersionId=version_id) if version_id else s3_client.head_object(Bucket=self.bucket, Key=params["Key"])
        except Exception as e:
            logger.exception("S3 put_object/head_object failed: %s | params: bucket=%s key=%s", e, self.bucket, params.get("Key"))
            raise
        return {
            "bucket": self.bucket,
            "key": params["Key"],
            "version_id": version_id,
            "size": int(head.get("ContentLength", 0)),
            "content_type": head.get("ContentType"),
        }

    def get_object(self, key: str, version_id: Optional[str] = None) -> tuple[bytes, dict[str, Any]]:
        if not self.enabled or not s3_client or not self.bucket:
            raise RuntimeError("S3Storage not enabled")
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        obj = s3_client.get_object(**params)
        body: bytes = obj["Body"].read()
        meta = {
            "size": int(obj.get("ContentLength", len(body)) or len(body)),
            "content_type": obj.get("ContentType", "application/octet-stream"),
        }
        return body, meta

    def generate_presigned_url(self, key: str, expires_in: int = 3600, version_id: Optional[str] = None) -> str:
        if not self.enabled or not s3_client or not self.bucket:
            raise RuntimeError("S3Storage not enabled")
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        return s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    def delete_object(self, key: str, version_id: Optional[str] = None) -> None:
        if not self.enabled or not s3_client or not self.bucket:
            return
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        try:
            s3_client.delete_object(**params)
        except Exception:
            logger.exception("Failed to delete S3 object: %s", key)
