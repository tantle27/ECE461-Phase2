import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import analyze_entry


@pytest.mark.asyncio
@patch('src.metrics.metrics_calculator.HuggingFaceClient')
@patch('src.metrics.metrics_calculator.GenAIClient')
@patch('src.metrics.metrics_calculator.GitClient')
async def test_parallelism_performance(
    MockGitClient, MockGenAIClient, MockHuggingFaceClient
):
    """
    Tests that processing entries concurrently is substantially
    faster than a sequential approach, validating the project's
    performance goals.
    """
    # Create test entries
    entries = [(f"https://github.com/test/repo{i}",
                None, f"https://huggingface.co/model{i}")
               for i in range(4)]
    encountered_datasets = set()

    # --- Mock API Clients ---

    # Mock GitClient
    mock_git_instance = MockGitClient.return_value

    def mock_clone(url):
        time.sleep(0.1)  # Simulate I/O delay
        return f"/tmp/{url.split('/')[-1]}"
    mock_git_instance.clone_repository.side_effect = mock_clone
    mock_git_instance.read_readme.return_value = "Mock README content"
    mock_git_instance.analyze_commits.return_value = MagicMock(
        total_commits=10, contributors={'a': 5, 'b': 5}
    )
    mock_git_instance.analyze_code_quality.return_value = MagicMock(
        lint_errors=5, has_tests=True
    )
    mock_git_instance.analyze_ramp_up_time.return_value = {
        'has_examples': True, 'has_dependencies': True
    }
    mock_git_instance.cleanup.return_value = None

    # Mock GenAIClient using AsyncMock for its methods
    mock_genai_instance = MockGenAIClient.return_value
    mock_genai_instance.get_readme_clarity = AsyncMock(return_value=0.85)
    mock_genai_instance.get_performance_claims = AsyncMock(return_value={
        "has_metrics": 1, "mentions_benchmarks": 1
    })

    # Mock HuggingFaceClient
    mock_hf_instance = MockHuggingFaceClient.return_value
    mock_hf_instance.get_dataset_info.return_value = {
        'likes': 100, 'downloads': 1000
    }

    # --- Test Sequential Execution ---
    start_time_seq = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entry in entries:
            await analyze_entry(entry, pool, encountered_datasets)
    sequential_time = time.time() - start_time_seq

    # --- Test Concurrent Execution ---
    start_time_para = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [analyze_entry(entry, pool, encountered_datasets)
                 for entry in entries]
        await asyncio.gather(*tasks)
    parallel_time = time.time() - start_time_para

    print(f"\nSequential-like execution time: {sequential_time:.4f}s")
    print(f"Concurrent execution time:      {parallel_time:.4f}s")

    speedup_ratio = sequential_time / parallel_time if parallel_time > 0 else 0
    print(f"Speedup ratio: {speedup_ratio:.2f}x")

    assert parallel_time < sequential_time, \
        f"Concurrent execution ({parallel_time:.4f}s) should be" \
        f"faster than sequential ({sequential_time:.4f}s)"
    assert parallel_time < sequential_time * 0.67, \
        f"Concurrent execution should be at least 1.5x faster. " \
        f"Got {speedup_ratio:.2f}x speedup."
