import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from git import Repo

from src.api.git_client import CodeQualityStats, CommitStats, GitClient

sys.path.insert(0,
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__)))))


class TestGitClientCoverage(unittest.TestCase):
    """Additional tests to improve code coverage."""

    def setUp(self):
        """Set up test fixtures."""
        self.git_client = GitClient()
        self.temp_repo_path = None

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_repo_path and os.path.exists(self.temp_repo_path):
            self._force_remove_directory(self.temp_repo_path)
        self.git_client.cleanup()

    def _force_remove_directory(self, path):
        """Force remove directory with retries"""
        def handle_remove_readonly(func, path, exc):
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)
                func(path)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                shutil.rmtree(path, onerror=handle_remove_readonly)
                break
            except (PermissionError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    print(f"Can't remove {path} after {max_retries} tries")

    def test_analyze_code_quality_flake8_error_handling(self):
        """Test code quality when flake8 fails to run."""
        repo_path = tempfile.mkdtemp(prefix="test_repo_")
        self.temp_repo_path = repo_path

        # Create a Python file
        python_file = Path(repo_path) / "test.py"
        python_file.write_text("print('Hello, World!')")

        # Mock subprocess.run to raise an exception
        with patch('subprocess.run',
                   side_effect=Exception("Flake8 not found")):
            quality_stats = self.git_client.analyze_code_quality(repo_path)

            self.assertIsInstance(quality_stats, CodeQualityStats)
            self.assertEqual(quality_stats.lint_errors, 0)
            self.assertEqual(quality_stats.code_quality_score, 1.0)

    def test_analyze_code_quality_flake8_invalid_output(self):
        """Test code quality when flake8 returns invalid output."""
        repo_path = tempfile.mkdtemp(prefix="test_repo_")
        self.temp_repo_path = repo_path

        # Create a Python file
        python_file = Path(repo_path) / "test.py"
        python_file.write_text("print('Hello, World!')")

        # Mock subprocess.run to return invalid stderr
        mock_result = MagicMock()
        mock_result.stderr = "Invalid output\nNot a number"
        with patch('subprocess.run', return_value=mock_result):
            quality_stats = self.git_client.analyze_code_quality(repo_path)

            self.assertIsInstance(quality_stats, CodeQualityStats)
            self.assertEqual(quality_stats.lint_errors, 0)

    def test_get_repository_size_file_access_error(self):
        """Test repository size when file access fails."""
        repo_path = tempfile.mkdtemp(prefix="test_repo_")
        self.temp_repo_path = repo_path

        # Create a file
        test_file = Path(repo_path) / "test.txt"
        test_file.write_text("test content")

        # Mock file.stat() to raise an exception
        with patch.object(Path,
                          'stat', side_effect=OSError("Permission denied")):
            size_scores = self.git_client.get_repository_size(repo_path)

            self.assertIsInstance(size_scores, dict)
            self.assertEqual(size_scores['raspberry_pi'], 0.0)

    def test_analyze_commits_no_commits_in_period(self):
        """Test commit analysis when no commits exist in the time period."""
        repo_path = tempfile.mkdtemp(prefix="test_repo_")
        self.temp_repo_path = repo_path

        # Create a repo but don't make any commits
        Repo.init(repo_path)

        commit_stats = self.git_client.analyze_commits(repo_path)

        self.assertIsInstance(commit_stats, CommitStats)
        self.assertEqual(commit_stats.total_commits, 0)
        self.assertEqual(commit_stats.bus_factor, 0.0)

    def test_analyze_commits_git_error(self):
        """Test commit analysis when Git operations fail."""
        # Mock Repo to raise an exception
        with patch('git.Repo', side_effect=Exception("Git error")):
            commit_stats = self.git_client.analyze_commits("/some/path")

            self.assertIsInstance(commit_stats, CommitStats)
            self.assertEqual(commit_stats.total_commits, 0)
            self.assertEqual(commit_stats.bus_factor, 0.0)

    def test_cleanup_with_errors(self):
        """Test cleanup when some directories can't be removed."""
        # Create some temp directories
        temp_dir1 = tempfile.mkdtemp(prefix="test_cleanup_1_")
        temp_dir2 = tempfile.mkdtemp(prefix="test_cleanup_2_")

        self.git_client.temp_dirs = [temp_dir1, temp_dir2]

        # Mock shutil.rmtree to raise an exception for one directory
        original_rmtree = shutil.rmtree
        call_count = 0

        def mock_rmtree(path, onerror=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call fails
                raise PermissionError("Cannot remove directory")
            else:  # Second call succeeds
                original_rmtree(path, onerror=onerror)

        with patch('shutil.rmtree', side_effect=mock_rmtree):
            self.git_client.cleanup()

        # Should have attempted to clean up both directories
        self.assertEqual(call_count, 2)

    def test_code_quality_score_calculation(self):
        """Test code quality score calc with various lint error counts."""
        repo_path = tempfile.mkdtemp(prefix="test_repo_")
        self.temp_repo_path = repo_path

        # Create a Python file
        python_file = Path(repo_path) / "test.py"
        python_file.write_text("print('Hello, World!')")

        # Test different lint error counts
        test_cases = [
            (0, 1.0),    # No errors = perfect score
            (5, 0.75),   # 5 errors = 1.0 - (5 * 0.05) = 0.75
            (20, 0.0),   # 20 errors = 1.0 - (20 * 0.05) = 0.0 (minimum)
            (25, 0.0),   # 25 errors = 1.0 - (25 * 0.05) = -0.25, clamped to 0
        ]

        for lint_errors, expected_score in test_cases:
            with patch('subprocess.run') as mock_run:
                mock_result = MagicMock()
                mock_result.stderr = f"Some output\n{lint_errors}"
                mock_run.return_value = mock_result

                quality_stats = self.git_client.analyze_code_quality(repo_path)
                self.assertAlmostEqual(quality_stats.
                                       code_quality_score,
                                       expected_score,
                                       places=2)


if __name__ == '__main__':
    unittest.main()
