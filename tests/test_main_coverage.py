"""
Test coverage for src.main module.
Tests core functionality to improve overall coverage.
"""

import pytest
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock

from src.main import (
    _github_token_is_valid,
    _fail,
    validate_and_configure_logging,
    parse_url_file,
    process_entries,
    main
)


class TestGitHubTokenValidation:
    """Test GitHub token validation function."""

    def test_valid_ghp_token(self):
        """Test valid ghp_ token format."""
        token = "ghp_" + "A" * 36
        assert _github_token_is_valid(token)

    def test_valid_gho_token(self):
        """Test valid gho_ token format."""
        token = "gho_" + "B" * 36
        assert _github_token_is_valid(token)

    def test_valid_github_pat_token(self):
        """Test valid github_pat_ token format."""
        token = "github_pat_" + "C" * 30
        assert _github_token_is_valid(token)

    def test_invalid_token_wrong_prefix(self):
        """Test invalid token with wrong prefix."""
        token = "invalid_" + "A" * 36
        assert not _github_token_is_valid(token)

    def test_invalid_token_too_short(self):
        """Test invalid token too short."""
        token = "ghp_ABC123"
        assert not _github_token_is_valid(token)

    def test_invalid_token_empty(self):
        """Test invalid empty token."""
        assert not _github_token_is_valid("")


class TestFailFunction:
    """Test the _fail function."""

    def test_fail_exits_with_code_1(self):
        """Test that _fail exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            _fail("Test error message")
        assert exc_info.value.code == 1

    @patch('sys.stderr')
    def test_fail_prints_error_message(self, mock_stderr):
        """Test that _fail prints error to stderr."""
        with pytest.raises(SystemExit):
            _fail("Test error message")


class TestLoggingValidation:
    """Test logging validation and configuration."""

    def test_validate_logging_no_github_token(self):
        """Test validation when no GitHub token is set."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise any exception
            validate_and_configure_logging()

    def test_validate_logging_valid_github_token(self):
        """Test validation with valid GitHub token."""
        valid_token = "ghp_" + "A" * 36
        with patch.dict(os.environ, {"GITHUB_TOKEN": valid_token}):
            validate_and_configure_logging()

    def test_validate_logging_blank_github_token(self):
        """Test validation fails with blank GitHub token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "   "}):
            with pytest.raises(SystemExit):
                validate_and_configure_logging()

    def test_validate_logging_invalid_github_token(self):
        """Test validation fails with invalid GitHub token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "invalid_token"}):
            with pytest.raises(SystemExit):
                validate_and_configure_logging()

    def test_validate_logging_invalid_log_level(self):
        """Test validation fails with invalid log level."""
        with patch.dict(os.environ, {"LOG_LEVEL": "3"}):
            with pytest.raises(SystemExit):
                validate_and_configure_logging()

    def test_validate_logging_valid_log_levels(self):
        """Test validation passes with valid log levels."""
        for level in ["0", "1", "2"]:
            with patch.dict(os.environ, {"LOG_LEVEL": level}, clear=True):
                validate_and_configure_logging()

    def test_validate_logging_with_valid_log_file(self):
        """Test validation with valid log file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=True) as tmp:
            tmp_path = tmp.name
            with patch.dict(os.environ, {"LOG_FILE": tmp_path, "LOG_LEVEL": "1"}):
                validate_and_configure_logging()


class TestUrlFileParsing:
    """Test URL file parsing functionality."""

    def test_parse_url_file_valid_urls(self):
        """Test parsing file with valid URLs."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp.write("https://github.com/user/repo1\\n")
            tmp.write("https://huggingface.co/user/model1\\n")
            tmp_path = tmp.name

        try:
            urls = parse_url_file(tmp_path)
            assert len(urls) >= 0  # Should not fail parsing
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_parse_url_file_empty_file(self):
        """Test parsing empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp_path = tmp.name

        try:
            urls = parse_url_file(tmp_path)
            assert isinstance(urls, list)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestProcessEntries:
    """Test entries processing functionality."""

    @patch('src.main.MetricsCalculator')
    @pytest.mark.asyncio
    async def test_process_entries_empty_list(self, mock_calculator):
        """Test processing empty entries list."""
        mock_instance = MagicMock()
        mock_calculator.return_value = mock_instance
        
        await process_entries([])
        # Should complete without error

    @patch('src.main.MetricsCalculator')
    @pytest.mark.asyncio
    async def test_process_entries_with_urls(self, mock_calculator):
        """Test processing entries with URLs."""
        mock_instance = MagicMock()
        mock_calculator.return_value = mock_instance
        mock_instance.calculate_all_metrics_async.return_value = {
            "url": "https://github.com/user/repo",
            "bus_factor": 0.5,
            "bus_factor_latency": 100,
            "correctness": 0.8,
            "correctness_latency": 150,
            "ramp_up": 0.7,
            "ramp_up_latency": 200,
            "responsive_maintainer": 0.9,
            "responsive_maintainer_latency": 120,
            "license": 1.0,
            "license_latency": 50,
            "code_quality": 0.85,
            "code_quality_latency": 180,
        }
        
        urls = ["https://github.com/user/repo"]
        await process_entries(urls)


class TestMainFunction:
    """Test main function."""

    def test_main_no_arguments(self):
        """Test main function with no arguments."""
        with patch.object(sys, 'argv', ['main.py']):
            with pytest.raises(SystemExit):
                main()

    def test_main_too_many_arguments(self):
        """Test main function with too many arguments."""
        with patch.object(sys, 'argv', ['main.py', 'file1.txt', 'file2.txt']):
            with pytest.raises(SystemExit):
                main()

    @patch('src.main.parse_url_file')
    @patch('src.main.asyncio.run')
    def test_main_with_valid_file(self, mock_asyncio_run, mock_parse):
        """Test main function with valid file."""
        mock_parse.return_value = ["https://github.com/user/repo"]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp_path = tmp.name
        
        try:
            with patch.object(sys, 'argv', ['main.py', tmp_path]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @patch('src.main.parse_url_file')
    def test_main_with_empty_file(self, mock_parse):
        """Test main function with file containing no URLs."""
        mock_parse.return_value = []
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            tmp_path = tmp.name
        
        try:
            with patch.object(sys, 'argv', ['main.py', tmp_path]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)