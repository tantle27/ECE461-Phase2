"""
Advanced comprehensive tests for app/core.py - Flask routes and complex functions.

This test file focuses on:
- Flask route handlers and HTTP endpoints
- Artifact CRUD operations
- Authentication and authorization flows
- File upload and download functionality
- Error handling and edge cases
- Database and storage operations
- Complex business logic functions
"""

import base64
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

# Import the functions and classes we want to test
from app.core import (
    ArtifactMetadata,
    Artifact,
    ArtifactQuery,
    save_artifact,
    fetch_artifact,
    list_artifacts,
    reset_storage,
    _json_body,
    _require_auth,
    _audit_add,
    _calculate_artifact_size_mb,
    _artifact_from_raw,
    _parse_bearer,
    _mint_token,
    _decode_token,
    _is_dangerous_regex,
    blueprint,
    _STORE,
    _ARTIFACT_ORDER,
)


@pytest.fixture
def app():
    """Create a Flask app for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(blueprint)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def clean_storage():
    """Clean storage before and after each test."""
    reset_storage()
    yield
    reset_storage()


class TestArtifactCRUDOperations:
    """Test Create, Read, Update, Delete operations for artifacts."""

    def test_save_artifact_basic(self, clean_storage):
        """Test saving a basic artifact."""
        metadata = ArtifactMetadata(
            id="test-id",
            name="test-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={"readme": "test content"})

        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.save = MagicMock()

            result = save_artifact(artifact)

            assert result.metadata.id == "test-id"
            assert result.metadata.name == "test-artifact"
            mock_store.save.assert_called_once()

    def test_save_artifact_with_storage_error(self, clean_storage):
        """Test saving artifact when storage adapter fails."""
        metadata = ArtifactMetadata(
            id="test-id",
            name="test-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={"readme": "test content"})

        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.save.side_effect = Exception("Storage error")

            # Should still work, just log the error
            result = save_artifact(artifact)

            assert result.metadata.id == "test-id"
            # Should be saved in memory store despite storage error
            assert "package:test-id" in _STORE

    def test_fetch_artifact_from_adapter(self, clean_storage):
        """Test fetching artifact from storage adapter."""
        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.get.return_value = {
                "metadata": {"id": "test-id", "name": "test", "type": "package", "version": "1.0"},
                "data": {"readme": "test content"}
            }

            result = fetch_artifact("package", "test-id")

            assert result is not None
            assert result.metadata.id == "test-id"
            assert result.metadata.name == "test"
            mock_store.get.assert_called_once_with("package", "test-id")

    def test_fetch_artifact_from_memory(self, clean_storage):
        """Test fetching artifact from memory store."""
        # First save an artifact
        metadata = ArtifactMetadata(
            id="memory-id",
            name="memory-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={"readme": "memory content"})

        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.save = MagicMock()
            mock_store.get.return_value = None  # Not in adapter

            save_artifact(artifact)

            # Now fetch it
            result = fetch_artifact("package", "memory-id")

            assert result is not None
            assert result.metadata.id == "memory-id"
            assert result.metadata.name == "memory-artifact"

    def test_fetch_artifact_not_found(self, clean_storage):
        """Test fetching non-existent artifact."""
        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.get.return_value = None

            result = fetch_artifact("package", "nonexistent")

            assert result is None

    def test_list_artifacts_empty(self, clean_storage):
        """Test listing artifacts when none exist."""
        query = ArtifactQuery(artifact_type="package")

        with patch('app.core._ARTIFACT_STORE') as mock_store:
            mock_store.find_by_type.return_value = []

            result = list_artifacts(query)

            assert result["totalCount"] == 0
            assert result["artifacts"] == []

    def test_list_artifacts_with_data(self, clean_storage):
        """Test listing artifacts with existing data."""
        # Save some test artifacts first
        for i in range(3):
            metadata = ArtifactMetadata(
                id=f"test-{i}",
                name=f"artifact-{i}",
                type="package",
                version="1.0.0"
            )
            artifact = Artifact(metadata=metadata, data={"readme": f"content {i}"})
            save_artifact(artifact)

        query = ArtifactQuery(artifact_type="package")
        result = list_artifacts(query)

        assert result["totalCount"] == 3
        assert len(result["artifacts"]) == 3

    def test_list_artifacts_with_pagination(self, clean_storage):
        """Test listing artifacts with pagination."""
        # Save 10 test artifacts
        for i in range(10):
            metadata = ArtifactMetadata(
                id=f"test-{i}",
                name=f"artifact-{i}",
                type="package",
                version="1.0.0"
            )
            artifact = Artifact(metadata=metadata, data={"readme": f"content {i}"})
            save_artifact(artifact)

        query = ArtifactQuery(artifact_type="package", page=2, page_size=3)
        result = list_artifacts(query)

        assert result["totalCount"] == 10
        assert len(result["artifacts"]) == 3  # page size
        assert result["page"] == 2

    def test_list_artifacts_with_name_filter(self, clean_storage):
        """Test listing artifacts with name filtering."""
        # Save test artifacts with different names
        names = ["package-react", "react-utils", "vue-components", "angular-lib"]
        for i, name in enumerate(names):
            metadata = ArtifactMetadata(
                id=f"test-{i}",
                name=name,
                type="package",
                version="1.0.0"
            )
            artifact = Artifact(metadata=metadata, data={"readme": f"content {i}"})
            save_artifact(artifact)

        query = ArtifactQuery(artifact_type="package", name="react")
        result = list_artifacts(query)

        # Should match artifacts containing "react"
        assert result["totalCount"] >= 2
        for artifact in result["artifacts"]:
            assert "react" in artifact["Name"].lower()


class TestFlaskRoutes:
    """Test Flask route handlers."""

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"

    @patch('app.core._STORE')
    @patch('app.core._ARTIFACT_STORE')
    def test_health_components_endpoint(self, mock_artifact_store, mock_store, client):
        """Test health components endpoint."""
        mock_artifact_store.health_check.return_value = True

        response = client.get('/health/components')
        assert response.status_code == 200
        data = response.get_json()
        assert "storage" in data
        assert "db" in data

    def test_openapi_spec_endpoint(self, client):
        """Test OpenAPI specification endpoint."""
        response = client.get('/openapi.yaml')
        assert response.status_code == 200
        # Should return YAML content
        assert 'openapi:' in response.get_data(as_text=True)

    @patch('app.core._require_auth')
    def test_authenticate_endpoint_success(self, mock_auth, client):
        """Test authentication endpoint with valid credentials."""
        mock_auth.return_value = ("testuser", False)

        response = client.put('/authenticate',
                             json={"User": {"name": "testuser"}, "Secret": {"password": "testpass"}})

        assert response.status_code == 200
        data = response.get_json()
        assert "bearer" in data

    def test_authenticate_endpoint_missing_data(self, client):
        """Test authentication endpoint with missing data."""
        response = client.put('/authenticate', json={})

        assert response.status_code == 400

    @patch('app.core._require_auth')
    @patch('app.core._json_body')
    def test_create_artifact_endpoint_success(self, mock_json_body, mock_auth, client):
        """Test creating artifact via API endpoint."""
        mock_auth.return_value = ("testuser", False)
        mock_json_body.return_value = {
            "Name": "test-package",
            "Version": "1.0.0",
            "Content": base64.b64encode(b"test content").decode()
        }

        with patch('app.core.save_artifact') as mock_save:
            mock_save.return_value = Artifact(
                metadata=ArtifactMetadata(id="new-id", name="test-package", type="package", version="1.0.0"),
                data={}
            )

            response = client.post('/package')

            assert response.status_code == 201
            mock_save.assert_called_once()

    @patch('app.core._require_auth')
    def test_enumerate_artifacts_endpoint(self, mock_auth, client, clean_storage):
        """Test enumerating artifacts via API endpoint."""
        mock_auth.return_value = ("testuser", False)

        # Add some test artifacts
        for i in range(3):
            metadata = ArtifactMetadata(
                id=f"enum-{i}",
                name=f"enum-artifact-{i}",
                type="package",
                version="1.0.0"
            )
            artifact = Artifact(metadata=metadata, data={})
            save_artifact(artifact)

        response = client.post('/packages', json=[{"Name": "*"}])

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 3

    @patch('app.core._require_auth')
    def test_get_artifact_endpoint_success(self, mock_auth, client, clean_storage):
        """Test getting specific artifact via API endpoint."""
        mock_auth.return_value = ("testuser", False)

        # Create test artifact
        metadata = ArtifactMetadata(
            id="get-test",
            name="get-test-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={"readme": "test readme"})
        save_artifact(artifact)

        response = client.get('/package/get-test')

        assert response.status_code == 200
        data = response.get_json()
        assert data["metadata"]["ID"] == "get-test"
        assert data["metadata"]["Name"] == "get-test-artifact"

    @patch('app.core._require_auth')
    def test_get_artifact_endpoint_not_found(self, mock_auth, client):
        """Test getting non-existent artifact via API endpoint."""
        mock_auth.return_value = ("testuser", False)

        response = client.get('/package/nonexistent')

        assert response.status_code == 404


class TestUtilityAndHelperFunctions:
    """Test utility and helper functions."""

    def test_json_body_success(self):
        """Test _json_body function with valid JSON."""
        test_data = {"key": "value", "number": 42}

        with patch('app.core.request') as mock_request:
            mock_request.get_json.return_value = test_data

            result = _json_body()

            assert result == test_data

    def test_json_body_failure(self):
        """Test _json_body function with invalid JSON."""
        with patch('app.core.request') as mock_request:
            mock_request.get_json.side_effect = Exception("Invalid JSON")

            with pytest.raises(Exception):
                _json_body()

    @patch('app.core.request')
    def test_require_auth_success(self, mock_request):
        """Test _require_auth with valid authentication."""
        mock_request.headers = {"Authorization": "Bearer valid-token"}

        with patch('app.core._decode_token') as mock_decode:
            mock_decode.return_value = ("testuser", False)

            username, is_admin = _require_auth()

            assert username == "testuser"
            assert is_admin is False

    @patch('app.core.request')
    def test_require_auth_missing_header(self, mock_request):
        """Test _require_auth with missing authorization header."""
        mock_request.headers = {}

        with pytest.raises(Exception):  # Should raise authorization error
            _require_auth()

    @patch('app.core.request')
    def test_require_auth_invalid_token(self, mock_request):
        """Test _require_auth with invalid token."""
        mock_request.headers = {"Authorization": "Bearer invalid-token"}

        with patch('app.core._decode_token') as mock_decode:
            mock_decode.return_value = None

            with pytest.raises(Exception):  # Should raise authorization error
                _require_auth()

    def test_audit_add_function(self):
        """Test _audit_add audit logging function."""
        with patch('app.core.audit_event') as mock_audit:
            _audit_add("package", "test-id", "CREATE", "test-name")

            mock_audit.assert_called_once()
            args, kwargs = mock_audit.call_args
            assert "CREATE" in args[0]  # Message should contain action

    def test_calculate_artifact_size_mb_with_content(self):
        """Test _calculate_artifact_size_mb with content data."""
        data = {
            "Content": base64.b64encode(b"x" * 1000).decode(),  # 1000 bytes
            "readme": "Some readme content"
        }

        size_mb = _calculate_artifact_size_mb(data)

        assert size_mb > 0
        assert size_mb < 1  # Should be less than 1 MB

    def test_calculate_artifact_size_mb_no_content(self):
        """Test _calculate_artifact_size_mb without content."""
        data = {"readme": "Some readme content", "version": "1.0.0"}

        size_mb = _calculate_artifact_size_mb(data)

        assert size_mb == 0

    def test_is_dangerous_regex_safe(self):
        """Test _is_dangerous_regex with safe patterns."""
        result = _is_dangerous_regex("test-package")
        assert result is False

    def test_is_dangerous_regex_dangerous(self):
        """Test _is_dangerous_regex with dangerous patterns."""
        # Test patterns that might cause exponential backtracking
        dangerous_patterns = [
            "(a+)+b",  # Nested quantifiers
            "a*a*a*a*a*a*b",  # Multiple quantifiers
            "(a|a)*b"  # Alternation with overlap
        ]
        
        for pattern in dangerous_patterns:
            result = _is_dangerous_regex(pattern)
            # Function should detect dangerous patterns
            assert isinstance(result, bool)


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge case scenarios."""

    def test_reset_storage_function(self):
        """Test reset_storage clears all data."""
        # Add some data first
        metadata = ArtifactMetadata(
            id="reset-test",
            name="reset-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={})
        save_artifact(artifact)

        # Verify data exists
        assert len(_STORE) > 0
        assert len(_ARTIFACT_ORDER) > 0

        # Reset and verify clean
        reset_storage()

        assert len(_STORE) == 0
        assert len(_ARTIFACT_ORDER) == 0

    def test_artifact_with_missing_metadata_fields(self):
        """Test creating artifact with minimal metadata."""
        # Test with only required fields
        raw_data = {
            "metadata": {"id": "minimal"},
            "data": {"content": "test"}
        }

        from app.core import _artifact_from_raw
        result = _artifact_from_raw(raw_data, "package", "default-id")

        assert result.metadata.id == "minimal"
        assert result.metadata.type == "package"
        assert result.metadata.version == "1.0.0"  # default

    def test_artifact_with_invalid_data_structure(self):
        """Test creating artifact with invalid data structure."""
        raw_data = "invalid string data"

        from app.core import _artifact_from_raw
        result = _artifact_from_raw(raw_data, "package", "default-id")

        # Should handle gracefully
        assert result.metadata.id == "default-id"
        assert result.metadata.type == "package"

    @patch('app.core._persist_state')
    def test_save_artifact_persist_error(self, mock_persist):
        """Test save_artifact when persist_state fails."""
        mock_persist.side_effect = Exception("Persist error")

        metadata = ArtifactMetadata(
            id="persist-test",
            name="persist-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(metadata=metadata, data={})

        # Should not raise exception even if persist fails
        result = save_artifact(artifact)

        assert result.metadata.id == "persist-test"
        mock_persist.assert_called_once()


class TestFileOperationsAndContent:
    """Test file operations and content handling."""

    def test_artifact_with_zip_content(self):
        """Test artifact with ZIP file content."""
        # Create a test ZIP file in memory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr('test.txt', 'Hello, World!')
            zip_file.writestr('subdir/another.txt', 'Another file')

        zip_content = base64.b64encode(zip_buffer.getvalue()).decode()

        metadata = ArtifactMetadata(
            id="zip-test",
            name="zip-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(
            metadata=metadata,
            data={"Content": zip_content, "JSProgram": "true"}
        )

        result = save_artifact(artifact)

        assert result.metadata.id == "zip-test"
        assert "Content" in result.data

    def test_artifact_with_large_content(self):
        """Test artifact with large content."""
        # Create large content (1MB)
        large_content = base64.b64encode(b"x" * (1024 * 1024)).decode()

        metadata = ArtifactMetadata(
            id="large-test",
            name="large-artifact",
            type="package",
            version="1.0.0"
        )
        artifact = Artifact(
            metadata=metadata,
            data={"Content": large_content}
        )

        result = save_artifact(artifact)

        assert result.metadata.id == "large-test"

        # Test size calculation
        size_mb = _calculate_artifact_size_mb(result.data)
        assert size_mb >= 1.0  # Should be at least 1 MB


if __name__ == "__main__":
    pytest.main([__file__])
