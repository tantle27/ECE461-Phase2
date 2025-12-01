"""Focused tests for core.py functions to improve coverage."""

from unittest.mock import patch, MagicMock

from app.core import (
    _is_dangerous_regex,
    _safe_eval_with_timeout,
    _safe_int,
    _parse_bearer,
    _mint_token,
    _decode_token,
    list_artifacts,
    reset_storage,
    _to_openapi_model_rating,
    _STORE,
    _AUDIT_LOG
)
from app.scoring import ModelRating


class TestRegexSafety:
    """Test regex safety checking functionality."""

    def test_dangerous_regex_safe_patterns(self):
        """Test that safe regex patterns are not flagged as dangerous."""
        assert not _is_dangerous_regex("simple text")
        assert not _is_dangerous_regex("test.*pattern")
        assert not _is_dangerous_regex("a{1,5}")
        assert not _is_dangerous_regex("")  # Empty string
        assert not _is_dangerous_regex("normal{5,10}")  # Normal quantifier

    def test_dangerous_regex_dangerous_patterns(self):
        """Test that dangerous regex patterns are correctly flagged."""
        assert _is_dangerous_regex("a{999999}")  # Large single quantifier
        assert _is_dangerous_regex("a{1,999999}")  # Large upper bound
        assert _is_dangerous_regex("b{100000,}")  # Large lower bound


class TestTimeoutFunction:
    """Test the safe evaluation with timeout function."""

    def test_safe_eval_timeout_success(self):
        """Test timeout function with successful completion."""
        def quick_function():
            return "success"
        
        result = _safe_eval_with_timeout(quick_function, timeout=1.0)
        assert result == "success"

    def test_safe_eval_timeout_with_args(self):
        """Test timeout function with arguments."""
        def function_with_args(x, y):
            return x + y
        
        result = _safe_eval_with_timeout(function_with_args, 1.0, 5, 3)
        assert result == 8


class TestUtilityFunctions:
    """Test utility and helper functions."""

    def test_safe_int_valid(self):
        """Test _safe_int with valid integers."""
        assert _safe_int("123") == 123
        assert _safe_int("0") == 0
        assert _safe_int("-456") == -456

    def test_safe_int_invalid(self):
        """Test _safe_int with invalid input returns None."""
        assert _safe_int("abc") is None
        assert _safe_int("12.34") is None
        assert _safe_int("") is None
        assert _safe_int(None) is None

    def test_parse_bearer_valid(self):
        """Test bearer token parsing with valid input."""
        result = _parse_bearer("Bearer abc123")
        assert result == "abc123"

    def test_parse_bearer_invalid(self):
        """Test bearer token parsing with invalid input."""
        assert _parse_bearer("abc123") is None  # Missing Bearer prefix
        assert _parse_bearer("bearer abc123") is None  # Lowercase
        assert _parse_bearer("") is None
        assert _parse_bearer(None) is None


class TestTokenOperations:
    """Test token minting and decoding."""

    def test_mint_and_decode_token(self):
        """Test minting and decoding a token."""
        test_data = {"user": "test_user", "exp": 1234567890}
        
        # Mock the secret key
        with patch('app.core.SECRET_KEY', 'test_secret_key'):
            token = _mint_token(test_data)
            assert token is not None
            assert isinstance(token, str)
            
            # Decode the token
            decoded = _decode_token(token)
            assert decoded is not None
            assert decoded["user"] == "test_user"

    def test_decode_invalid_token(self):
        """Test decoding an invalid token."""
        with patch('app.core.SECRET_KEY', 'test_secret_key'):
            result = _decode_token("invalid.token.here")
            assert result is None


class TestDataConversion:
    """Test data conversion and transformation functions."""

    def test_to_openapi_model_rating(self):
        """Test conversion of ModelRating to OpenAPI format."""
        # Create a valid ModelRating object
        rating = ModelRating(
            id="test-123",
            generated_at="2023-01-01T00:00:00Z",
            scores={"quality": 0.8, "performance": 0.9},
            latencies={"total": 1.5},
            summary="Test summary"
        )
        
        result = _to_openapi_model_rating(rating)
        assert result is not None
        assert isinstance(result, dict)


class TestStorageOperations:
    """Test storage and state management."""

    def test_reset_storage(self):
        """Test storage reset functionality."""
        # Add some test data first
        _STORE["test"] = "data"
        _AUDIT_LOG.append("test entry")
        
        # Reset storage
        reset_storage()
        
        # Verify storage is empty
        assert len(_STORE) == 0
        assert len(_AUDIT_LOG) == 0

    def test_list_artifacts_empty(self):
        """Test listing artifacts when storage is empty."""
        reset_storage()  # Ensure clean state
        
        from app.core import ArtifactQuery
        query = ArtifactQuery(name=None, version=None, offset=0, limit=10)
        
        results = list_artifacts(query)
        assert results is not None
        assert len(results) == 0

    @patch('app.core._STORE', {'test-artifact': MagicMock()})
    def test_list_artifacts_with_data(self):
        """Test listing artifacts when there is data."""
        from app.core import ArtifactQuery
        query = ArtifactQuery(name=None, version=None, offset=0, limit=10)
        
        # Mock the artifact data
        mock_artifact = MagicMock()
        mock_artifact.metadata.name = "test-artifact"
        mock_artifact.metadata.version = "1.0.0"
        
        with patch('app.core._STORE', {'test-artifact': mock_artifact}):
            results = list_artifacts(query)
            assert results is not None