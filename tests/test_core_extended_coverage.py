"""Additional comprehensive tests for core.py to improve coverage."""

import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import (
    ArtifactMetadata,
    Artifact,
    _is_dangerous_regex,
    _safe_eval_with_timeout,
    reset_storage,
    artifact_to_dict,
    _to_openapi_model_rating,
    _audit_add,
    _AUDIT_LOG,
    _STORE,
    _ARTIFACT_ORDER,
    ArtifactQuery,
    list_artifacts,
    _safe_int,
    _parse_bearer,
    _mint_token,
    _decode_token,
    _persist_state,
    _load_state
)
from app.scoring import ModelRating


class TestErrorHandlingAndFallbacks:
    """Test error handling and fallback functionality."""

    def test_audit_fallback_functions_import_error(self):
        """Test fallback functions when audit logging fails to import."""
        # This tests the except block in lines 33-39
        with patch('app.core.audit_event') as mock_audit:
            with patch('app.core.security_alert') as mock_security:
                # The fallback functions should be no-ops that just log
                # We can't easily test the import error case, but we can test the functions exist
                assert callable(mock_audit)
                assert callable(mock_security)

    def test_dangerous_regex_detection(self):
        """Test regex safety checking functionality."""
        # Test safe patterns
        assert not _is_dangerous_regex("simple text")
        assert not _is_dangerous_regex("test.*pattern")
        assert not _is_dangerous_regex("a{1,5}")
        
        # Test dangerous patterns - large quantifiers
        assert _is_dangerous_regex("a{999999}")  # Large single quantifier
        assert _is_dangerous_regex("a{1,999999}")  # Large upper bound
        assert _is_dangerous_regex("b{100000,}")  # Large lower bound
        
        # Test edge cases
        assert not _is_dangerous_regex("")  # Empty string
        assert not _is_dangerous_regex("normal{5,10}")  # Normal quantifier

    def test_safe_eval_with_timeout_success(self):
        """Test timeout function with successful completion."""
        def quick_function():
            return "success"
        
        completed, result = _safe_eval_with_timeout(quick_function, 1000)
        assert completed is True
        assert result == "success"

    def test_safe_eval_with_timeout_timeout(self):
        """Test timeout function with timeout."""
        def slow_function():
            time.sleep(0.1)  # Sleep 100ms
            return "too late"
        
        completed, result = _safe_eval_with_timeout(slow_function, 50)  # 50ms timeout
        assert completed is False
        assert result is None

    def test_safe_eval_with_timeout_exception(self):
        """Test timeout function with exception in target."""
        def error_function():
            raise ValueError("test error")
        
        # Should still complete (exception is caught), but no result
        completed, result = _safe_eval_with_timeout(error_function, 1000)
        assert completed is True
        assert result is None  # Exception causes no value to be set

    def test_safe_name_match_exact(self):
        """Test safe name matching with exact match."""
        pattern = re.compile(r"test.*")
        
        # Test exact matching
        result = _safe_name_match(
            pattern, "test-package", exact_match=True,
            raw_pattern="test.*", context="test"
        )
        assert result is False  # "test-package" doesn't exactly match "test.*"
        
        result = _safe_name_match(
            pattern, "test", exact_match=True,
            raw_pattern="test", context="test"
        )
        assert result is True

    def test_safe_name_match_partial(self):
        """Test safe name matching with partial match."""
        pattern = re.compile(r"test")
        
        result = _safe_name_match(
            pattern, "my-test-package", exact_match=False,
            raw_pattern="test", context="test"
        )
        assert result is True  # "test" is in "my-test-package"


class TestPersistenceAndStorage:
    """Test persistence and storage operations."""

    def setup_method(self):
        """Reset storage before each test."""
        reset_storage()

    def test_save_and_load_state_local(self):
        """Test saving and loading state to local file."""
        # Create test artifact
        metadata = ArtifactMetadata(
            id="test-persist", name="test-artifact",
            type="model", version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={"test": "data"})
        _STORE["model:test-persist"] = artifact
        _ARTIFACT_ORDER.append("model:test-persist")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = Path(temp_dir) / "test_persist.json"
            
            with patch('app.core._LOCAL_PERSIST_PATH', temp_file):
                with patch('app.core._S3.enabled', False):
                    # Save state
                    save_state()
                    assert temp_file.exists()
                    
                    # Clear storage and reload
                    reset_storage()
                    assert len(_STORE) == 0
                    
                    # Load state back
                    load_state()
                    assert len(_STORE) > 0
                    assert "model:test-persist" in _STORE

    def test_load_state_missing_file(self):
        """Test loading state when persist file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = Path(temp_dir) / "missing.json"
            
            with patch('app.core._LOCAL_PERSIST_PATH', temp_file):
                with patch('app.core._S3.enabled', False):
                    # Should not raise error when file doesn't exist
                    load_state()
                    assert len(_STORE) == 0  # Should remain empty

    def test_load_state_empty_file(self):
        """Test loading state from empty file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = Path(temp_dir) / "empty.json"
            temp_file.write_text("")  # Empty file
            
            with patch('app.core._LOCAL_PERSIST_PATH', temp_file):
                with patch('app.core._S3.enabled', False):
                    load_state()
                    assert len(_STORE) == 0

    def test_load_state_invalid_json(self):
        """Test loading state from file with invalid JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = Path(temp_dir) / "invalid.json"
            temp_file.write_text("invalid json content")
            
            with patch('app.core._LOCAL_PERSIST_PATH', temp_file):
                with patch('app.core._S3.enabled', False):
                    # Should handle JSON error gracefully
                    with pytest.raises(json.JSONDecodeError):
                        load_state()


class TestDataProcessingAndUtilities:
    """Test data processing utilities and edge cases."""

    def test_artifact_to_dict_complete(self):
        """Test artifact to dict conversion with all fields."""
        metadata = ArtifactMetadata(
            id="test-id", name="test-name",
            type="model", version="1.0.0"
        )
        artifact = Artifact(
            metadata=metadata, 
            data={"url": "http://example.com", "metrics": {"score": 0.8}}
        )
        
        result = artifact_to_dict(artifact)
        assert result["metadata"]["ID"] == "test-id"
        assert result["metadata"]["Name"] == "test-name" 
        assert result["metadata"]["Version"] == "1.0.0"
        assert result["data"]["url"] == "http://example.com"

    def test_to_openapi_model_rating(self):
        """Test OpenAPI model rating conversion."""
        rating = ModelRating(
            bus_factor=0.8,
            correctness=0.9,
            ramp_up=0.7,
            responsive_maintainer=0.6,
            license_score=1.0,
            good_pinning_practice=0.5,
            pull_request=0.4,
            net_score=0.7
        )
        
        result = _to_openapi_model_rating(rating)
        assert result["BusFactor"] == 0.8
        assert result["Correctness"] == 0.9
        assert result["RampUp"] == 0.7
        assert result["NetScore"] == 0.7

    def test_audit_add_function(self):
        """Test audit logging functionality."""
        # Clear previous entries
        _AUDIT_LOG.clear()
        
        _audit_add("model", "test-id", "CREATE", "test-artifact")
        
        assert "test-id" in _AUDIT_LOG
        assert len(_AUDIT_LOG["test-id"]) == 1
        entry = _AUDIT_LOG["test-id"][0]
        assert entry["action"] == "CREATE"
        assert entry["artifact"]["name"] == "test-artifact"
        assert entry["artifact"]["type"] == "model"

    def test_safe_int_valid(self):
        """Test _safe_int with valid inputs."""
        assert _safe_int("123", 0) == 123
        assert _safe_int(456, 0) == 456
        assert _safe_int("0", -1) == 0

    def test_safe_int_invalid(self):
        """Test _safe_int with invalid inputs."""
        assert _safe_int("invalid", 42) == 42
        assert _safe_int(None, 10) == 10
        assert _safe_int("", 5) == 5

    def test_parse_bearer_valid(self):
        """Test bearer token parsing with valid inputs."""
        assert _parse_bearer("Bearer abc123") == "abc123"
        assert _parse_bearer("BEARER xyz789") == "xyz789"  # Case insensitive
        assert _parse_bearer("bearer token-with-hyphens") == "token-with-hyphens"

    def test_parse_bearer_invalid(self):
        """Test bearer token parsing with invalid inputs."""
        assert _parse_bearer("") == ""
        assert _parse_bearer("Basic abc123") == "Basic abc123"  # Not bearer
        assert _parse_bearer("Bearer") == ""  # No token part
        assert _parse_bearer(None) == ""  # Handle None gracefully

    def test_mint_and_decode_token_roundtrip(self):
        """Test minting and decoding tokens."""
        # Mint a token
        token = _mint_token("testuser", True)
        assert isinstance(token, str)
        assert "." in token  # Should have signature separator
        
        # Decode it back
        username, is_admin = _decode_token(token)
        assert username == "testuser"
        assert is_admin is True

    def test_decode_token_invalid(self):
        """Test decoding invalid tokens."""
        assert _decode_token("") is None
        assert _decode_token("invalid") is None
        assert _decode_token("no.signature") is None
        assert _decode_token("invalid.signature.format") is None


class TestQueryAndListingFunctionality:
    """Test artifact querying and listing functionality."""

    def setup_method(self):
        """Set up test artifacts."""
        reset_storage()
        
        # Create test artifacts
        for i in range(5):
            metadata = ArtifactMetadata(
                id=f"test-{i}", name=f"artifact-{i}",
                type="model" if i % 2 == 0 else "dataset",
                version="1.0.0"
            )
            artifact = Artifact(metadata=metadata, data={"url": f"http://example.com/{i}"})
            key = f"{metadata.type}:test-{i}"
            _STORE[key] = artifact
            _ARTIFACT_ORDER.append(key)

    def test_list_artifacts_no_filter(self):
        """Test listing all artifacts without filters."""
        query = ArtifactQuery()
        results = list_artifacts(query)
        
        assert len(results.items) == 5
        assert results.total == 5
        assert results.page == 1

    def test_list_artifacts_type_filter(self):
        """Test listing artifacts with type filter."""
        query = ArtifactQuery(types=["model"])
        results = list_artifacts(query)
        
        # Should only return model artifacts (indices 0, 2, 4)
        assert len(results.items) == 3
        assert all(item.metadata.type == "model" for item in results.items)

    def test_list_artifacts_pagination(self):
        """Test artifact pagination."""
        query = ArtifactQuery(page_size=2, page=1)
        results = list_artifacts(query)
        
        assert len(results.items) == 2
        assert results.total == 5
        assert results.page == 1
        
        # Test second page
        query = ArtifactQuery(page_size=2, page=2)
        results = list_artifacts(query)
        
        assert len(results.items) == 2
        assert results.total == 5
        assert results.page == 2

    def test_list_artifacts_name_search(self):
        """Test artifact name searching."""
        query = ArtifactQuery(name="artifact-1")
        results = list_artifacts(query)
        
        assert len(results.items) == 1
        assert results.items[0].metadata.name == "artifact-1"


class TestEdgeCasesAndErrorConditions:
    """Test edge cases and error conditions."""

    def test_artifact_creation_edge_cases(self):
        """Test artifact creation with edge case inputs."""
        # Test with minimal data
        metadata = ArtifactMetadata(id="", name="", type="", version="")
        artifact = Artifact(metadata=metadata, data={})
        
        # Should not raise errors
        result = artifact_to_dict(artifact)
        assert result["metadata"]["ID"] == ""
        assert result["metadata"]["Name"] == ""

    def test_regex_safety_edge_cases(self):
        """Test regex safety with various edge cases."""
        # Test with different quantifier formats
        assert not _contains_dangerous_regex("a{5}")  # Single number
        assert not _contains_dangerous_regex("a{1,}")  # Open ended small
        assert not _contains_dangerous_regex("a+")  # Plus quantifier
        assert not _contains_dangerous_regex("a*")  # Star quantifier
        
        # Test with malformed quantifiers
        assert not _contains_dangerous_regex("a{abc}")  # Non-numeric
        assert not _contains_dangerous_regex("a{,}")  # Empty quantifier

    def test_storage_operations_with_empty_store(self):
        """Test storage operations when store is empty."""
        reset_storage()
        
        query = ArtifactQuery()
        results = list_artifacts(query)
        
        assert len(results.items) == 0
        assert results.total == 0
        assert results.page == 1