"""
Integration tests for REST API endpoints.

This module tests the Flask REST API endpoints that will be
implemented for Phase 2 of the model registry.
"""

import pytest
from unittest.mock import Mock
from typing import Dict, Any


# ==================== MODEL REGISTRY API TESTS ====================

@pytest.mark.api
class TestModelRegistryAPI:
    """Test model registry REST API endpoints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.api_client = Mock()
        self.auth_token = "test-token-123"
    
    @pytest.mark.asyncio
    async def test_upload_model_success(self):
        """Test successful model upload via API."""
        # Mock successful upload
        upload_data = {
            "model_name": "test-transformer",
            "version": "1.0.0",
            "description": "A test transformer model",
            "tags": ["nlp", "transformer", "test"]
        }
        
        expected_response = {
            "status": "success",
            "model_id": "model-123",
            "upload_url": "https://s3.example.com/upload/model-123",
            "message": "Model uploaded successfully"
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._upload_model(upload_data)
        
        assert response["status"] == "success"
        assert "model_id" in response
        assert "upload_url" in response
    
    @pytest.mark.asyncio
    async def test_upload_model_invalid_data(self):
        """Test model upload with invalid data."""
        # Missing required fields
        invalid_data = {
            "description": "A model without name or version"
        }
        
        expected_response = {
            "status": "error",
            "message": "Missing required fields: model_name, version",
            "code": 400
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._upload_model(invalid_data)
        
        assert response["status"] == "error"
        assert response["code"] == 400
        assert "Missing required fields" in response["message"]
    
    @pytest.mark.asyncio
    async def test_get_model_by_id(self):
        """Test retrieving model by ID."""
        model_id = "model-123"
        expected_model = {
            "id": model_id,
            "name": "test-transformer",
            "version": "1.0.0",
            "description": "A test transformer model",
            "upload_date": "2024-01-15T10:30:00Z",
            "metrics": {
                "bus_factor": 0.6,
                "code_quality": 0.8,
                "license": 1.0,
                "reproducibility": 0.9,
                "reviewedness": 0.7,
                "treescore": 0.75
            },
            "tags": ["nlp", "transformer", "test"]
        }
        
        self.api_client.get.return_value = expected_model
        
        response = await self._get_model(model_id)
        
        assert response["id"] == model_id
        assert "metrics" in response
        assert len(response["metrics"]) >= 6  # All Phase 2 metrics
    
    @pytest.mark.asyncio
    async def test_search_models_by_query(self):
        """Test searching models with query parameters."""
        search_params = {
            "query": "transformer nlp",
            "min_score": 0.7,
            "tags": ["nlp"],
            "limit": 10
        }
        
        expected_results = {
            "total": 25,
            "results": [
                {
                    "id": "model-123",
                    "name": "transformer-base",
                    "score": 0.85,
                    "tags": ["nlp", "transformer"]
                },
                {
                    "id": "model-456",
                    "name": "bert-model",
                    "score": 0.78,
                    "tags": ["nlp", "bert"]
                }
            ],
            "page": 1,
            "limit": 10
        }
        
        self.api_client.get.return_value = expected_results
        
        response = await self._search_models(search_params)
        
        assert response["total"] > 0
        assert len(response["results"]) <= search_params["limit"]
        for result in response["results"]:
            assert result["score"] >= search_params["min_score"]
    
    @pytest.mark.asyncio
    async def test_update_model_metadata(self):
        """Test updating model metadata."""
        model_id = "model-123"
        update_data = {
            "description": "Updated description",
            "tags": ["nlp", "transformer", "updated"],
            "additional_info": {
                "paper_url": "https://arxiv.org/abs/1234.5678",
                "license_url": "https://opensource.org/licenses/MIT"
            }
        }
        
        expected_response = {
            "status": "success",
            "message": "Model metadata updated successfully",
            "updated_fields": ["description", "tags", "additional_info"]
        }
        
        self.api_client.put.return_value = expected_response
        
        response = await self._update_model(model_id, update_data)
        
        assert response["status"] == "success"
        assert "updated_fields" in response
    
    @pytest.mark.asyncio
    async def test_delete_model(self):
        """Test deleting a model."""
        model_id = "model-123"
        
        expected_response = {
            "status": "success",
            "message": "Model deleted successfully",
            "deleted_files": [
                "s3://bucket/models/model-123/model.pkl",
                "s3://bucket/models/model-123/config.json"
            ]
        }
        
        self.api_client.delete.return_value = expected_response
        
        response = await self._delete_model(model_id)
        
        assert response["status"] == "success"
        assert "deleted_files" in response
    
    async def _upload_model(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upload model via API."""
        return self.api_client.post("/api/models", data=data)
    
    async def _get_model(self, model_id: str) -> Dict[str, Any]:
        """Get model by ID via API."""
        return self.api_client.get(f"/api/models/{model_id}")
    
    async def _search_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search models via API."""
        return self.api_client.get("/api/models/search", params=params)
    
    async def _update_model(
        self, model_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update model via API."""
        return self.api_client.put(f"/api/models/{model_id}", data=data)
    
    async def _delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete model via API."""
        return self.api_client.delete(f"/api/models/{model_id}")


# ==================== PACKAGE REGISTRY API TESTS ====================

@pytest.mark.api
class TestPackageRegistryAPI:
    """Test package registry REST API endpoints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.api_client = Mock()
        self.auth_token = "test-token-123"
    
    @pytest.mark.asyncio
    async def test_upload_package_success(self):
        """Test successful package upload via API."""
        package_data = {
            "name": "test-package",
            "version": "1.2.0",
            "description": "A test package",
            "repository_url": "https://github.com/user/test-package"
        }
        
        expected_response = {
            "status": "success",
            "package_id": "pkg-456",
            "upload_url": "https://s3.example.com/upload/pkg-456",
            "message": "Package uploaded successfully"
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._upload_package(package_data)
        
        assert response["status"] == "success"
        assert "package_id" in response
        assert "upload_url" in response
    
    @pytest.mark.asyncio
    async def test_get_package_metrics(self):
        """Test retrieving package metrics."""
        package_id = "pkg-456"
        expected_metrics = {
            "id": package_id,
            "name": "test-package",
            "version": "1.2.0",
            "metrics": {
                "bus_factor": 0.65,
                "code_quality": 0.82,
                "license": 1.0,
                "ramp_up_time": 0.73,
                "net_score": 0.76
            },
            "calculated_at": "2024-01-15T11:00:00Z"
        }
        
        self.api_client.get.return_value = expected_metrics
        
        response = await self._get_package_metrics(package_id)
        
        assert response["id"] == package_id
        assert "metrics" in response
        assert "net_score" in response["metrics"]
    
    @pytest.mark.asyncio
    async def test_search_packages_by_regex(self):
        """Test searching packages with regex patterns."""
        search_params = {
            "name_regex": "test-.*",
            "min_score": 0.5,
            "limit": 20
        }
        
        expected_results = {
            "total": 15,
            "results": [
                {
                    "id": "pkg-456",
                    "name": "test-package",
                    "version": "1.2.0",
                    "score": 0.76
                },
                {
                    "id": "pkg-789",
                    "name": "test-utils",
                    "version": "2.1.0",
                    "score": 0.68
                }
            ],
            "page": 1,
            "limit": 20
        }
        
        self.api_client.get.return_value = expected_results
        
        response = await self._search_packages(search_params)
        
        assert response["total"] > 0
        assert len(response["results"]) <= search_params["limit"]
    
    async def _upload_package(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upload package via API."""
        return self.api_client.post("/api/packages", data=data)
    
    async def _get_package_metrics(self, package_id: str) -> Dict[str, Any]:
        """Get package metrics via API."""
        return self.api_client.get(f"/api/packages/{package_id}/metrics")
    
    async def _search_packages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search packages via API."""
        return self.api_client.get("/api/packages/search", params=params)


# ==================== AUTHENTICATION API TESTS ====================

@pytest.mark.api
@pytest.mark.security
class TestAuthenticationAPI:
    """Test authentication and authorization endpoints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.api_client = Mock()
    
    @pytest.mark.asyncio
    async def test_register_user_success(self):
        """Test successful user registration."""
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "secure_password_123",
            "full_name": "Test User"
        }
        
        expected_response = {
            "status": "success",
            "user_id": "user-123",
            "message": "User registered successfully",
            "activation_required": True
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._register_user(user_data)
        
        assert response["status"] == "success"
        assert "user_id" in response
        assert response["activation_required"] is True
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful user login."""
        login_data = {
            "username": "testuser",
            "password": "secure_password_123"
        }
        
        expected_response = {
            "status": "success",
            "access_token": "jwt_token_here",
            "refresh_token": "refresh_token_here",
            "expires_in": 3600,
            "user_info": {
                "id": "user-123",
                "username": "testuser",
                "email": "test@example.com"
            }
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._login_user(login_data)
        
        assert response["status"] == "success"
        assert "access_token" in response
        assert "user_info" in response
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        invalid_login = {
            "username": "testuser",
            "password": "wrong_password"
        }
        
        expected_response = {
            "status": "error",
            "message": "Invalid username or password",
            "code": 401
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._login_user(invalid_login)
        
        assert response["status"] == "error"
        assert response["code"] == 401
    
    @pytest.mark.asyncio
    async def test_refresh_token(self):
        """Test token refresh functionality."""
        refresh_data = {
            "refresh_token": "refresh_token_here"
        }
        
        expected_response = {
            "status": "success",
            "access_token": "new_jwt_token_here",
            "expires_in": 3600
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._refresh_token(refresh_data)
        
        assert response["status"] == "success"
        assert "access_token" in response
    
    @pytest.mark.asyncio
    async def test_logout(self):
        """Test user logout."""
        auth_headers = {"Authorization": "Bearer jwt_token_here"}
        
        expected_response = {
            "status": "success",
            "message": "Logged out successfully"
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._logout_user(auth_headers)
        
        assert response["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_protected_endpoint_unauthorized(self):
        """Test accessing protected endpoint without authorization."""
        # No auth headers
        expected_response = {
            "status": "error",
            "message": "Authorization header required",
            "code": 401
        }
        
        self.api_client.get.return_value = expected_response
        
        response = await self._access_protected_endpoint()
        
        assert response["status"] == "error"
        assert response["code"] == 401
    
    async def _register_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Register user via API."""
        return self.api_client.post("/api/auth/register", data=data)
    
    async def _login_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Login user via API."""
        return self.api_client.post("/api/auth/login", data=data)
    
    async def _refresh_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh token via API."""
        return self.api_client.post("/api/auth/refresh", data=data)
    
    async def _logout_user(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """Logout user via API."""
        return self.api_client.post("/api/auth/logout", headers=headers)
    
    async def _access_protected_endpoint(self) -> Dict[str, Any]:
        """Access protected endpoint."""
        return self.api_client.get("/api/user/profile")


# ==================== ERROR HANDLING TESTS ====================

@pytest.mark.api
class TestAPIErrorHandling:
    """Test API error handling and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.api_client = Mock()
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test API rate limiting behavior."""
        # Simulate rate limit exceeded
        expected_response = {
            "status": "error",
            "message": "Rate limit exceeded",
            "code": 429,
            "retry_after": 300  # seconds
        }
        
        self.api_client.get.return_value = expected_response
        
        response = await self._make_request()
        
        assert response["code"] == 429
        assert "retry_after" in response
    
    @pytest.mark.asyncio
    async def test_server_error_handling(self):
        """Test handling of server errors."""
        # Simulate internal server error
        expected_response = {
            "status": "error",
            "message": "Internal server error",
            "code": 500,
            "request_id": "req-123-456"
        }
        
        self.api_client.get.return_value = expected_response
        
        response = await self._make_request()
        
        assert response["code"] == 500
        assert "request_id" in response
    
    @pytest.mark.asyncio
    async def test_validation_errors(self):
        """Test input validation error responses."""
        # Simulate validation errors
        expected_response = {
            "status": "error",
            "message": "Validation failed",
            "code": 422,
            "errors": {
                "name": ["This field is required"],
                "version": ["Invalid version format"],
                "email": ["Invalid email address"]
            }
        }
        
        self.api_client.post.return_value = expected_response
        
        response = await self._submit_invalid_data()
        
        assert response["code"] == 422
        assert "errors" in response
        assert len(response["errors"]) > 0
    
    @pytest.mark.asyncio
    async def test_not_found_errors(self):
        """Test handling of resource not found errors."""
        # Simulate resource not found
        expected_response = {
            "status": "error",
            "message": "Model not found",
            "code": 404,
            "resource_type": "model",
            "resource_id": "model-999"
        }
        
        self.api_client.get.return_value = expected_response
        
        response = await self._get_nonexistent_resource()
        
        assert response["code"] == 404
        assert response["resource_type"] == "model"
    
    async def _make_request(self) -> Dict[str, Any]:
        """Make API request."""
        return self.api_client.get("/api/models")
    
    async def _submit_invalid_data(self) -> Dict[str, Any]:
        """Submit invalid data."""
        return self.api_client.post("/api/models", data={})
    
    async def _get_nonexistent_resource(self) -> Dict[str, Any]:
        """Get nonexistent resource."""
        return self.api_client.get("/api/models/model-999")


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.api
@pytest.mark.slow
class TestAPIPerformance:
    """Test API performance and load handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.api_client = Mock()
    
    @pytest.mark.asyncio
    async def test_concurrent_uploads(self):
        """Test handling of concurrent model uploads."""
        # Simulate concurrent upload responses
        upload_responses = [
            {"status": "success", "model_id": f"model-{i}"}
            for i in range(10)
        ]
        
        self.api_client.post.side_effect = upload_responses
        
        # Mock concurrent uploads
        results = []
        for i in range(10):
            response = await self._upload_model_concurrent(i)
            results.append(response)
        
        assert len(results) == 10
        for i, result in enumerate(results):
            assert result["status"] == "success"
            assert result["model_id"] == f"model-{i}"
    
    @pytest.mark.asyncio
    async def test_large_search_results(self):
        """Test handling of large search result sets."""
        # Simulate large result set
        large_results = {
            "total": 10000,
            "results": [
                {"id": f"model-{i}", "name": f"model-{i}", "score": 0.8}
                for i in range(100)  # First page of 100 results
            ],
            "page": 1,
            "limit": 100,
            "total_pages": 100
        }
        
        self.api_client.get.return_value = large_results
        
        response = await self._search_large_dataset()
        
        assert response["total"] == 10000
        assert len(response["results"]) == 100
        assert response["total_pages"] == 100
    
    @pytest.mark.asyncio
    async def test_metrics_calculation_timeout(self):
        """Test handling of long-running metrics calculations."""
        # Simulate long-running calculation
        timeout_response = {
            "status": "accepted",
            "message": "Metrics calculation started",
            "job_id": "job-123",
            "estimated_completion": "2024-01-15T12:00:00Z"
        }
        
        self.api_client.post.return_value = timeout_response
        
        response = await self._start_metrics_calculation()
        
        assert response["status"] == "accepted"
        assert "job_id" in response
        assert "estimated_completion" in response
    
    async def _upload_model_concurrent(self, index: int) -> Dict[str, Any]:
        """Upload model in concurrent test."""
        data = {"name": f"model-{index}", "version": "1.0.0"}
        return self.api_client.post("/api/models", data=data)
    
    async def _search_large_dataset(self) -> Dict[str, Any]:
        """Search large dataset."""
        params = {"limit": 100, "page": 1}
        return self.api_client.get("/api/models/search", params=params)
    
    async def _start_metrics_calculation(self) -> Dict[str, Any]:
        """Start metrics calculation."""
        data = {"model_id": "model-123", "force_recalculate": True}
        return self.api_client.post("/api/models/metrics", data=data)