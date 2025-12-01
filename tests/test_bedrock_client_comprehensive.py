"""
Comprehensive tests for src.api.bedrock_client module.
Tests AWS Bedrock client functionality with complete mocking.
"""

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch


class TestBedrockClientImport(unittest.TestCase):
    """Test importing BedrockClient with dependency handling."""

    @patch.dict("sys.modules", {"boto3": MagicMock()})
    def test_import_bedrock_client_success(self):
        """Test successful import of BedrockClient."""
        from src.api.bedrock_client import BedrockClient

        self.assertIsNotNone(BedrockClient)

    def test_bedrock_client_class_exists(self):
        """Test BedrockClient class definition exists."""
        with patch.dict("sys.modules", {"boto3": MagicMock()}):
            from src.api.bedrock_client import BedrockClient

            self.assertTrue(callable(BedrockClient))


class TestBedrockClientInitialization(unittest.TestCase):
    """Test BedrockClient initialization scenarios."""

    @patch("boto3.client")
    def test_init_with_default_values(self, mock_boto_client):
        """Test initialization with default values."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        self.assertIsNone(client.model_id)
        self.assertIsNone(client.region)
        mock_boto_client.assert_called_once_with("bedrock-runtime", region_name=None)

    @patch("boto3.client")
    def test_init_with_explicit_values(self, mock_boto_client):
        """Test initialization with explicit model_id and region."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model", region="us-east-1")

        self.assertEqual(client.model_id, "test-model")
        self.assertEqual(client.region, "us-east-1")
        mock_boto_client.assert_called_once_with("bedrock-runtime", region_name="us-east-1")

    @patch.dict(os.environ, {"BEDROCK_MODEL_ID": "env-model", "AWS_REGION": "us-west-2"})
    @patch("boto3.client")
    def test_init_with_environment_variables(self, mock_boto_client):
        """Test initialization using environment variables."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        self.assertEqual(client.model_id, "env-model")
        self.assertEqual(client.region, "us-west-2")
        mock_boto_client.assert_called_once_with("bedrock-runtime", region_name="us-west-2")

    @patch("boto3.client")
    def test_init_explicit_overrides_environment(self, mock_boto_client):
        """Test that explicit values override environment variables."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        with patch.dict(os.environ, {"BEDROCK_MODEL_ID": "env-model", "AWS_REGION": "us-west-2"}):
            from src.api.bedrock_client import BedrockClient

            client = BedrockClient(model_id="override-model", region="override-region")

            self.assertEqual(client.model_id, "override-model")
            self.assertEqual(client.region, "override-region")
            mock_boto_client.assert_called_once_with(
                "bedrock-runtime", region_name="override-region"
            )


class TestBedrockClientSyncMethods(unittest.TestCase):
    """Test synchronous internal methods of BedrockClient."""

    @patch("boto3.client")
    def test_invoke_sync_successful_response(self, mock_boto_client):
        """Test successful synchronous invocation."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Mock response with streaming body
        mock_stream = MagicMock()
        mock_stream.read.return_value = b'{"result": "test response"}'
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        result = client._invoke_sync("test-model", b'{"input": "test"}')

        self.assertEqual(result, '{"result": "test response"}')
        mock_client.invoke_model.assert_called_once_with(
            modelId="test-model",
            contentType="application/json",
            accept="application/json",
            body=b'{"input": "test"}',
        )

    @patch("boto3.client")
    def test_invoke_sync_no_body_error(self, mock_boto_client):
        """Test error when no body in response."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.invoke_model.return_value = {"body": None}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        with self.assertRaises(RuntimeError) as context:
            client._invoke_sync("test-model", b'{"input": "test"}')

        self.assertEqual(str(context.exception), "No body in Bedrock response")

    @patch("boto3.client")
    def test_invoke_sync_decode_error_fallback(self, mock_boto_client):
        """Test fallback when UTF-8 decode fails."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Mock response with non-UTF-8 bytes
        mock_stream = MagicMock()
        mock_stream.read.return_value = b"\xff\xfe\x00\x00"  # Invalid UTF-8
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        result = client._invoke_sync("test-model", b'{"input": "test"}')

        # Should fallback to str() representation
        self.assertEqual(result, "b'\\xff\\xfe\\x00\\x00'")


class TestBedrockClientAsyncMethods(unittest.TestCase):
    """Test async methods of BedrockClient."""

    def setUp(self):
        """Set up test environment."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up test environment."""
        self.loop.close()

    @patch("boto3.client")
    def test_chat_successful(self, mock_boto_client):
        """Test successful chat method."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        mock_stream = MagicMock()
        mock_stream.read.return_value = b"Test response from Bedrock"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.chat("Hello, world!")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, "Test response from Bedrock")

    @patch("boto3.client")
    def test_chat_no_model_configured(self, mock_boto_client):
        """Test chat method with no model configured."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()  # No model_id

        async def run_test():
            with self.assertRaises(ValueError) as context:
                await client.chat("Hello, world!")
            self.assertEqual(
                str(context.exception), "No Bedrock model id configured (BEDROCK_MODEL_ID)"
            )

        self.loop.run_until_complete(run_test())

    @patch("boto3.client")
    def test_chat_with_custom_model(self, mock_boto_client):
        """Test chat method with custom model override."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        mock_stream = MagicMock()
        mock_stream.read.return_value = b"Custom model response"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="default-model")

        async def run_test():
            result = await client.chat("Hello, world!", model="custom-model")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, "Custom model response")

        # Verify the custom model was used
        call_args = mock_client.invoke_model.call_args
        self.assertEqual(call_args[1]["modelId"], "custom-model")


class TestBedrockClientPerformanceClaims(unittest.TestCase):
    """Test get_performance_claims method."""

    def setUp(self):
        """Set up test environment."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up test environment."""
        self.loop.close()

    @patch("boto3.client")
    def test_get_performance_claims_successful_json(self, mock_boto_client):
        """Test successful performance claims extraction with valid JSON."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        json_response = (
            '{"mentions_benchmarks": 0.8, "has_metrics": 0.9, "claims": ["Fast"], "score": 0.85}'
        )
        mock_stream = MagicMock()
        mock_stream.read.return_value = json_response.encode()
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_performance_claims("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        expected = {
            "mentions_benchmarks": 0.8,
            "has_metrics": 0.9,
            "claims": ["Fast"],
            "score": 0.85,
        }
        self.assertEqual(result, expected)

    @patch("boto3.client")
    def test_get_performance_claims_json_with_extra_text(self, mock_boto_client):
        """Test performance claims extraction from response with extra text."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        response_with_extra = (
            'Here are the results: {"score": 0.7, "claims": ["Efficient"]} and that\'s it.'
        )
        mock_stream = MagicMock()
        mock_stream.read.return_value = response_with_extra.encode()
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_performance_claims("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        expected = {"score": 0.7, "claims": ["Efficient"]}
        self.assertEqual(result, expected)

    @patch("boto3.client")
    def test_get_performance_claims_fallback_default(self, mock_boto_client):
        """Test performance claims fallback to default when parsing fails."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Invalid JSON response
        mock_stream = MagicMock()
        mock_stream.read.return_value = b"Invalid JSON response"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_performance_claims("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        expected = {"mentions_benchmarks": 0.0, "has_metrics": 0.0, "claims": [], "score": 0.0}
        self.assertEqual(result, expected)


class TestBedrockClientReadmeClarity(unittest.TestCase):
    """Test get_readme_clarity method."""

    def setUp(self):
        """Set up test environment."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up test environment."""
        self.loop.close()

    @patch("boto3.client")
    def test_get_readme_clarity_direct_float(self, mock_boto_client):
        """Test readme clarity with direct float response."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        mock_stream = MagicMock()
        mock_stream.read.return_value = b"0.75"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_readme_clarity("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, 0.75)

    @patch("boto3.client")
    def test_get_readme_clarity_with_extra_text(self, mock_boto_client):
        """Test readme clarity extraction from response with extra text."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        mock_stream = MagicMock()
        mock_stream.read.return_value = b"The clarity score is 0.82 out of 1.0"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_readme_clarity("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, 0.82)

    @patch("boto3.client")
    def test_get_readme_clarity_fallback_default(self, mock_boto_client):
        """Test readme clarity fallback to default when parsing fails."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Response with no numbers
        mock_stream = MagicMock()
        mock_stream.read.return_value = b"Unable to determine clarity"
        mock_client.invoke_model.return_value = {"body": mock_stream}

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_readme_clarity("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, 0.5)

    @patch("boto3.client")
    def test_get_readme_clarity_exception_handling(self, mock_boto_client):
        """Test readme clarity exception handling."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Simulate exception in chat method
        mock_client.invoke_model.side_effect = Exception("Bedrock error")

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient(model_id="test-model")

        async def run_test():
            result = await client.get_readme_clarity("README content")
            return result

        result = self.loop.run_until_complete(run_test())
        self.assertEqual(result, 0.5)


class TestBedrockClientEdgeCases(unittest.TestCase):
    """Test edge cases and error scenarios."""

    def setUp(self):
        """Set up test environment."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up test environment."""
        self.loop.close()

    @patch("boto3.client")
    def test_bedrock_client_attributes(self, mock_boto_client):
        """Test BedrockClient has expected attributes."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        self.assertTrue(hasattr(client, "model_id"))
        self.assertTrue(hasattr(client, "region"))
        self.assertTrue(hasattr(client, "_client"))
        self.assertTrue(hasattr(client, "_invoke_sync"))
        self.assertTrue(hasattr(client, "chat"))
        self.assertTrue(hasattr(client, "get_performance_claims"))
        self.assertTrue(hasattr(client, "get_readme_clarity"))

    @patch("boto3.client")
    def test_async_method_signatures(self, mock_boto_client):
        """Test that async methods have correct signatures."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        from src.api.bedrock_client import BedrockClient

        client = BedrockClient()

        import inspect

        # Check chat method
        chat_sig = inspect.signature(client.chat)
        self.assertIn("message", chat_sig.parameters)
        self.assertIn("model", chat_sig.parameters)

        # Check get_performance_claims method
        perf_sig = inspect.signature(client.get_performance_claims)
        self.assertIn("readme_text", perf_sig.parameters)

        # Check get_readme_clarity method
        clarity_sig = inspect.signature(client.get_readme_clarity)
        self.assertIn("readme_text", clarity_sig.parameters)


if __name__ == "__main__":
    unittest.main()
