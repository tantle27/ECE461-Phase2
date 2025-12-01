"""
Comprehensive test coverage for app/s3_adapter.py.

Tests all major functionality including:
- S3Storage class initialization and configuration
- File upload operations with various parameters
- Object retrieval and metadata handling
- Presigned URL generation
- Object deletion operations
- Error handling and fallback scenarios
- Environment variable configuration
- AWS service integration mocking
"""

import io
import os
from unittest.mock import Mock, patch

import pytest

# Import from app.s3_adapter
from app.s3_adapter import S3_BUCKET, S3_PREFIX, S3_REGION, USE_S3, S3Storage


class TestEnvironmentConfiguration:
    """Test environment variable configuration and initialization."""

    def test_default_environment_values(self):
        """Test default environment variable values."""
        # These are loaded at module import time
        assert isinstance(USE_S3, bool)
        assert S3_REGION == "us-east-2" or S3_REGION == os.environ.get("AWS_REGION", "us-east-2")
        assert S3_PREFIX == "uploads"

    @patch.dict(
        "os.environ",
        {
            "USE_S3": "true",
            "S3_BUCKET_NAME": "test-bucket",
            "S3_REGION": "us-west-2",
            "S3_PREFIX": "test/prefix",
            "S3_SSE": "AES256",
            "S3_ACL": "bucket-owner-full-control",
        },
    )
    def test_environment_variable_override(self):
        """Test environment variable configuration override."""
        # Need to reload module to pick up env changes
        import importlib

        import app.s3_adapter

        importlib.reload(app.s3_adapter)

        assert app.s3_adapter.USE_S3 is True
        assert app.s3_adapter.S3_BUCKET == "test-bucket"
        assert app.s3_adapter.S3_REGION == "us-west-2"
        assert app.s3_adapter.S3_PREFIX == "test/prefix"
        assert app.s3_adapter.S3_SSE == "AES256"
        assert app.s3_adapter.S3_ACL == "bucket-owner-full-control"

    @patch.dict("os.environ", {"USE_S3": "false"})
    def test_s3_disabled_configuration(self):
        """Test S3 disabled configuration."""
        import importlib

        import app.s3_adapter

        importlib.reload(app.s3_adapter)

        assert app.s3_adapter.USE_S3 is False


class TestS3StorageInitialization:
    """Test S3Storage class initialization."""

    def test_s3storage_init_disabled(self):
        """Test S3Storage initialization when S3 is disabled."""
        with patch("app.s3_adapter.USE_S3", False):
            storage = S3Storage()
            assert storage.enabled is False
            assert storage.bucket == S3_BUCKET
            assert storage.prefix == S3_PREFIX

    def test_s3storage_init_enabled_no_bucket(self):
        """Test S3Storage initialization when enabled but no bucket."""
        with patch("app.s3_adapter.USE_S3", True), patch("app.s3_adapter.S3_BUCKET", None), patch(
            "app.s3_adapter.s3_client", Mock()
        ):
            storage = S3Storage()
            assert storage.enabled is False

    def test_s3storage_init_enabled_no_client(self):
        """Test S3Storage initialization when enabled but no client."""
        with patch("app.s3_adapter.USE_S3", True), patch("app.s3_adapter.S3_BUCKET", "test-bucket"), patch(
            "app.s3_adapter.s3_client", None
        ):
            storage = S3Storage()
            assert storage.enabled is False

    def test_s3storage_init_fully_enabled(self):
        """Test S3Storage initialization when fully enabled."""
        with patch("app.s3_adapter.USE_S3", True), patch("app.s3_adapter.S3_BUCKET", "test-bucket"), patch(
            "app.s3_adapter.s3_client", Mock()
        ):
            storage = S3Storage()
            assert storage.enabled is True
            assert storage.bucket == "test-bucket"

    def test_key_generation_with_prefix(self):
        """Test key generation with prefix."""
        with patch("app.s3_adapter.S3_PREFIX", "uploads"):
            storage = S3Storage()
            key = storage._key("test/file.zip")
            assert key == "uploads/test/file.zip"

    def test_key_generation_without_prefix(self):
        """Test key generation without prefix."""
        with patch("app.s3_adapter.S3_PREFIX", ""):
            storage = S3Storage()
            key = storage._key("test/file.zip")
            assert key == "test/file.zip"

    def test_key_generation_strips_leading_slash(self):
        """Test key generation strips leading slash."""
        storage = S3Storage()
        key = storage._key("/test/file.zip")
        assert not key.startswith("/")


class TestS3StorageFileOperations:
    """Test S3Storage file operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_s3_client = Mock()
        self.storage = S3Storage()

    def test_put_file_disabled_storage(self):
        """Test put_file with disabled storage raises error."""
        self.storage.enabled = False

        file_obj = io.BytesIO(b"test content")

        with pytest.raises(RuntimeError, match="S3Storage not enabled"):
            self.storage.put_file(file_obj, "test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_put_file_success_basic(self, mock_client):
        """Test successful file upload with basic parameters."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        # Mock S3 responses
        mock_client.put_object.return_value = {"VersionId": "v123"}
        mock_client.head_object.return_value = {"ContentLength": 1024, "ContentType": "text/plain"}

        file_obj = io.BytesIO(b"test content")
        result = self.storage.put_file(file_obj, "test.txt", "text/plain")

        # Verify put_object call
        mock_client.put_object.assert_called_once()
        call_args = mock_client.put_object.call_args[1]
        assert call_args["Bucket"] == "test-bucket"
        assert call_args["Body"] == file_obj
        assert call_args["ContentType"] == "text/plain"

        # Verify head_object call
        mock_client.head_object.assert_called_once()

        # Verify result
        assert result["bucket"] == "test-bucket"
        assert result["version_id"] == "v123"
        assert result["size"] == 1024
        assert result["content_type"] == "text/plain"

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    @patch("app.s3_adapter.S3_SSE", "aws:kms")
    @patch(
        "app.s3_adapter.S3_KMS_KEY_ID", "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012",
    )
    @patch("app.s3_adapter.S3_ACL", "bucket-owner-full-control")
    def test_put_file_with_encryption_and_acl(self, mock_client):
        """Test file upload with encryption and ACL."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.put_object.return_value = {"VersionId": "v123"}
        mock_client.head_object.return_value = {
            "ContentLength": 1024,
            "ContentType": "application/zip",
        }

        file_obj = io.BytesIO(b"encrypted content")
        self.storage.put_file(file_obj, "encrypted.zip", "application/zip")

        call_args = mock_client.put_object.call_args[1]
        assert call_args["ServerSideEncryption"] == "aws:kms"
        assert call_args["SSEKMSKeyId"] == "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
        assert call_args["ACL"] == "bucket-owner-full-control"

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_put_file_no_version_id(self, mock_client):
        """Test file upload without version ID."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.put_object.return_value = {}  # No VersionId
        mock_client.head_object.return_value = {"ContentLength": 512}

        file_obj = io.BytesIO(b"content")
        result = self.storage.put_file(file_obj, "test.txt")

        assert result["version_id"] is None
        # Should call head_object without VersionId
        head_call_args = mock_client.head_object.call_args[1]
        assert "VersionId" not in head_call_args

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_put_file_s3_error(self, mock_client):
        """Test file upload with S3 error."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.put_object.side_effect = Exception("S3 Error")

        file_obj = io.BytesIO(b"content")

        with pytest.raises(Exception):
            self.storage.put_file(file_obj, "test.txt")

    def test_get_object_disabled_storage(self):
        """Test get_object with disabled storage raises error."""
        self.storage.enabled = False

        with pytest.raises(RuntimeError, match="S3Storage not enabled"):
            self.storage.get_object("test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_get_object_success(self, mock_client):
        """Test successful object retrieval."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        # Mock S3 response
        mock_body = Mock()
        mock_body.read.return_value = b"file content"
        mock_client.get_object.return_value = {
            "Body": mock_body,
            "ContentLength": 12,
            "ContentType": "text/plain",
        }

        body, meta = self.storage.get_object("test.txt")

        assert body == b"file content"
        assert meta["size"] == 12
        assert meta["content_type"] == "text/plain"

        # Verify get_object call
        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_get_object_with_version(self, mock_client):
        """Test object retrieval with version ID."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_body = Mock()
        mock_body.read.return_value = b"versioned content"
        mock_client.get_object.return_value = {
            "Body": mock_body,
            "ContentLength": 17,
            "ContentType": "application/octet-stream",
        }

        body, meta = self.storage.get_object("test.txt", "v123")

        assert body == b"versioned content"
        assert meta["content_type"] == "application/octet-stream"

        # Verify version ID included
        call_args = mock_client.get_object.call_args[1]
        assert call_args["VersionId"] == "v123"

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_get_object_missing_metadata(self, mock_client):
        """Test object retrieval with missing metadata."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_body = Mock()
        mock_body.read.return_value = b"content"
        mock_client.get_object.return_value = {
            "Body": mock_body,
            # Missing ContentLength and ContentType
        }

        body, meta = self.storage.get_object("test.txt")

        assert body == b"content"
        assert meta["size"] == len(b"content")  # Falls back to body length
        assert meta["content_type"] == "application/octet-stream"  # Default

    def test_generate_presigned_url_disabled_storage(self):
        """Test presigned URL generation with disabled storage."""
        self.storage.enabled = False

        with pytest.raises(RuntimeError, match="S3Storage not enabled"):
            self.storage.generate_presigned_url("test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_generate_presigned_url_success(self, mock_client):
        """Test successful presigned URL generation."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/signed-url"

        url = self.storage.generate_presigned_url("test.txt", expires_in=7200)

        assert url == "https://s3.amazonaws.com/signed-url"

        # Verify call
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object", Params={"Bucket": "test-bucket", "Key": "test.txt"}, ExpiresIn=7200,
        )

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_generate_presigned_url_with_version(self, mock_client):
        """Test presigned URL generation with version ID."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/versioned-url"

        self.storage.generate_presigned_url("test.txt", version_id="v123")

        # Verify version ID included in params
        call_args = mock_client.generate_presigned_url.call_args[1]
        assert call_args["Params"]["VersionId"] == "v123"

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_delete_object_success(self, mock_client):
        """Test successful object deletion."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        self.storage.delete_object("test.txt")

        mock_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_delete_object_with_version(self, mock_client):
        """Test object deletion with version ID."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        self.storage.delete_object("test.txt", "v123")

        call_args = mock_client.delete_object.call_args[1]
        assert call_args["VersionId"] == "v123"

    def test_delete_object_disabled_storage(self):
        """Test delete_object with disabled storage (should not raise)."""
        self.storage.enabled = False

        # Should not raise exception
        self.storage.delete_object("test.txt")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_delete_object_s3_error(self, mock_client):
        """Test object deletion with S3 error."""
        self.storage.enabled = True
        self.storage.bucket = "test-bucket"

        mock_client.delete_object.side_effect = Exception("S3 Delete Error")

        # Should not raise exception (error is logged)
        self.storage.delete_object("test.txt")


class TestS3ClientInitialization:
    """Test S3 client initialization scenarios."""

    @patch.dict("os.environ", {"USE_S3": "true", "S3_BUCKET_NAME": "test-bucket"})
    @patch("boto3.client")
    def test_s3_client_initialization_success(self, mock_boto_client):
        """Test successful S3 client initialization."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client

        # Reload module to trigger initialization
        import importlib

        import app.s3_adapter

        importlib.reload(app.s3_adapter)

        mock_boto_client.assert_called_once_with("s3", region_name="us-east-2")
        assert app.s3_adapter.s3_client == mock_client

    @patch.dict("os.environ", {"USE_S3": "true"})
    @patch("boto3.client")
    def test_s3_client_initialization_failure(self, mock_boto_client):
        """Test S3 client initialization failure."""
        mock_boto_client.side_effect = Exception("Boto3 import error")

        # Reload module to trigger initialization
        import importlib

        import app.s3_adapter

        importlib.reload(app.s3_adapter)

        # Should disable S3 on failure
        assert app.s3_adapter.USE_S3 is False


class TestErrorHandlingScenarios:
    """Test various error handling scenarios."""

    def test_put_file_precondition_checks(self):
        """Test put_file precondition validation."""
        storage = S3Storage()

        # Test with disabled storage
        storage.enabled = False
        with pytest.raises(RuntimeError):
            storage.put_file(io.BytesIO(b"test"), "test.txt")

        # Test with missing client
        storage.enabled = True
        with patch("app.s3_adapter.s3_client", None):
            with pytest.raises(RuntimeError):
                storage.put_file(io.BytesIO(b"test"), "test.txt")

        # Test with missing bucket
        storage.bucket = None
        with patch("app.s3_adapter.s3_client", Mock()):
            with pytest.raises(RuntimeError):
                storage.put_file(io.BytesIO(b"test"), "test.txt")

    def test_edge_case_content_length_handling(self):
        """Test edge cases in content length handling."""
        storage = S3Storage()
        storage.enabled = True
        storage.bucket = "test-bucket"

        with patch("app.s3_adapter.s3_client") as mock_client:
            mock_body = Mock()
            mock_body.read.return_value = b"test content"

            # Test with None ContentLength
            mock_client.get_object.return_value = {
                "Body": mock_body,
                "ContentLength": None,
                "ContentType": "text/plain",
            }

            body, meta = storage.get_object("test.txt")
            assert meta["size"] == len(b"test content")

    @patch("app.s3_adapter.s3_client")
    @patch("app.s3_adapter.S3_BUCKET", "test-bucket")
    def test_put_file_exception_handling_with_body_cleanup(self, mock_client):
        """Test put_file exception handling with body parameter cleanup."""
        storage = S3Storage()
        storage.enabled = True
        storage.bucket = "test-bucket"

        # Mock put_object to raise exception
        mock_client.put_object.side_effect = Exception("S3 put error")

        file_obj = io.BytesIO(b"test content")

        with pytest.raises(Exception):
            storage.put_file(file_obj, "test.txt", "text/plain")

        # Exception should be raised, not silenced
        mock_client.put_object.assert_called_once()
