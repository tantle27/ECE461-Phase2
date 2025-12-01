"""
Comprehensive tests for src/main.py
This file tests CLI functionality, URL parsing, and main execution paths.
"""

import logging
import os
import tempfile
from io import StringIO
from unittest.mock import Mock, patch

from src.main import (
    _classify_url,
    _fail,
    _github_token_is_valid,
    calculate_net_score,
    parse_url_file,
    validate_and_configure_logging,
)


class TestGitHubTokenValidation:
    """Test GitHub token format validation."""

    def test_valid_ghp_token(self):
        """Test valid ghp_ token format."""
        valid_token = "ghp_" + "A" * 36
        assert _github_token_is_valid(valid_token)

    def test_valid_gho_token(self):
        """Test valid gho_ token format."""
        valid_token = "gho_" + "B" * 40
        assert _github_token_is_valid(valid_token)

    def test_valid_ghu_token(self):
        """Test valid ghu_ token format."""
        valid_token = "ghu_" + "C" * 36
        assert _github_token_is_valid(valid_token)

    def test_valid_ghs_token(self):
        """Test valid ghs_ token format."""
        valid_token = "ghs_" + "D" * 50
        assert _github_token_is_valid(valid_token)

    def test_valid_pat_token(self):
        """Test valid github_pat_ token format."""
        valid_token = "github_pat_" + "E" * 30
        assert _github_token_is_valid(valid_token)

    def test_invalid_short_token(self):
        """Test invalid token that's too short."""
        invalid_token = "ghp_short"
        assert not _github_token_is_valid(invalid_token)

    def test_invalid_wrong_prefix(self):
        """Test invalid token with wrong prefix."""
        invalid_token = "xyz_" + "A" * 40
        assert not _github_token_is_valid(invalid_token)

    def test_invalid_empty_token(self):
        """Test invalid empty token."""
        assert not _github_token_is_valid("")

    def test_invalid_no_underscore(self):
        """Test invalid token without underscore."""
        invalid_token = "ghp" + "A" * 40
        assert not _github_token_is_valid(invalid_token)


class TestFailFunction:
    """Test the _fail function."""

    def test_fail_exits_with_code_1(self):
        """Test that _fail exits with code 1."""
        with patch("sys.exit") as mock_exit, patch("sys.stderr", new_callable=StringIO):
            _fail("Test error message")
            mock_exit.assert_called_once_with(1)

    def test_fail_prints_to_stderr(self):
        """Test that _fail prints error message to stderr."""
        with patch("sys.exit"), patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            _fail("Test error message")
            output = mock_stderr.getvalue()
            assert "Error: Test error message" in output


class TestValidateAndConfigureLogging:
    """Test the validate_and_configure_logging function."""

    def test_valid_github_token(self):
        """Test validation with valid GitHub token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_" + "A" * 36, "LOG_LEVEL": "0"}):
            # Should not raise or exit
            with patch("logging.disable"):
                validate_and_configure_logging()

    def test_invalid_github_token_blank(self):
        """Test validation with blank GitHub token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "   ", "LOG_LEVEL": "0"}):
            with patch("src.main._fail") as mock_fail:
                validate_and_configure_logging()
                mock_fail.assert_called()
                # Check that one of the calls was about blank token
                call_args = [str(call) for call in mock_fail.call_args_list]
                assert any("blank" in arg for arg in call_args)

    def test_invalid_github_token_format(self):
        """Test validation with invalid GitHub token format."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "invalid_token", "LOG_LEVEL": "0"}):
            with patch("src.main._fail") as mock_fail:
                validate_and_configure_logging()
                mock_fail.assert_called()
                # Check that one of the calls was about token format
                call_args = [str(call) for call in mock_fail.call_args_list]
                assert any("format" in arg for arg in call_args)

    def test_invalid_log_level(self):
        """Test validation with invalid LOG_LEVEL."""
        with patch.dict(os.environ, {"LOG_LEVEL": "5"}):
            with patch("src.main._fail") as mock_fail:
                validate_and_configure_logging()
                mock_fail.assert_called_once()
                assert "LOG_LEVEL" in str(mock_fail.call_args)

    def test_valid_log_levels(self):
        """Test validation with all valid log levels."""
        for level in ["0", "1", "2"]:
            with patch.dict(os.environ, {"LOG_LEVEL": level}, clear=True):
                with patch("logging.disable"), patch("logging.basicConfig"), patch("logging.getLogger"):
                    # Should not raise or exit
                    validate_and_configure_logging()

    def test_log_level_0_creates_blank_file(self):
        """Test that LOG_LEVEL=0 creates a blank log file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"LOG_LEVEL": "0", "LOG_FILE": tmp_path}):
                with patch("logging.disable"), patch("logging.getLogger"):
                    validate_and_configure_logging()

                # File should exist and be empty
                assert os.path.exists(tmp_path)
                with open(tmp_path) as f:
                    content = f.read()
                    assert content == ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_invalid_log_file_path(self):
        """Test validation with invalid log file path."""
        with patch.dict(os.environ, {"LOG_FILE": "/invalid/path/logfile.txt", "LOG_LEVEL": "0"}):
            with patch("src.main._fail") as mock_fail:
                validate_and_configure_logging()
                mock_fail.assert_called()
                # Check that one of the calls was about log file path
                call_args = [str(call) for call in mock_fail.call_args_list]
                assert any("log file" in arg for arg in call_args)

    def test_log_level_1_with_file(self):
        """Test LOG_LEVEL=1 with log file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"LOG_LEVEL": "1", "LOG_FILE": tmp_path}):
                with patch("logging.basicConfig") as mock_basic_config, patch(
                    "logging.getLogger"
                ) as mock_get_logger, patch("logging.info"), patch("logging.debug"):
                    mock_logger = Mock()
                    mock_get_logger.return_value = mock_logger

                    validate_and_configure_logging()

                    mock_basic_config.assert_called_once()
                    assert mock_basic_config.call_args[1]["level"] == logging.INFO
                    assert mock_basic_config.call_args[1]["filename"] == tmp_path
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_log_level_2_with_file(self):
        """Test LOG_LEVEL=2 with debug logging."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"LOG_LEVEL": "2", "LOG_FILE": tmp_path}):
                with patch("logging.basicConfig") as mock_basic_config, patch(
                    "logging.getLogger"
                ) as mock_get_logger, patch("logging.info") as mock_info, patch("logging.debug") as mock_debug:
                    mock_logger = Mock()
                    mock_get_logger.return_value = mock_logger

                    validate_and_configure_logging()

                    mock_basic_config.assert_called_once()
                    assert mock_basic_config.call_args[1]["level"] == logging.DEBUG
                    mock_info.assert_called_once()
                    mock_debug.assert_called_once()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_log_level_without_file_disables_logging(self):
        """Test LOG_LEVEL>0 without LOG_FILE disables logging."""
        with patch.dict(os.environ, {"LOG_LEVEL": "1"}, clear=True):
            with patch("logging.disable") as mock_disable, patch("logging.getLogger") as mock_get_logger:
                mock_logger = Mock()
                mock_get_logger.return_value = mock_logger

                validate_and_configure_logging()

                mock_disable.assert_called_once_with(logging.CRITICAL)


class TestClassifyUrl:
    """Test the _classify_url function."""

    def test_classify_github_url(self):
        """Test classification of GitHub URLs as code."""
        github_urls = [
            "https://github.com/user/repo",
            "http://github.com/org/project",
            "github.com/simple/repo",
        ]
        for url in github_urls:
            assert _classify_url(url) == "code"

    def test_classify_huggingface_dataset_url(self):
        """Test classification of HuggingFace dataset URLs."""
        dataset_urls = [
            "https://huggingface.co/datasets/user/dataset",
            "http://huggingface.co/datasets/org/data",
            "huggingface.co/datasets/simple",
        ]
        for url in dataset_urls:
            assert _classify_url(url) == "dataset"

    def test_classify_huggingface_model_url(self):
        """Test classification of HuggingFace model URLs."""
        model_urls = [
            "https://huggingface.co/user/model",
            "http://huggingface.co/org/transformer",
            "huggingface.co/gpt2",
        ]
        for url in model_urls:
            assert _classify_url(url) == "model"

    def test_classify_unknown_url(self):
        """Test classification of unknown URLs."""
        unknown_urls = [
            "https://example.com/repo",
            "http://gitlab.com/user/project",
            "npm.org/package",
            "",
        ]
        for url in unknown_urls:
            assert _classify_url(url) == "unknown"

    def test_classify_url_strips_whitespace(self):
        """Test that URL classification strips whitespace."""
        assert _classify_url("  https://github.com/user/repo  ") == "code"
        assert _classify_url("\\n\\thuggingface.co/datasets/test\\n") == "dataset"


class TestParseUrlFile:
    """Test the parse_url_file function."""

    def test_parse_csv_format(self):
        """Test parsing CSV format file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp_file:
            # Write actual CSV lines with proper model URLs
            tmp_file.write(
                "https://github.com/user/code,https://huggingface.co/datasets/data,https://huggingface.co/model1\n"
            )
            tmp_file.write(",https://huggingface.co/datasets/data2,https://huggingface.co/model2\n")
            tmp_path = tmp_file.name

        try:
            with patch("logging.info"), patch("logging.debug"), patch("logging.warning"):
                entries = parse_url_file(tmp_path)

            assert len(entries) == 2
            expected1 = (
                "https://github.com/user/code",
                "https://huggingface.co/datasets/data",
                "https://huggingface.co/model1",
            )
            expected2 = (
                None,
                "https://huggingface.co/datasets/data2",
                "https://huggingface.co/model2",
            )
            assert entries[0] == expected1
            assert entries[1] == expected2
        finally:
            os.unlink(tmp_path)

    def test_parse_single_url_format(self):
        """Test parsing single URL per line format."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp_file:
            # Write actual URLs with newlines - each model gets preceding code/dataset
            tmp_file.write("https://github.com/user/code\n")
            tmp_file.write("https://huggingface.co/datasets/data\n")
            tmp_file.write("https://huggingface.co/model1\n")
            tmp_file.write("https://huggingface.co/model2\n")
            tmp_path = tmp_file.name

        try:
            with patch("logging.info"), patch("logging.debug"), patch("logging.warning"):
                entries = parse_url_file(tmp_path)

            assert len(entries) == 2
            expected = (
                "https://github.com/user/code",
                "https://huggingface.co/datasets/data",
                "https://huggingface.co/model1",
            )
            assert entries[0] == expected
            assert entries[1] == (None, None, "https://huggingface.co/model2")
        finally:
            os.unlink(tmp_path)

    def test_parse_empty_lines(self):
        """Test parsing file with empty lines."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp_file:
            tmp_file.write("\n")
            tmp_file.write("https://github.com/user/code\n")
            tmp_file.write("\n")
            tmp_file.write("https://huggingface.co/model1\n")
            tmp_file.write("\n")
            tmp_path = tmp_file.name

        try:
            with patch("logging.info"), patch("logging.debug"), patch("logging.warning"):
                entries = parse_url_file(tmp_path)

            assert len(entries) == 1
            expected = ("https://github.com/user/code", None, "https://huggingface.co/model1")
            assert entries[0] == expected
        finally:
            os.unlink(tmp_path)

    def test_parse_file_not_found(self):
        """Test parsing non-existent file."""
        with patch("src.main._fail") as mock_fail:
            parse_url_file("/nonexistent/file.txt")
            mock_fail.assert_called_once()
            assert "not found" in str(mock_fail.call_args)

    def test_parse_csv_missing_model(self):
        """Test CSV format with missing model URL."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp_file:
            # Write CSV line with missing model URL (empty third field)
            tmp_file.write("https://github.com/user/code,https://huggingface.co/datasets/data,\n")
            tmp_path = tmp_file.name

        try:
            with patch("logging.info"), patch("logging.debug"), patch("logging.warning") as mock_warning:
                entries = parse_url_file(tmp_path)

            assert len(entries) == 0  # No valid entries
            mock_warning.assert_called()
        finally:
            os.unlink(tmp_path)

    def test_parse_unknown_url_warning(self):
        """Test unknown URL type generates warning."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp_file:
            tmp_file.write("https://example.com/unknown\n")
            tmp_file.write("https://huggingface.co/model1\n")
            tmp_path = tmp_file.name

        try:
            with patch("logging.info"), patch("logging.debug"), patch("logging.warning") as mock_warning:
                parse_url_file(tmp_path)

            mock_warning.assert_called()
            # Check if warning was called with unknown URL message
            call_args = [str(call) for call in mock_warning.call_args_list]
            assert any("unknown URL type" in arg for arg in call_args)
        finally:
            os.unlink(tmp_path)


class TestCalculateNetScore:
    """Test the calculate_net_score function."""

    def test_calculate_perfect_score(self):
        """Test calculation with perfect metrics."""
        metrics = {
            "license": 1.0,
            "ramp_up_time": 1.0,
            "dataset_and_code_score": 1.0,
            "performance_claims": 1.0,
            "bus_factor": 1.0,
            "code_quality": 1.0,
            "dataset_quality": 1.0,
        }
        score = calculate_net_score(metrics)
        assert score == 1.0

    def test_calculate_zero_score(self):
        """Test calculation with all zero metrics."""
        metrics = {
            "license": 0.0,
            "ramp_up_time": 0.0,
            "dataset_and_code_score": 0.0,
            "performance_claims": 0.0,
            "bus_factor": 0.0,
            "code_quality": 0.0,
            "dataset_quality": 0.0,
        }
        score = calculate_net_score(metrics)
        assert score == 0.0

    def test_calculate_weighted_score(self):
        """Test calculation with specific weighted values."""
        metrics = {
            "license": 1.0,  # 0.30 weight
            "ramp_up_time": 0.5,  # 0.20 weight
            "dataset_and_code_score": 0.0,  # 0.15 weight
            "performance_claims": 1.0,  # 0.10 weight
            "bus_factor": 0.8,  # 0.15 weight
            "code_quality": 0.6,  # 0.05 weight
            "dataset_quality": 0.4,  # 0.05 weight
        }
        expected = (
            (1.0 * 0.30) + (0.5 * 0.20) + (0.0 * 0.15) + (1.0 * 0.10) + (0.8 * 0.15) + (0.6 * 0.05) + (0.4 * 0.05)
        )
        score = calculate_net_score(metrics)
        assert abs(score - expected) < 0.001

    def test_calculate_missing_metrics(self):
        """Test calculation with missing metrics (default to 0)."""
        metrics = {
            "license": 0.5,
            # Other metrics missing
        }
        expected = 0.5 * 0.30  # Only license contributes
        score = calculate_net_score(metrics)
        assert abs(score - expected) < 0.001

    def test_calculate_score_bounds(self):
        """Test that score is bounded between 0 and 1."""
        # Test over 1.0 (should cap at 1.0)
        metrics = {
            m: 2.0
            for m in [
                "license",
                "ramp_up_time",
                "dataset_and_code_score",
                "performance_claims",
                "bus_factor",
                "code_quality",
                "dataset_quality",
            ]
        }
        score = calculate_net_score(metrics)
        assert score == 1.0

        # Test under 0.0 (should floor at 0.0)
        metrics = {
            m: -1.0
            for m in [
                "license",
                "ramp_up_time",
                "dataset_and_code_score",
                "performance_claims",
                "bus_factor",
                "code_quality",
                "dataset_quality",
            ]
        }
        score = calculate_net_score(metrics)
        assert score == 0.0

    def test_calculate_empty_metrics(self):
        """Test calculation with empty metrics dictionary."""
        metrics = {}
        score = calculate_net_score(metrics)
        assert score == 0.0
