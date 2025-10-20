"""
Shared pytest fixtures and configuration for the ECE461-Phase2 project.

This file contains common fixtures used across all test modules,
including database setup, API clients, authentication, and test data.
"""

import asyncio
import os
import tempfile
from typing import Dict, Generator, Any
from unittest.mock import AsyncMock, MagicMock
import pytest
from concurrent.futures import ProcessPoolExecutor

# Import project modules for fixtures
from src.metrics.metrics_calculator import MetricsCalculator
from src.api.git_client import GitClient
from src.api.gen_ai_client import GenAIClient
from src.api.hugging_face_client import HuggingFaceClient


# ==================== ASYNC EVENT LOOP FIXTURES ====================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== DIRECTORY AND FILE FIXTURES ====================

@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def sample_url_file(temp_dir: str) -> str:
    """Create a sample URL file for testing."""
    file_path = os.path.join(temp_dir, "test_urls.txt")
    with open(file_path, "w") as f:
        f.write("https://github.com/test/repo1,"
                "https://huggingface.co/datasets/test,"
                "https://huggingface.co/model1\n")
        f.write(",,https://huggingface.co/model2\n")
        f.write("https://github.com/test/repo2,,"
                "https://huggingface.co/model3\n")
    return file_path


# ==================== API CLIENT FIXTURES ====================

@pytest.fixture
def mock_git_client():
    """Create a mock GitClient for testing."""
    client = MagicMock(spec=GitClient)
    client.clone_repository.return_value = "/tmp/test_repo"
    client.read_readme.return_value = (
        "# Test README\n\nThis is a test repository."
    )
    client.analyze_commits.return_value = MagicMock(
        total_commits=50,
        contributors={"author1": 25, "author2": 15, "author3": 10},
        bus_factor=0.6
    )
    client.analyze_code_quality.return_value = MagicMock(
        has_tests=True,
        lint_errors=2,
        code_quality_score=0.8
    )
    client.analyze_ramp_up_time.return_value = {
        'has_examples': True,
        'has_dependencies': True
    }
    client.cleanup.return_value = None
    return client


@pytest.fixture
def mock_gen_ai_client():
    """Create a mock GenAIClient for testing."""
    client = MagicMock(spec=GenAIClient)
    client.has_api_key = True
    client.get_readme_clarity = AsyncMock(return_value=0.75)
    client.get_performance_claims = AsyncMock(return_value={
        "has_metrics": 1,
        "mentions_benchmarks": 1,
        "claims": ["92% accuracy", "F1-score of 0.85"],
        "score": 1.0
    })
    return client


@pytest.fixture
def mock_hf_client():
    """Create a mock HuggingFaceClient for testing."""
    client = MagicMock(spec=HuggingFaceClient)
    client.get_dataset_info.return_value = {
        "normalized_likes": 0.8,
        "normalized_downloads": 0.9
    }
    client.download_file.return_value = "/tmp/test_model.bin"
    return client


# ==================== METRICS CALCULATOR FIXTURES ====================

@pytest.fixture
def process_pool():
    """Create a ProcessPoolExecutor for testing."""
    with ProcessPoolExecutor(max_workers=2) as pool:
        yield pool


@pytest.fixture
def metrics_calculator(
    process_pool, mock_git_client, mock_gen_ai_client, mock_hf_client
):
    """Create a MetricsCalculator with mocked dependencies."""
    calculator = MetricsCalculator(process_pool, github_token="fake_token")
    calculator.git_client = mock_git_client
    calculator.gen_ai_client = mock_gen_ai_client
    calculator.hf_client = mock_hf_client
    return calculator


# ==================== TEST DATA FIXTURES ====================

@pytest.fixture
def sample_scorecard() -> Dict[str, Any]:
    """Sample scorecard data for testing."""
    return {
        "name": "test-model",
        "category": "MODEL",
        "net_score": 0.75,
        "net_score_latency": 1500,
        "ramp_up_time": 0.8,
        "ramp_up_time_latency": 100,
        "bus_factor": 0.6,
        "bus_factor_latency": 200,
        "performance_claims": 0.9,
        "performance_claims_latency": 300,
        "license": 1.0,
        "license_latency": 50,
        "size_score": {
            "raspberry_pi": 0.5,
            "jetson_nano": 0.7,
            "desktop_pc": 1.0,
            "aws_server": 1.0
        },
        "size_score_latency": 75,
        "dataset_and_code_score": 0.85,
        "dataset_and_code_score_latency": 125,
        "dataset_quality": 0.7,
        "dataset_quality_latency": 150,
        "code_quality": 0.8,
        "code_quality_latency": 175
    }


@pytest.fixture
def sample_model_entries():
    """Sample model entries for testing."""
    return [
        (
            "https://github.com/test/repo1",
            "https://huggingface.co/datasets/test1",
            "https://huggingface.co/model1"
        ),
        (None, None, "https://huggingface.co/model2"),
        (
            "https://github.com/test/repo2",
            None,
            "https://huggingface.co/model3"
        )
    ]


# ==================== ENVIRONMENT FIXTURES ====================

@pytest.fixture
def clean_env():
    """Provide a clean environment for testing."""
    original_env = os.environ.copy()
    # Clear relevant environment variables
    env_vars_to_clear = [
        "GITHUB_TOKEN", "GENAI_API_KEY", "LOG_FILE", "LOG_LEVEL"
    ]
    for var in env_vars_to_clear:
        os.environ.pop(var, None)
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def test_env():
    """Set up test environment variables."""
    test_vars = {
        "GITHUB_TOKEN": "test_github_token",
        "GENAI_API_KEY": "test_genai_key",
        "LOG_LEVEL": "2",
        "LOG_FILE": "/tmp/test.log"
    }
    
    original_env = os.environ.copy()
    os.environ.update(test_vars)
    
    yield test_vars
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# ==================== BACKEND API FIXTURES (for Phase 2) ====================

@pytest.fixture
def mock_database():
    """Mock database connection for backend tests."""
    db = MagicMock()
    # Mock common database operations
    db.connect.return_value = True
    db.execute.return_value = {"status": "success"}
    db.fetch_all.return_value = []
    db.fetch_one.return_value = None
    db.close.return_value = None
    return db


@pytest.fixture
def mock_s3_client():
    """Mock AWS S3 client for file storage tests."""
    s3 = MagicMock()
    s3.upload_file.return_value = {"ETag": "test-etag"}
    s3.download_file.return_value = True
    s3.list_objects.return_value = {"Contents": []}
    s3.delete_object.return_value = {"DeleteMarker": True}
    return s3


@pytest.fixture
def mock_auth_token():
    """Mock authentication token for API tests."""
    return {
        "access_token": "test_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "user_id": "test_user_123",
        "permissions": ["upload", "download", "search"]
    }


@pytest.fixture
def sample_api_request():
    """Sample API request data for testing."""
    return {
        "model_name": "test-model",
        "version": "1.0.0",
        "description": "A test model for unit testing",
        "tags": ["test", "demo"],
        "license": "MIT",
        "size_bytes": 1024000
    }


# ==================== PYTEST MARKERS ====================

# Mark slow tests
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


# Skip slow tests by default in development
def pytest_collection_modifyitems(config, items):
    """Automatically mark slow tests."""
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(pytest.mark.slow)


# ==================== HELPER FUNCTIONS ====================

@pytest.fixture
def assert_scorecard_valid():
    """Helper function to validate scorecard structure."""
    def _assert_scorecard_valid(scorecard: Dict[str, Any]):
        """Assert that a scorecard has the required structure."""
        required_fields = [
            "name", "category", "net_score", "net_score_latency",
            "ramp_up_time", "bus_factor", "performance_claims",
            "license", "size_score", "dataset_quality", "code_quality"
        ]
        
        for field in required_fields:
            assert field in scorecard, f"Missing required field: {field}"
        
        # Validate score ranges (0.0 to 1.0)
        score_fields = [
            "net_score", "ramp_up_time", "bus_factor",
            "performance_claims", "license", "dataset_quality", "code_quality"
        ]
        
        for field in score_fields:
            if field in scorecard and scorecard[field] is not None:
                score_val = scorecard[field]
                assert 0.0 <= score_val <= 1.0, (
                    f"{field} score out of range: {score_val}"
                )
        
        # Validate latency fields (should be non-negative integers)
        latency_fields = [
            f"{field}_latency" for field in score_fields
            if f"{field}_latency" in scorecard
        ]
        for field in latency_fields:
            assert isinstance(scorecard[field], int), (
                f"{field} should be an integer"
            )
            assert scorecard[field] >= 0, f"{field} should be non-negative"
    
    return _assert_scorecard_valid