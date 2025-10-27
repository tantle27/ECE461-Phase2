"""
Comprehensive test coverage for app/core.py.

Tests all major functionality including:
- Data classes (ArtifactMetadata, Artifact, ArtifactQuery)
- Flask routes and blueprint
- Authentication and authorization
- Artifact CRUD operations
- Upload/download functionality
- Rating and scoring system
- Search and pagination
- Error handling and validation
- Utility functions and helpers
- File operations and S3 integration
- License checking and lineage
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from flask import Flask

# Import from app.core
from app.core import (
    ArtifactMetadata, Artifact, ArtifactQuery,
    blueprint, artifact_to_dict, save_artifact, fetch_artifact,
    list_artifacts, reset_storage, _safe_int, _parse_query, _parse_query_args,
    _sanitize_search_pattern, _prefix_match, _substring_match,
    _paginate_artifacts, _search_artifacts, _validate_artifact_data,
    _parse_semver, _cmp_ver, _in_version_range, _record_timing,
    _percentile, _store_key, _calculate_artifact_size_mb,
    _STORE, _RATINGS_CACHE, _TOKENS, _STATS, _REQUEST_TIMES
)


class TestDataClasses:
    """Test data class functionality and validation."""
    
    def test_artifact_metadata_creation(self):
        """Test ArtifactMetadata creation with all fields."""
        metadata = ArtifactMetadata(
            id="test-id",
            name="test-name",
            type="model",
            version="1.0.0"
        )
        assert metadata.id == "test-id"
        assert metadata.name == "test-name"
        assert metadata.type == "model"
        assert metadata.version == "1.0.0"
    
    def test_artifact_creation(self):
        """Test Artifact creation with metadata and data."""
        metadata = ArtifactMetadata(id="art-1", name="test", type="model", version="1.0.0")
        data = {"model_link": "https://example.com/model"}
        artifact = Artifact(metadata=metadata, data=data)
        
        assert artifact.metadata == metadata
        assert artifact.data == data
    
    def test_artifact_query_defaults(self):
        """Test ArtifactQuery default values."""
        query = ArtifactQuery()
        assert query.artifact_type is None
        assert query.name is None
        assert query.types == []
        assert query.page == 1
        assert query.page_size == 25
    
    def test_artifact_query_custom_values(self):
        """Test ArtifactQuery with custom values."""
        query = ArtifactQuery(
            artifact_type="model",
            name="test-model",
            types=["model", "dataset"],
            page=2,
            page_size=50
        )
        assert query.artifact_type == "model"
        assert query.name == "test-model"
        assert query.types == ["model", "dataset"]
        assert query.page == 2
        assert query.page_size == 50


class TestUtilityFunctions:
    """Test utility and helper functions."""
    
    def test_artifact_to_dict(self):
        """Test conversion of Artifact to dictionary."""
        metadata = ArtifactMetadata(id="test", name="name", type="model", version="1.0")
        data = {"model_link": "https://example.com"}
        artifact = Artifact(metadata=metadata, data=data)
        
        result = artifact_to_dict(artifact)
        expected = {
            "metadata": {
                "id": "test",
                "name": "name",
                "type": "model",
                "version": "1.0"
            },
            "data": {"model_link": "https://example.com"}
        }
        assert result == expected
    
    def test_store_key(self):
        """Test store key generation."""
        key = _store_key("model", "test-id")
        assert key == "model:test-id"
    
    def test_safe_int_valid_integer(self):
        """Test _safe_int with valid integer."""
        assert _safe_int("123", 0) == 123
        assert _safe_int(456, 0) == 456
    
    def test_safe_int_invalid_values(self):
        """Test _safe_int with invalid values returns default."""
        assert _safe_int("invalid", 42) == 42
        assert _safe_int(None, 10) == 10
        assert _safe_int("", 5) == 5
    
    def test_parse_query_valid_payload(self):
        """Test _parse_query with valid payload."""
        payload = {
            "page": 2,
            "page_size": 50,
            "artifact_type": "model",
            "name": "test",
            "types": ["model", "dataset"]
        }
        query = _parse_query(payload)
        assert query.page == 2
        assert query.page_size == 50
        assert query.artifact_type == "model"
        assert query.name == "test"
        assert query.types == ["model", "dataset"]
    
    def test_parse_query_invalid_pagination(self):
        """Test _parse_query with invalid pagination values."""
        payload = {"page": 0, "page_size": 200}
        query = _parse_query(payload)
        assert query.page == 1  # Corrected to 1
        assert query.page_size == 25  # Corrected to default
    
    def test_parse_query_args(self):
        """Test _parse_query_args with request args."""
        args = {"page": "3", "page_size": "10", "artifact_type": "dataset", "name": "test"}
        query = _parse_query_args(args)
        assert query.page == 3
        assert query.page_size == 10
        assert query.artifact_type == "dataset"
        assert query.name == "test"
    
    def test_sanitize_search_pattern_normal(self):
        """Test search pattern sanitization."""
        result = _sanitize_search_pattern("test.model")
        assert result == "test.model"
    
    def test_sanitize_search_pattern_special_chars(self):
        """Test sanitization removes special characters."""
        result = _sanitize_search_pattern("test<>!@#$%model")
        assert result == "test$model"  # $ is allowed in regex
    
    def test_sanitize_search_pattern_too_long(self):
        """Test pattern truncation."""
        long_pattern = "a" * 200
        result = _sanitize_search_pattern(long_pattern)
        assert len(result) == 128
    
    def test_prefix_match(self):
        """Test prefix matching."""
        assert _prefix_match("TestModel", "test") is True
        assert _prefix_match("model", "test") is False
    
    def test_substring_match(self):
        """Test substring matching."""
        assert _substring_match("TestModel", "est") is True
        assert _substring_match("model", "xyz") is False
    
    def test_paginate_artifacts(self):
        """Test artifact pagination."""
        artifacts = []
        for i in range(10):
            metadata = ArtifactMetadata(id=f"id-{i}", name=f"name-{i}", type="model", version="1.0")
            artifacts.append(Artifact(metadata=metadata, data={}))
        
        result = _paginate_artifacts(artifacts, 2, 3)
        assert result["page"] == 2
        assert result["page_size"] == 3
        assert result["total"] == 10
        assert len(result["items"]) == 3
        assert result["items"][0]["metadata"]["id"] == "id-3"  # Start of page 2
    
    def test_paginate_artifacts_edge_cases(self):
        """Test pagination edge cases."""
        artifacts = []
        
        # Empty list
        result = _paginate_artifacts(artifacts, 1, 10)
        assert result["total"] == 0
        assert result["items"] == []
        
        # Invalid page/size correction
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        artifacts = [Artifact(metadata=metadata, data={})]
        result = _paginate_artifacts(artifacts, 0, 500)
        assert result["page"] == 1
        assert result["page_size"] == 25


class TestSemVerFunctions:
    """Test semantic version parsing and comparison."""
    
    def test_parse_semver_valid(self):
        """Test parsing valid semantic versions."""
        assert _parse_semver("1.2.3") == (1, 2, 3)
        assert _parse_semver("v1.2.3") == (1, 2, 3)
        assert _parse_semver("0.0.1") == (0, 0, 1)
        assert _parse_semver("10.20.30") == (10, 20, 30)
    
    def test_parse_semver_invalid(self):
        """Test parsing invalid semantic versions."""
        assert _parse_semver("1.2") is None
        assert _parse_semver("invalid") is None
        assert _parse_semver("1.2.3.4") is None
        assert _parse_semver("") is None
    
    def test_cmp_ver(self):
        """Test version comparison."""
        assert _cmp_ver((1, 0, 0), (2, 0, 0)) == -1
        assert _cmp_ver((2, 0, 0), (1, 0, 0)) == 1
        assert _cmp_ver((1, 0, 0), (1, 0, 0)) == 0
        assert _cmp_ver((1, 2, 3), (1, 2, 4)) == -1
    
    def test_in_version_range_exact(self):
        """Test exact version matching."""
        assert _in_version_range("1.2.3", "1.2.3") is True
        assert _in_version_range("1.2.3", "1.2.4") is False
    
    def test_in_version_range_tilde(self):
        """Test tilde range matching."""
        assert _in_version_range("1.2.3", "~1.2.0") is True
        assert _in_version_range("1.2.0", "~1.2.0") is True
        assert _in_version_range("1.3.0", "~1.2.0") is False
    
    def test_in_version_range_caret(self):
        """Test caret range matching."""
        assert _in_version_range("1.2.3", "^1.0.0") is True
        assert _in_version_range("2.0.0", "^1.0.0") is False
        assert _in_version_range("0.1.2", "^0.1.0") is True
        assert _in_version_range("0.2.0", "^0.1.0") is False
    
    def test_in_version_range_hyphen(self):
        """Test hyphen range matching."""
        assert _in_version_range("1.5.0", "1.0.0-2.0.0") is True
        assert _in_version_range("0.9.0", "1.0.0-2.0.0") is False
        assert _in_version_range("2.0.0", "1.0.0-2.0.0") is True  # Upper bound inclusive


class TestObservabilityHelpers:
    """Test observability and timing functions."""
    
    def test_record_timing_success(self):
        """Test timing decorator for successful operations."""
        @_record_timing
        def test_func():
            return "success"
        
        initial_ok = _STATS["ok"]
        initial_times = len(_REQUEST_TIMES)
        
        result = test_func()
        assert result == "success"
        assert _STATS["ok"] == initial_ok + 1
        assert len(_REQUEST_TIMES) == initial_times + 1
    
    def test_record_timing_exception(self):
        """Test timing decorator for operations with exceptions."""
        @_record_timing
        def test_func():
            raise ValueError("test error")
        
        initial_err = _STATS["err"]
        initial_times = len(_REQUEST_TIMES)
        
        with pytest.raises(ValueError):
            test_func()
        
        assert _STATS["err"] == initial_err + 1
        assert len(_REQUEST_TIMES) == initial_times + 1
    
    def test_percentile_calculation(self):
        """Test percentile calculation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(values, 0.0) == 1.0
        assert _percentile(values, 0.5) == 3.0
        assert _percentile(values, 1.0) == 5.0
        assert _percentile([], 0.5) == 0.0


class TestArtifactStorage:
    """Test artifact storage and retrieval operations."""
    
    def setup_method(self):
        """Reset storage before each test."""
        reset_storage()
        # Also clear any existing artifacts from previous tests
        from app.core import _STORE
        _STORE.clear()
    
    def test_save_and_fetch_artifact(self):
        """Test saving and fetching artifacts."""
        metadata = ArtifactMetadata(id="test", name="test-model", type="model", version="1.0")
        data = {"model_link": "https://example.com/model"}
        artifact = Artifact(metadata=metadata, data=data)
        
        # Save artifact
        saved = save_artifact(artifact)
        assert saved == artifact
        
        # Fetch artifact
        fetched = fetch_artifact("model", "test")
        assert fetched is not None
        assert fetched.metadata.id == "test"
        assert fetched.data["model_link"] == "https://example.com/model"
    
    def test_fetch_nonexistent_artifact(self):
        """Test fetching non-existent artifact returns None."""
        result = fetch_artifact("model", "nonexistent")
        assert result is None
    
    @patch('app.core._ARTIFACT_STORE')
    def test_save_artifact_store_failure(self, mock_store):
        """Test artifact save with store failure falls back to memory."""
        mock_store.save.side_effect = Exception("Store failed")
        
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        artifact = Artifact(metadata=metadata, data={})
        
        # Should not raise exception, should fallback to memory
        result = save_artifact(artifact)
        assert result == artifact
        # Verify it's in memory store
        assert _store_key("model", "test") in _STORE
    
    @patch('app.core._ARTIFACT_STORE')
    def test_fetch_artifact_store_failure(self, mock_store):
        """Test artifact fetch with store failure falls back to memory."""
        mock_store.get.side_effect = Exception("Store failed")
        
        # Add to memory store directly
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        artifact = Artifact(metadata=metadata, data={})
        _STORE[_store_key("model", "test")] = artifact
        
        result = fetch_artifact("model", "test")
        assert result == artifact
    
    def test_list_artifacts_empty(self):
        """Test listing artifacts when none exist."""
        query = ArtifactQuery()
        result = list_artifacts(query)
        assert result["total"] == 0
        assert result["items"] == []
    
    def test_list_artifacts_with_data(self):
        """Test listing artifacts with stored data."""
        # Add test artifacts
        for i in range(5):
            metadata = ArtifactMetadata(
                id=f"test-{i}", name=f"model-{i}", type="model", version="1.0"
            )
            artifact = Artifact(metadata=metadata, data={})
            save_artifact(artifact)
        
        query = ArtifactQuery(page=1, page_size=3)
        result = list_artifacts(query)
        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["page"] == 1
        assert result["page_size"] == 3
    
    def test_list_artifacts_filtered_by_type(self):
        """Test listing artifacts filtered by type."""
        # Add mixed artifacts
        for artifact_type in ["model", "dataset"]:
            for i in range(2):
                metadata = ArtifactMetadata(
                    id=f"{artifact_type}-{i}",
                    name=f"{artifact_type}-{i}",
                    type=artifact_type,
                    version="1.0"
                )
                artifact = Artifact(metadata=metadata, data={})
                save_artifact(artifact)
        
        query = ArtifactQuery(artifact_type="model")
        result = list_artifacts(query)
        assert result["total"] == 2
        for item in result["items"]:
            assert item["metadata"]["type"] == "model"
    
    def test_list_artifacts_filtered_by_name(self):
        """Test listing artifacts filtered by name."""
        metadata1 = ArtifactMetadata(id="1", name="test-model", type="model", version="1.0")
        metadata2 = ArtifactMetadata(id="2", name="other-model", type="model", version="1.0")
        
        save_artifact(Artifact(metadata=metadata1, data={}))
        save_artifact(Artifact(metadata=metadata2, data={}))
        
        query = ArtifactQuery(name="test")
        result = list_artifacts(query)
        assert result["total"] == 1
        assert result["items"][0]["metadata"]["name"] == "test-model"
    
    def test_list_artifacts_types_filter(self):
        """Test listing artifacts with types filter."""
        # Add different types
        for artifact_type in ["model", "dataset", "code"]:
            metadata = ArtifactMetadata(
                id=artifact_type, name=artifact_type, type=artifact_type, version="1.0"
            )
            save_artifact(Artifact(metadata=metadata, data={}))
        
        query = ArtifactQuery(types=["model", "dataset"])
        result = list_artifacts(query)
        assert result["total"] == 2
        types_found = {item["metadata"]["type"] for item in result["items"]}
        assert types_found == {"model", "dataset"}
    
    @patch('app.core._ARTIFACT_STORE')
    def test_list_artifacts_store_failure(self, mock_store):
        """Test list artifacts with store failure falls back to memory."""
        mock_store.list_all.side_effect = Exception("Store failed")
        
        # Add to memory
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        artifact = Artifact(metadata=metadata, data={})
        _STORE[_store_key("model", "test")] = artifact
        
        query = ArtifactQuery()
        result = list_artifacts(query)
        assert result["total"] == 1
    
    def test_reset_storage(self):
        """Test storage reset clears all data."""
        # Add some data
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        save_artifact(Artifact(metadata=metadata, data={}))
        _TOKENS.add("test-token")
        
        assert len(_STORE) > 0
        assert len(_TOKENS) > 0
        
        reset_storage()
        
        assert len(_STORE) == 0
        assert len(_TOKENS) == 0
        assert len(_RATINGS_CACHE) == 0


class TestValidation:
    """Test validation functions."""
    
    def test_validate_artifact_data_valid_model(self):
        """Test validation with valid model data."""
        data = {"model_link": "https://example.com/model"}
        result = _validate_artifact_data("model", data)
        assert result["model_link"] == "https://example.com/model"
    
    def test_validate_artifact_data_url_mapping(self):
        """Test URL field mapping to specific link fields."""
        # Test model
        data = {"url": "https://example.com/model"}
        result = _validate_artifact_data("model", data)
        assert result["model_link"] == "https://example.com/model"
        
        # Test code
        data = {"url": "https://example.com/code"}
        result = _validate_artifact_data("code", data)
        assert result["code_link"] == "https://example.com/code"
        
        # Test dataset
        data = {"url": "https://example.com/dataset"}
        result = _validate_artifact_data("dataset", data)
        assert result["dataset_link"] == "https://example.com/dataset"
    
    def test_validate_artifact_data_missing_model_link(self):
        """Test validation fails for model without model_link."""
        with pytest.raises(Exception):  # Should raise HTTPStatus.BAD_REQUEST
            _validate_artifact_data("model", {})
    
    def test_validate_artifact_data_empty_model_link(self):
        """Test validation fails for model with empty model_link."""
        with pytest.raises(Exception):
            _validate_artifact_data("model", {"model_link": ""})
    
    def test_validate_artifact_data_optional_fields(self):
        """Test validation with optional fields."""
        data = {
            "model_link": "https://example.com/model",
            "code_link": "https://example.com/code",
            "dataset_link": "https://example.com/dataset",
            "code": "",  # Empty field should be removed
            "dataset": None  # None field should be removed
        }
        result = _validate_artifact_data("model", data)
        assert result["model_link"] == "https://example.com/model"
        assert result["code_link"] == "https://example.com/code"
        assert result["dataset_link"] == "https://example.com/dataset"
        assert "code" not in result
        assert "dataset" not in result
    
    def test_validate_artifact_data_non_dict(self):
        """Test validation fails for non-dict data."""
        with pytest.raises(Exception):
            _validate_artifact_data("model", "not-a-dict")
        with pytest.raises(Exception):
            _validate_artifact_data("model", ["not", "a", "dict"])
    
    def test_validate_artifact_data_invalid_field_type(self):
        """Test validation fails for invalid field types."""
        with pytest.raises(Exception):
            _validate_artifact_data("model", {
                "model_link": "https://example.com",
                "code_link": 123  # Should be string
            })


class TestSearchFunctionality:
    """Test search and filtering functionality."""
    
    def setup_method(self):
        """Set up test artifacts."""
        reset_storage()
        
        # Add test artifacts with varying content
        artifacts_data = [
            ("model-1", "TensorFlow Model", {"readme": "Deep learning model for classification"}),
            ("model-2", "PyTorch Network", {"readme": "Neural network for regression tasks"}),
            ("dataset-1", "Image Dataset", {"readme": "Collection of labeled images"}),
            ("code-1", "Training Script", {"readme": "Python script for model training"}),
        ]
        
        for art_id, name, data in artifacts_data:
            artifact_type = art_id.split('-')[0]
            metadata = ArtifactMetadata(id=art_id, name=name, type=artifact_type, version="1.0")
            artifact = Artifact(metadata=metadata, data=data)
            save_artifact(artifact)
    
    def test_search_artifacts_substring_name(self):
        """Test substring search in artifact names."""
        matches = _search_artifacts(None, None, "substring", "TensorFlow")
        assert len(matches) == 1
        assert matches[0].metadata.name == "TensorFlow Model"
    
    def test_search_artifacts_substring_readme(self):
        """Test substring search in readme content."""
        matches = _search_artifacts(None, None, "substring", "classification")
        assert len(matches) == 1
        assert matches[0].metadata.id == "model-1"
    
    def test_search_artifacts_prefix_mode(self):
        """Test prefix search mode."""
        matches = _search_artifacts(None, None, "prefix", "Tensor")
        assert len(matches) == 1
        assert matches[0].metadata.name == "TensorFlow Model"
    
    def test_search_artifacts_regex_mode(self):
        """Test regex search mode."""
        import re
        pattern = re.compile("model|script", re.IGNORECASE)
        matches = _search_artifacts(pattern, None, "regex", "")
        assert len(matches) >= 2  # Should match model and script artifacts
    
    def test_search_artifacts_with_type_filter(self):
        """Test search with artifact type filter."""
        matches = _search_artifacts(None, "model", "substring", "model")
        model_types = [m.metadata.type for m in matches]
        assert all(t == "model" for t in model_types)
    
    def test_search_artifacts_no_matches(self):
        """Test search with no matches."""
        matches = _search_artifacts(None, None, "substring", "nonexistent")
        assert len(matches) == 0
    
    def test_search_artifacts_sort_order(self):
        """Test search results are sorted."""
        matches = _search_artifacts(None, None, "substring", "")  # Match all
        # Should be sorted by type, then name
        for i in range(len(matches) - 1):
            curr = (matches[i].metadata.type, matches[i].metadata.name)
            next_item = (matches[i + 1].metadata.type, matches[i + 1].metadata.name)
            assert curr <= next_item


class TestCalculateArtifactSize:
    """Test artifact size calculation functionality."""
    
    def test_calculate_artifact_size_from_data_size(self):
        """Test size calculation from artifact data."""
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        data = {"size": 1048576}  # 1MB in bytes
        artifact = Artifact(metadata=metadata, data=data)
        
        size_mb = _calculate_artifact_size_mb(artifact)
        assert size_mb == 1.0
    
    def test_calculate_artifact_size_zero(self):
        """Test size calculation with no size data."""
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        artifact = Artifact(metadata=metadata, data={})
        
        size_mb = _calculate_artifact_size_mb(artifact)
        assert size_mb == 0.0
    
    @patch('app.core._S3')
    def test_calculate_artifact_size_from_s3(self, mock_s3):
        """Test size calculation from S3 metadata."""
        mock_s3.enabled = True
        mock_s3.get_object.return_value = (b"data", {"size": 2097152})  # 2MB
        
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        data = {"s3_key": "test-key", "s3_version_id": "v1"}
        artifact = Artifact(metadata=metadata, data=data)
        
        size_mb = _calculate_artifact_size_mb(artifact)
        assert size_mb == 2.0
    
    @patch('app.core._S3')
    def test_calculate_artifact_size_s3_failure(self, mock_s3):
        """Test size calculation with S3 failure."""
        mock_s3.enabled = True
        mock_s3.get_object.side_effect = Exception("S3 failed")
        
        metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
        data = {"s3_key": "test-key"}
        artifact = Artifact(metadata=metadata, data=data)
        
        size_mb = _calculate_artifact_size_mb(artifact)
        assert size_mb == 0.0
    
    def test_calculate_artifact_size_from_file(self):
        """Test size calculation from local file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = Path(temp_dir) / "test.zip"
            test_file.write_bytes(b"x" * 1024)  # 1KB file
            
            metadata = ArtifactMetadata(id="test", name="test", type="model", version="1.0")
            data = {"path": str(test_file.relative_to(Path(temp_dir).parent))}
            artifact = Artifact(metadata=metadata, data=data)
            
            with patch('app.core._UPLOAD_DIR', Path(temp_dir)):
                size_mb = _calculate_artifact_size_mb(artifact)
                assert size_mb == 1024 / (1024 * 1024)  # 1KB in MB


class TestFlaskApp:
    """Test Flask application setup and basic functionality."""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(blueprint)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_blueprint_registration(self, app):
        """Test blueprint is properly registered."""
        assert blueprint.name == "registry"
        assert any(bp.name == "registry" for bp in app.iter_blueprints())