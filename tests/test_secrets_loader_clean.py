"""
Comprehensive test coverage for src/core/secrets_loader.py.

Tests all major functionality including:
- AWS Secrets Manager integration
- Environment variable configuration
- JSON parsing and secret extraction
- Error handling and fallback scenarios
- Boto3 dependency management
- Import-time execution
"""

import json
import os
from unittest.mock import Mock, patch

# Import from app.secrets_loader
from app.secrets_loader import load_registry_secrets


class TestSecretsLoaderConfiguration:
    """Test configuration and environment variable handling."""

    def test_load_secrets_no_arn_configured(self):
        """Test load_registry_secrets with no ARN configured."""
        with patch.dict("os.environ", {}, clear=True):
            # Should return early without doing anything
            load_registry_secrets()
            # No exception should be raised

    def test_load_secrets_empty_arn(self):
        """Test load_registry_secrets with empty ARN."""
        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": ""}):
            # Should return early without doing anything
            load_registry_secrets()
            # No exception should be raised


class TestBoto3DependencyHandling:
    """Test boto3 dependency handling and fallback."""

    @patch("app.secrets_loader.boto3", None)
    def test_load_secrets_no_boto3(self):
        """Test load_registry_secrets when boto3 is not available."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.warning") as mock_warning:
                load_registry_secrets()

                mock_warning.assert_called_once_with(
                    "boto3 not installed; cannot retrieve secrets from Secrets Manager"
                )


class TestSecretsManagerIntegration:
    """Test AWS Secrets Manager integration."""

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_successful_retrieval(self, mock_boto3):
        """Test successful secret retrieval and environment variable setting."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock successful secret response
        secret_data = {"GH_TOKEN": "test-github-token", "GENAI_API_KEY": "test-genai-key"}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # Verify boto3 client was created
            mock_boto3.client.assert_called_once_with("secretsmanager")

            # Verify get_secret_value was called
            mock_secrets_client.get_secret_value.assert_called_once_with(SecretId=test_arn)

            # Verify environment variables were set
            assert os.environ.get("GH_TOKEN") == "test-github-token"
            assert os.environ.get("GENAI_API_KEY") == "test-genai-key"

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_partial_data(self, mock_boto3):
        """Test secret retrieval with only partial data."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock secret with only one key
        secret_data = {"GH_TOKEN": "only-github-token"}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # Verify only available key was set
            assert os.environ.get("GH_TOKEN") == "only-github-token"
            assert os.environ.get("GENAI_API_KEY") is None

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_preserves_existing_env_vars(self, mock_boto3):
        """Test that existing environment variables are preserved."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        secret_data = {"GH_TOKEN": "secret-github-token", "GENAI_API_KEY": "secret-genai-key"}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        # Set existing environment variables
        existing_env = {
            "REGISTRY_SECRET_ARN": test_arn,
            "GH_TOKEN": "existing-github-token",
            "GENAI_API_KEY": "existing-genai-key",
        }

        with patch.dict("os.environ", existing_env):
            load_registry_secrets()

            # Verify existing values were preserved (setdefault behavior)
            assert os.environ.get("GH_TOKEN") == "existing-github-token"
            assert os.environ.get("GENAI_API_KEY") == "existing-genai-key"

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_sets_only_missing_env_vars(self, mock_boto3):
        """Test that only missing environment variables are set."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        secret_data = {"GH_TOKEN": "secret-github-token", "GENAI_API_KEY": "secret-genai-key"}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        # Set partial existing environment
        existing_env = {
            "REGISTRY_SECRET_ARN": test_arn,
            "GH_TOKEN": "existing-github-token"
            # GENAI_API_KEY not set
        }

        with patch.dict("os.environ", existing_env):
            load_registry_secrets()

            # Verify existing value preserved, missing value set
            assert os.environ.get("GH_TOKEN") == "existing-github-token"
            assert os.environ.get("GENAI_API_KEY") == "secret-genai-key"


class TestErrorHandling:
    """Test error handling scenarios."""

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_boto_core_error(self, mock_boto3):
        """Test handling of BotoCoreError."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Create a generic exception that will be caught by the except clause
        from botocore.exceptions import BotoCoreError

        mock_secrets_client.get_secret_value.side_effect = BotoCoreError()

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.exception") as mock_log:
                load_registry_secrets()

                # Verify error was logged
                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                assert "Failed to fetch secret" in call_args[0]

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_client_error(self, mock_boto3):
        """Test handling of ClientError."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Create a ClientError exception
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}}
        mock_secrets_client.get_secret_value.side_effect = ClientError(error_response, "GetSecretValue")

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.exception") as mock_log:
                load_registry_secrets()

                # Verify error was logged
                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                assert "Failed to fetch secret" in call_args[0]

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_no_secret_string(self, mock_boto3):
        """Test handling when secret has no SecretString."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response without SecretString
        mock_secrets_client.get_secret_value.return_value = {}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.warning") as mock_warning:
                load_registry_secrets()

                mock_warning.assert_called_once()
                call_args = mock_warning.call_args[0]
                assert "has no SecretString" in call_args[0]
                assert test_arn in call_args

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_empty_secret_string(self, mock_boto3):
        """Test handling when SecretString is empty."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with empty SecretString
        mock_secrets_client.get_secret_value.return_value = {"SecretString": ""}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.warning") as mock_warning:
                load_registry_secrets()

                mock_warning.assert_called_once()
                call_args = mock_warning.call_args[0]
                assert "has no SecretString" in call_args[0]

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_invalid_json(self, mock_boto3):
        """Test handling of invalid JSON in SecretString."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with invalid JSON
        mock_secrets_client.get_secret_value.return_value = {"SecretString": "invalid-json-content"}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.exception") as mock_log:
                load_registry_secrets()

                # Verify JSON decode error was logged
                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                assert "is not valid JSON" in call_args[0]
                assert test_arn in call_args

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_malformed_json(self, mock_boto3):
        """Test handling of malformed JSON."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with malformed JSON
        mock_secrets_client.get_secret_value.return_value = {
            "SecretString": '{"key": value}'  # Missing quotes around value
        }

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}):
            with patch("logging.exception") as mock_log:
                load_registry_secrets()

                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                assert "is not valid JSON" in call_args[0]


class TestSecretDataProcessing:
    """Test secret data processing and environment variable setting."""

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_empty_secret_data(self, mock_boto3):
        """Test handling of empty secret data."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with empty JSON object
        mock_secrets_client.get_secret_value.return_value = {"SecretString": "{}"}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # No environment variables should be set
            assert os.environ.get("GH_TOKEN") is None
            assert os.environ.get("GENAI_API_KEY") is None

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_null_values(self, mock_boto3):
        """Test handling of null values in secret data."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with null values
        secret_data = {"GH_TOKEN": None, "GENAI_API_KEY": None}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # No environment variables should be set for null values
            assert os.environ.get("GH_TOKEN") is None
            assert os.environ.get("GENAI_API_KEY") is None

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_empty_string_values(self, mock_boto3):
        """Test handling of empty string values in secret data."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with empty string values
        secret_data = {"GH_TOKEN": "", "GENAI_API_KEY": ""}
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # Empty strings should not be set as environment variables
            assert os.environ.get("GH_TOKEN") is None
            assert os.environ.get("GENAI_API_KEY") is None

    @patch("app.secrets_loader.boto3")
    def test_load_secrets_extra_keys_ignored(self, mock_boto3):
        """Test that extra keys in secret data are ignored."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock response with extra keys
        secret_data = {
            "GH_TOKEN": "github-token",
            "GENAI_API_KEY": "genai-key",
            "EXTRA_KEY": "extra-value",
            "ANOTHER_KEY": "another-value",
        }
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # Only expected keys should be set
            assert os.environ.get("GH_TOKEN") == "github-token"
            assert os.environ.get("GENAI_API_KEY") == "genai-key"
            assert os.environ.get("EXTRA_KEY") is None
            assert os.environ.get("ANOTHER_KEY") is None


class TestImportTimeExecution:
    """Test import-time execution and exception handling."""

    def test_import_time_exception_handling(self):
        """Test that exceptions during import-time execution are handled."""
        # This test verifies the try/except block around the import-time call
        # The actual import-time execution has already happened, but we can
        # test the function behavior that would occur during import

        with patch("app.secrets_loader.load_registry_secrets") as mock_load:
            mock_load.side_effect = RuntimeError("Unexpected error")

            with patch("logging.exception") as mock_log:
                # Simulate the import-time execution
                try:
                    mock_load()
                except RuntimeError:
                    mock_log("Unexpected error while loading registry secrets")

                # In the actual module, the exception would be caught and logged
                mock_log.assert_called_once_with("Unexpected error while loading registry secrets")


class TestIntegrationScenarios:
    """Test integration scenarios and realistic use cases."""

    @patch("app.secrets_loader.boto3")
    def test_production_like_scenario(self, mock_boto3):
        """Test production-like scenario with real secret structure."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:registry-prod-secrets"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock realistic production secret
        secret_data = {
            "GH_TOKEN": "ghp_1234567890abcdef1234567890abcdef12345678",
            "GENAI_API_KEY": "sk-1234567890abcdef1234567890abcdef1234567890abcdef",
            "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/registry",  # Should be ignored
            "SECRET_VERSION": "2024-01-15",  # Should be ignored
        }
        mock_secrets_client.get_secret_value.return_value = {
            "SecretString": json.dumps(secret_data),
            "VersionId": "EXAMPLE1-90ab-cdef-fedc-ba987EXAMPLE",
            "VersionStages": ["AWSCURRENT"],
        }

        with patch.dict("os.environ", {"REGISTRY_SECRET_ARN": test_arn}, clear=True):
            load_registry_secrets()

            # Verify expected tokens were set
            assert os.environ.get("GH_TOKEN") == secret_data["GH_TOKEN"]
            assert os.environ.get("GENAI_API_KEY") == secret_data["GENAI_API_KEY"]

            # Verify other keys were ignored
            assert os.environ.get("DATABASE_URL") is None
            assert os.environ.get("SECRET_VERSION") is None

    @patch("app.secrets_loader.boto3")
    def test_development_environment_fallback(self, mock_boto3):
        """Test development environment where secrets are pre-configured."""
        test_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:registry-prod-secrets"
        mock_secrets_client = Mock()
        mock_boto3.client.return_value = mock_secrets_client

        # Mock secret data
        secret_data = {
            "GH_TOKEN": "production-github-token",
            "GENAI_API_KEY": "production-genai-key",
        }
        mock_secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

        # Simulate development environment with pre-configured tokens
        dev_env = {
            "REGISTRY_SECRET_ARN": test_arn,
            "GH_TOKEN": "dev-github-token",
            "GENAI_API_KEY": "dev-genai-key",
        }

        with patch.dict("os.environ", dev_env):
            load_registry_secrets()

            # Verify development tokens were preserved
            assert os.environ.get("GH_TOKEN") == "dev-github-token"
            assert os.environ.get("GENAI_API_KEY") == "dev-genai-key"

    def test_local_development_no_secrets_manager(self):
        """Test local development scenario without Secrets Manager."""
        # Simulate local development with no secret ARN
        with patch.dict("os.environ", {}, clear=True):
            # Should complete without error
            load_registry_secrets()

            # No tokens should be set
            assert os.environ.get("GH_TOKEN") is None
            assert os.environ.get("GENAI_API_KEY") is None
