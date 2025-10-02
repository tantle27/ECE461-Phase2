import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src import main

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_url_file_success():
    """Tests URL parser correctly reads valid file with new format."""
    file_path = "test_urls.txt"
    entries_to_write = [
        ("https://github.com/test/repo1, "
         "https://huggingface.co/datasets/test, "
         "https://huggingface.co/model1"),
        ",,https://huggingface.co/model2"
    ]
    with open(file_path, "w") as f:
        for entry in entries_to_write:
            f.write(entry + "\n")

    parsed_entries = main.parse_url_file(file_path)
    expected = [
        ("https://github.com/test/repo1",
         "https://huggingface.co/datasets/test",
         "https://huggingface.co/model1"),
        (None, None, "https://huggingface.co/model2")
    ]
    assert parsed_entries == expected

    os.remove(file_path)


@pytest.mark.asyncio
async def test_process_entries():
    """
    Tests the async process_entries function to ensure it produces
    valid NDJSON output for each entry.
    """
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    entries = [
        ("https://github.com/test/repo1",
         None, "https://huggingface.co/model1"),
        (None, None, "https://huggingface.co/model2")
    ]

    # Mock the async analyze_entry function
    with patch('src.main.analyze_entry') as mock_analyze_entry:
        # Set up the mock to return different values for each call
        mock_analyze_entry.side_effect = [
            {"url": "https://huggingface.co/model1", "net_score": 0.5},
            {"url": "https://huggingface.co/model2", "net_score": 0.8},
        ]

        # Await the async function
        await main.process_entries(entries)

    sys.stdout = old_stdout

    output = captured_output.getvalue().strip().split('\n')
    assert len(output) == len(entries)

    # Verify that the mock was called for each entry
    assert mock_analyze_entry.call_count == len(entries)

    # Verify the output is valid NDJSON
    for line in output:
        try:
            json.loads(line)
        except json.JSONDecodeError:
            assert False, "Output is not valid NDJSON"


def test_parse_url_file_not_found():
    """
    Tests that the script exits with code 1 when the URL file is not found.
    """
    with pytest.raises(SystemExit) as e:
        main.parse_url_file("non_existent_file.txt")
    assert e.type == SystemExit
    assert e.value.code == 1


@pytest.mark.asyncio
@patch('src.metrics.metrics_calculator.MetricsCalculator.analyze_entry')
async def test_analyze_entry(mock_analyze_entry_method):
    """Tests the async analyze_entry function."""
    # Mock the return value of the underlying analysis
    mock_analyze_entry_method.return_value = {
        'bus_factor': 0.8,
        'code_quality': 0.9,
        'ramp_up_time': 0.7,
        'license': 1.0,
        'dataset_quality': 0.6,
        'performance_claims': 0.5,
        'dataset_and_code_score': 0.7,
    }
    entry = ("https://github.com/test/repo",
             None, "https://huggingface.co/model")
    encountered_datasets = set()

    with ProcessPoolExecutor() as pool:
        # Await the async function and pass the required process pool
        scorecard = await main.analyze_entry(entry, pool, encountered_datasets)

    assert 'net_score' in scorecard
    assert scorecard['net_score'] > 0
    mock_analyze_entry_method.assert_awaited_once()


def test_main_function_incorrect_args(monkeypatch):
    """
    Tests that the main function exits when called with incorrect arguments.
    """
    # Test with too many arguments (should exit with code 1)
    monkeypatch.setattr(sys, 'argv', ['src/main.py', 'file1.txt', 'file2.txt'])
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 1


@patch('src.main.parse_url_file')
@patch('src.main.process_entries')
def test_main_function_with_file(mock_process_entries, mock_parse_url):
    """Tests the main function with a file argument."""
    mock_parse_url.return_value = [
        ('https://github.com/test/repo',
         None, 'https://huggingface.co/model1'),
        (None, None, 'https://huggingface.co/model2')
    ]
    # Mock the async function as a MagicMock
    mock_process_entries = MagicMock()

    with patch('src.main.process_entries', mock_process_entries):
        with patch('asyncio.run') as mock_asyncio_run:
            with patch.object(sys, 'argv', ['src/main.py', 'some_file.txt']):
                main.main()

            mock_parse_url.assert_called_with('some_file.txt')
            # Check that asyncio.run was called with our mocked function
            mock_asyncio_run.assert_called_once()
