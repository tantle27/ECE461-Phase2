import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.gen_ai_client import GenAIClient


class TestGenAIClient:
    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    def test_init_sets_headers(self):
        client = GenAIClient()
        assert client.headers["Authorization"] == "Bearer test_key"
        assert client.headers["Content-Type"] == "application/json"
        assert client.url == (
            "https://genai.rcac.purdue.edu/api/chat/completions"
        )

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_post):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [
                {"message": {"content": "Hello, world!"}}
            ]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.chat("Hi")
        assert result == "Hello, world!"
        mock_post.assert_called_once()

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @pytest.mark.asyncio
    async def test_chat_error(self, mock_post):
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        with pytest.raises(Exception) as exc:
            await client.chat("Hi")
        assert "Error: 400" in str(exc.value)
        assert "Bad Request" in str(exc.value)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @pytest.mark.asyncio
    async def test_chat_authentication_failure_returns_default(
        self, mock_post
    ):
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.chat("Hi")

        assert result == (
            "No performance claims found in the documentation."
        )
        assert client.has_api_key is False

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @pytest.mark.asyncio
    async def test_chat_custom_model(self, mock_post):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [
                {"message": {"content": "Model response"}}
            ]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.chat("Test", model="custom-model")
        assert result == "Model response"

        # Verify the call was made with custom model
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "custom-model"

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims(self, mock_open, mock_post):
        # Mock file reading - need to handle two different files
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP responses - two calls for two-stage approach
        expected_dict = {
            "mentions_benchmarks": 0.8,
            "has_metrics": 0.6
        }

        # First response (extraction)
        extraction_response = "METRICS FOUND: accuracy 92%\n" \
                              "BENCHMARKS FOUND: SQuAD"
        mock_response1 = AsyncMock()
        mock_response1.status = 200
        mock_response1.json = AsyncMock(return_value={
            "choices": [
                {"message": {"content": extraction_response}}
            ]
        })

        # Second response (conversion to JSON)
        mock_response2 = AsyncMock()
        mock_response2.status = 200
        mock_response2.json = AsyncMock(return_value={
            "choices": [
                {"message": {"content": json.dumps(expected_dict)}}
            ]
        })

        mock_post.return_value.__aenter__.side_effect = [
            mock_response1,
            mock_response2,
        ]

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        # Verify the result is the expected dict
        assert result == expected_dict
        assert isinstance(result, dict)

        # Verify both files were opened
        assert mock_open.call_count == 2
        mock_open.assert_any_call(
            "src/api/performance_claims_extraction_prompt.txt", "r"
        )
        mock_open.assert_any_call(
            "src/api/performance_claims_conversion_prompt.txt", "r"
        )

        # Verify HTTP calls were made twice
        assert mock_post.call_count == 2

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims_with_markdown_code_block(
        self, mock_open, mock_post
    ):
        """Test get_performance_claims with JSON wrapped in
        markdown code blocks."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with JSON in markdown code block
        expected_dict = {"mentions_benchmarks": 1, "has_metrics": 0}
        response_content = (
            "Here is the analysis:\n"
            "```json\n"
            f"{json.dumps(expected_dict)}\n"
            "```\n"
            "Done."
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": response_content}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        assert result == expected_dict
        assert isinstance(result, dict)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims_with_nested_braces(
        self, mock_open, mock_post
    ):
        """Test get_performance_claims with nested JSON objects."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with nested JSON -
        # the regex should extract only the first level
        expected_dict = {"mentions_benchmarks": 1, "has_metrics": 1}
        response_content = (
            f'Analysis: {json.dumps(expected_dict)} and some nested object '
            f'{{"inner": {{"deep": "value"}}}}'
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": response_content}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        assert result == expected_dict
        assert isinstance(result, dict)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims_fallback_to_full_response(
        self, mock_open, mock_post
    ):
        """Test get_performance_claims falls back to
        parsing full response when no braces found."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with no braces -
        # should fall back to parsing entire response
        expected_dict = {"mentions_benchmarks": 0, "has_metrics": 1}
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": json.dumps(expected_dict)}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        assert result == expected_dict
        assert isinstance(result, dict)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims_invalid_extracted_json(
        self, mock_open, mock_post
    ):
        """Test get_performance_claims
        with invalid JSON in extracted braces."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with invalid JSON in braces
        response_content = (
            "Analysis result: {invalid_json_content} - not valid"
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": response_content}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        assert result == {
            "mentions_benchmarks": 0.0,
            "has_metrics": 0.0,
            "claims": [],
            "score": 0.0,
        }

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_performance_claims_invalid_full_response_json(
        self, mock_open, mock_post
    ):
        """Test get_performance_claims with invalid JSON
        in full response fallback."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Test prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with no braces and invalid JSON as fallback
        response_content = "This is not JSON at all"
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": response_content}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_performance_claims("README content")

        assert result == {
            "mentions_benchmarks": 0.0,
            "has_metrics": 0.0,
            "claims": [],
            "score": 0.0,
        }

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_direct_float_parsing(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity with direct float response."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with direct float
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "0.85"}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.85
        assert isinstance(result, float)

        # Verify file was opened correctly
        mock_open.assert_called_once_with(
            "src/api/readme_clarity_ai_prompt.txt", "r"
        )

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_with_whitespace(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity strips whitespace from
        direct float response."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with whitespace around float
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "  0.92  \n"}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.92
        assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_regex_extraction(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity with regex pattern matching."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with text containing float pattern
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [
                {
                    "message": {
                        "content": "The clarity score is 0.73."
                    }
                }
            ]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.73
        assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_perfect_score(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity with perfect score (1.0)."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "1.0"}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 1.0
        assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_zero_score(self, mock_open, mock_post):
        """Test get_readme_clarity with zero score (0.0)."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "0.0"}}]
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.0
        assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_realistic_responses(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity with realistic
        LLM responses following the prompt."""
        test_cases = [
            ("0.85", 0.85),  # Direct number as instructed
            ("0.0", 0.0),    # Minimum score
            ("1.0", 1.0),    # Maximum score
            ("0.67", 0.67),  # Mid-range score
            ("The clarity score is 0.73", 0.73),  # LLM adds some text
            ("Based on analysis: 0.91", 0.91),    # LLM prefixes
        ]

        for i, (content, expected) in enumerate(test_cases):
            # Mock file reading
            mock_file = MagicMock()
            mock_file.read.return_value = "Clarity prompt: "
            mock_open.return_value.__enter__.return_value = mock_file

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "choices": [{"message": {"content": content}}]
            })
            mock_post.return_value.__aenter__.return_value = mock_response

            client = GenAIClient()
            result = await client.get_readme_clarity("README content")

            assert result == expected, (
                f"Case {i}: '{content}' -> {expected}, got {result}'"
            )
            assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_decimal_formats(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity with various
        decimal formats that LLM might output."""
        test_cases = [
            ("0.0", 0.0),
            (".5", 0.5),         # Leading decimal point
            ("0.123456789", 0.123456789),  # High precision
            ("Quality: .99", 0.99),
            ("1", 1.0),          # Integer format for perfect score
        ]

        for i, (content, expected) in enumerate(test_cases):
            # Mock file reading
            mock_file = MagicMock()
            mock_file.read.return_value = "Clarity prompt: "
            mock_open.return_value.__enter__.return_value = mock_file

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "choices": [{"message": {"content": content}}]
            })
            mock_post.return_value.__aenter__.return_value = mock_response

            client = GenAIClient()
            result = await client.get_readme_clarity("README content")

            assert result == expected, (
                f"Case {i}: '{content}' -> {expected}, got {result}'"
            )
            assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_no_numbers_raises_exception(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity raises exception when no numbers found."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with no extractable numbers
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "The documentation quality is very poor"
                        }
                    }
                ]
            }
        )
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.5

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_llm_disobedience_fallback(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity handles case where
        LLM doesn't follow instructions perfectly."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Edge case: LLM provides a score but not exactly as instructed
        # This tests the decimal fallback regex
        # for extracting the first valid number
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "Score: 0.42 (based on analysis)"
                        }
                    }
                ]
            }
        )
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        assert result == 0.42
        assert isinstance(result, float)

    @patch.dict(os.environ, {"GENAI_API_KEY": "test_key"})
    @patch("aiohttp.ClientSession.post")
    @patch("builtins.open", create=True)
    @pytest.mark.asyncio
    async def test_get_readme_clarity_first_number_wins(
        self, mock_open, mock_post
    ):
        """Test get_readme_clarity extracts the first
        valid number when multiple exist."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "Clarity prompt: "
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock HTTP response with multiple numbers -
        # should take the first valid one
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "First score: 0.8, second score: 0.6"
                            )
                        }
                    }
                ]
            }
        )
        mock_post.return_value.__aenter__.return_value = mock_response

        client = GenAIClient()
        result = await client.get_readme_clarity("README content")

        # Should extract the first number (0.8)
        assert result == 0.8
        assert isinstance(result, float)
