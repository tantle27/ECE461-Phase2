from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.metrics.metrics_calculator import MetricsCalculator


@pytest.fixture
def mock_clients():
    """
    Fixture to create properly configured mock clients.
    It patches all API clients inside the metrics_calculator module,
    ensuring our calculator uses the mocks.
    """
    with patch('src.metrics.metrics_calculator.GitClient') as MockGitClient, \
         patch(
             'src.metrics.metrics_calculator.GenAIClient'
             ) as MockGenAIClient, \
         patch(
             'src.metrics.metrics_calculator.HuggingFaceClient'
             ) as MockHuggingFaceClient:

        mock_git = MockGitClient.return_value
        mock_genai = MockGenAIClient.return_value
        mock_hf = MockHuggingFaceClient.return_value

        yield {
            'git': mock_git,
            'genai': mock_genai,
            'hf': mock_hf
        }


@pytest.mark.asyncio
async def test_analyze_repository_success(mock_clients):
    """
    Tests the successful analysis path, ensuring positive scores are returned
    when mock data indicates a high-quality repository.
    """
    # Arrange: Configure mock data for a high-quality repository
    mock_git = mock_clients['git']
    mock_genai = mock_clients['genai']
    mock_hf = mock_clients['hf']

    mock_git.clone_repository.return_value = "/tmp/fake/repo"
    mock_git.analyze_commits.return_value = MagicMock(
        total_commits=100, contributors={'author1': 50, 'author2': 50}
    )
    mock_git.analyze_code_quality.return_value = MagicMock(
        lint_errors=0, has_tests=True
    )
    mock_git.read_readme.return_value = """
# Project Title

## License

This project is licensed under the MIT License.
    """.strip()
    mock_git.get_repository_size.return_value = {
        'raspberry_pi': 1.0,
        'jetson_nano': 1.0,
        'desktop_pc': 1.0,
        'aws_server': 1.0
    }

    # Mock GenAI client responses (async methods)
    mock_genai.get_performance_claims = AsyncMock(return_value={
        "has_metrics": 1, "mentions_benchmarks": 1
    })
    mock_genai.get_readme_clarity = AsyncMock(return_value=0.8)

    # Mock HuggingFace client responses (async methods)
    mock_hf.get_dataset_info = AsyncMock(return_value={
        'likes': 100, 'downloads': 1000
    })

    # **FIXED**: Use ThreadPoolExecutor in this test to
    # avoid pickling MagicMock objects.
    # Application's use of
    # ProcessPoolExecutor is still correct for production.
    with ThreadPoolExecutor() as pool:
        calculator = MetricsCalculator(pool)
        # Act
        result = await calculator.analyze_repository("http://test.url")

    # Assert
    assert result['bus_factor'] == 0.5
    assert result['code_quality'] == 1.0
    assert result['license'] == 1.0
    assert 'performance_claims' in result
    assert 'dataset_quality' in result
    mock_git.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_repository_clone_fails(mock_clients):
    """
    Tests the failure path where the git clone operation returns None.
    """
    # Arrange
    mock_git = mock_clients['git']
    mock_git.clone_repository.return_value = None

    # Using ThreadPoolExecutor here as well for consistency
    with ThreadPoolExecutor() as pool:
        calculator = MetricsCalculator(pool)
        # Act
        result = await calculator.analyze_repository("http://invalid.url")

    # Assert
    assert result['bus_factor'] == 0.0
    assert result['code_quality'] == 0.0
    assert result['license'] == 0.0
    # assert result['ramp_up_time'] == 0.0
    mock_git.cleanup.assert_not_called()
