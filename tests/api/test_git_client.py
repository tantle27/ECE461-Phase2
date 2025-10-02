import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path

from git import Actor, Repo

from src.api.git_client import CodeQualityStats, CommitStats, GitClient


class TestGitClient(unittest.TestCase):
    """Test cases for GitClient."""

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
        """remove directory with retries for Windows file locking."""
        def handle_remove_readonly(func, path, exc):
            """Handle readonly files on Windows."""
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
                    time.sleep(0.5 * (attempt + 1))  # Increasing delay
                else:
                    print(f"Can't remove {path} after {max_retries} tries")

    def create_test_repo(self) -> str:
        """Create a test repository for testing."""
        self.temp_repo_path = tempfile.mkdtemp(prefix="test_repo_")
        repo = Repo.init(self.temp_repo_path)

        # Create a test file
        test_file = Path(self.temp_repo_path) / "test.py"
        test_file.write_text("print('Hello, World!')")

        # Make initial commit with a specific author
        default_author = Actor("DefaultAuthor", "default@test.com")
        repo.index.add(["test.py"])
        repo.index.commit("Initial commit", author=default_author)

        return self.temp_repo_path

    def create_comprehensive_test_repo(self) -> str:
        """Create a comprehensive test repository with various files."""
        self.temp_repo_path = tempfile.mkdtemp(prefix="test_repo_")
        repo = Repo.init(self.temp_repo_path)

        # Create Python files
        (Path(self.temp_repo_path) / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")

        # Create a README
        (Path(self.temp_repo_path) / "README.md").write_text("""
# Test Repository

## Description
This is a test repository for comprehensive testing.

## Installation
```bash
pip install -r requirements.txt
```

## Usage
```python
from main import main
main()
```

## Examples
See the examples/ directory for usage examples.

## Getting Started
1. Clone this repository
2. Install dependencies
3. Run the examples
""")

        # Create requirements.txt
        (Path(self.temp_repo_path) / "requirements.txt"). \
            write_text("requests\nnumpy\npandas")

        # Create examples directory
        examples_dir = Path(self.temp_repo_path) / "examples"
        examples_dir.mkdir()
        (examples_dir / "demo.py").write_text("print('Demo example')")

        # Create tests directory
        tests_dir = Path(self.temp_repo_path) / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("""
import unittest
from main import main

class TestMain(unittest.TestCase):
    def test_main_function(self):
        # Test that main function runs without error
        try:
            main()
        except Exception as e:
            self.fail(f"main() raised {type(e).__name__} unexpectedly!")
""")

        # Make initial commit
        default_author = Actor("DefaultAuthor", "default@test.com")
        repo.index.add(["main.py",
                        "README.md",
                        "requirements.txt",
                        "examples/demo.py",
                        "tests/test_main.py"])
        repo.index.commit("Initial commit", author=default_author)

        return self.temp_repo_path

    def test_analyze_commits(self):
        """Test commit analysis."""
        repo_path = self.create_test_repo()

        # Add more commits with different authors
        repo = Repo(repo_path)

        # Create commits with different authors
        test_file = Path(repo_path) / "test.py"
        test_file.write_text("print('Updated!')")
        repo.index.add(["test.py"])
        author1 = Actor("Author1", "author1@test.com")
        repo.index.commit("Update test file", author=author1)

        test_file.write_text("print('Updated again!')")
        repo.index.add(["test.py"])
        author2 = Actor("Author2", "author2@test.com")
        repo.index.commit("Another update", author=author2)

        commit_stats = self.git_client.analyze_commits(repo_path)

        self.assertIsInstance(commit_stats, CommitStats)
        self.assertGreaterEqual(commit_stats.total_commits, 3)
        self.assertGreaterEqual(len(commit_stats.contributors), 2)
        self.assertGreaterEqual(commit_stats.bus_factor, 0.0)
        self.assertLessEqual(commit_stats.bus_factor, 1.0)

    def test_analyze_commits_empty_repo(self):
        """Test commit analysis on empty repository."""
        empty_repo_path = tempfile.mkdtemp(prefix="empty_repo_")
        try:
            Repo.init(empty_repo_path)
            commit_stats = self.git_client.analyze_commits(empty_repo_path)

            self.assertEqual(commit_stats.total_commits, 0)
            self.assertEqual(commit_stats.bus_factor, 0.0)
        finally:
            shutil.rmtree(empty_repo_path)

    def test_analyze_commits_single_author(self):
        """Test commit analysis with single author (low bus factor)."""
        repo_path = self.create_test_repo()

        # Add more commits with same author as the initial commit
        repo = Repo(repo_path)

        test_file = Path(repo_path) / "test.py"
        same_author = Actor("DefaultAuthor", "default@test.com")
        for i in range(5):
            test_file.write_text(f"print('Update {i}')")
            repo.index.add(["test.py"])
            repo.index.commit(f"Update {i}", author=same_author)

        commit_stats = self.git_client.analyze_commits(repo_path)

        self.assertIsInstance(commit_stats, CommitStats)
        self.assertGreaterEqual(commit_stats.total_commits, 6)
        self.assertEqual(len(commit_stats.contributors), 1)
        self.assertLess(commit_stats.bus_factor, 0.5)

    def test_analyze_commits_multiple_authors(self):
        """Test commit analysis with multiple authors (high bus factor)."""
        repo_path = self.create_test_repo()

        # Add commits with different authors
        repo = Repo(repo_path)

        test_file = Path(repo_path) / "test.py"
        authors = [
            Actor("Author1", "author1@test.com"),
            Actor("Author2", "author2@test.com"),
            Actor("Author3", "author3@test.com")
        ]

        for i, author in enumerate(authors):
            test_file.write_text(f"print('Update by {author.name}')")
            repo.index.add(["test.py"])
            repo.index.commit(f"Update by {author.name}", author=author)

        commit_stats = self.git_client.analyze_commits(repo_path)

        self.assertIsInstance(commit_stats, CommitStats)
        self.assertGreaterEqual(commit_stats.total_commits, 4)
        self.assertGreaterEqual(len(commit_stats.contributors), 3)
        self.assertGreater(commit_stats.bus_factor, 0.5)

    def test_cleanup(self):
        """Test cleanup functionality."""
        # Create some temp directories
        temp_dir1 = tempfile.mkdtemp(prefix="test_cleanup_1_")
        temp_dir2 = tempfile.mkdtemp(prefix="test_cleanup_2_")

        self.git_client.temp_dirs = [temp_dir1, temp_dir2]

        # Verify directories exist
        self.assertTrue(os.path.exists(temp_dir1))
        self.assertTrue(os.path.exists(temp_dir2))

        # Clean up
        self.git_client.cleanup()

        # Verify directories are removed
        self.assertFalse(os.path.exists(temp_dir1))
        self.assertFalse(os.path.exists(temp_dir2))
        self.assertEqual(len(self.git_client.temp_dirs), 0)

    def test_clone_repository_invalid_url(self):
        """Test cloning with invalid URL."""
        result = \
            self.git_client. \
            clone_repository("https://github.com/nonexistent/repo")
        self.assertIsNone(result)

    def test_analyze_commits_invalid_path(self):
        """Test commit analysis with invalid path."""
        commit_stats = self.git_client.analyze_commits("/nonexistent/path")

        self.assertIsInstance(commit_stats, CommitStats)
        self.assertEqual(commit_stats.total_commits, 0)
        self.assertEqual(commit_stats.bus_factor, 0.0)
        self.assertEqual(len(commit_stats.contributors), 0)

    def test_analyze_code_quality(self):
        """Test code quality analysis."""
        repo_path = self.create_comprehensive_test_repo()

        quality_stats = self.git_client.analyze_code_quality(repo_path)

        self.assertIsInstance(quality_stats, CodeQualityStats)
        self.assertTrue(quality_stats.has_tests)
        self.assertIsInstance(quality_stats.lint_errors, int)
        self.assertGreaterEqual(quality_stats.code_quality_score, 0.0)
        self.assertLessEqual(quality_stats.code_quality_score, 1.0)

    def test_analyze_code_quality_no_python_files(self):
        """Test code quality analysis with no Python files."""
        no_python_path = tempfile.mkdtemp(prefix="no_python_")
        try:
            Repo.init(no_python_path)
            (Path(no_python_path) / "README.txt").write_text("No Python here")

            quality_stats = \
                self.git_client.analyze_code_quality(no_python_path)

            self.assertFalse(quality_stats.has_tests)
            self.assertEqual(quality_stats.lint_errors, 0)
            self.assertEqual(quality_stats.code_quality_score, 1.0)
        finally:
            shutil.rmtree(no_python_path)

    def test_analyze_code_quality_invalid_path(self):
        """Test code quality analysis with invalid path."""
        quality_stats = \
            self.git_client.analyze_code_quality("/nonexistent/path")

        self.assertIsInstance(quality_stats, CodeQualityStats)
        self.assertFalse(quality_stats.has_tests)
        self.assertEqual(quality_stats.lint_errors, 0)
        self.assertEqual(quality_stats.code_quality_score, 0.0)

    def test_get_repository_size(self):
        """Test repository size calculation."""
        repo_path = self.create_comprehensive_test_repo()

        size_scores = \
            self.git_client.get_repository_size(repo_path)

        self.assertIsInstance(size_scores, dict)
        self.assertIn('raspberry_pi', size_scores)
        self.assertIn('jetson_nano', size_scores)
        self.assertIn('desktop_pc', size_scores)
        self.assertIn('aws_server', size_scores)

        # All scores should be 0.0 or 1.0
        for score in size_scores.values():
            self.assertIn(score, [0.0, 1.0])

    def test_get_repository_size_invalid_path(self):
        """Test repository size calculation with invalid path."""
        size_scores = \
            self.git_client.get_repository_size("/nonexistent/path")

        self.assertIsInstance(size_scores, dict)
        self.assertEqual(size_scores['raspberry_pi'], 0.0)
        self.assertEqual(size_scores['jetson_nano'], 0.0)
        self.assertEqual(size_scores['desktop_pc'], 0.0)
        self.assertEqual(size_scores['aws_server'], 0.0)


if __name__ == '__main__':
    unittest.main()
