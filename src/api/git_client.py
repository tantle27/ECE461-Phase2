import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from git import Repo


@dataclass
class CommitStats:
    """Statistics about commits in a repository."""
    total_commits: int
    contributors: Dict[str, int]  # author -> commit count
    bus_factor: float


@dataclass
class CodeQualityStats:
    """Statistics about code quality."""
    has_tests: bool
    lint_errors: int
    code_quality_score: float


class GitClient:
    """
    Client for cloning and analyzing Git repositories.
    """

    def __init__(self, github_token: Optional[str] = None):
        """Initialize Git client."""
        self.temp_dirs: List[str] = []  # Track temp dirs for cleanup
        self.github_token = github_token

    def _normalize_git_url(self, url: str) -> str:
        """
        Normalize a git URL by removing web interface paths.

        Args:
            url: Repository URL that may include web interface paths

        Returns:
            Clean URL suitable for git clone operations
        """
        # Remove common web interface paths
        patterns_to_remove = [
            r'/tree/[^/]+/?$',      # /tree/main, /tree/master, etc.
            r'/blob/[^/]+/.*$',     # /blob/main/file.py, etc.
            r'/commits?/[^/]+/?$',  # /commit/abc123, /commits/main
            r'/releases?/?.*$',     # /releases, /release/v1.0
            r'/issues?/?.*$',       # /issues, /issues/1
            r'/pull/?.*$',          # /pull/1
            r'/wiki/?.*$',          # /wiki, /wiki/page
        ]

        normalized_url = url.rstrip('/')
        for pattern in patterns_to_remove:
            normalized_url = re.sub(pattern, '', normalized_url)

        return normalized_url

    def clone_repository(self, url: str) -> Optional[str]:
        """
        Clone a repository to a temporary directory.
        :param url: Git repository URL
        :return: Path to cloned repository, or None if cloning failed
        """
        try:
            # Normalize URL for git cloning by removing web interface paths
            normalized_url = self._normalize_git_url(url)

            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="model_analysis_")
            self.temp_dirs.append(temp_dir)

            logging.info(f"Cloning repository: {normalized_url}")

            # Clone the repository
            Repo.clone_from(normalized_url, temp_dir)
            logging.info(f"Successfully cloned to: {temp_dir}")

            return temp_dir

        except Exception as e:
            logging.error(f"Failed to clone repository {url}: {str(e)}")
            return None

    def analyze_commits(self, repo_path: str) -> CommitStats:
        """
        Analyze commit history to calculate bus factor.
        :param repo_path: Path to local repository
        :return: CommitStats object
        """
        try:
            repo = Repo(repo_path)

            # Get commits from the last 365 days
            since_date = datetime.now() - timedelta(days=365)
            commits = list(repo.iter_commits(since=since_date))

            # Count commits by author
            contributors: Dict[str, int] = {}
            for commit in commits:
                author = commit.author.name
                if author:  # Skip commits with no author name
                    contributors[author] = contributors.get(author, 0) + 1

            # Calculate bus factor using Herfindahl-Hirschman Index
            total_commits = len(commits)
            if total_commits == 0:
                return CommitStats(
                    total_commits=0, contributors={}, bus_factor=0.0
                )

            # Get top 10 contributors
            top_contributors: List[tuple[str, int]] = sorted(
                contributors.items(), key=lambda x: x[1], reverse=True
            )[:10]

            # Calculate concentration index
            concentration = sum(
                (count / total_commits) ** 2
                for _, count in top_contributors
            )
            # Higher is better (more distributed)
            bus_factor = 1.0 - concentration

            return CommitStats(
                total_commits=total_commits,
                contributors=dict(top_contributors),
                bus_factor=max(0.0, min(1.0, bus_factor))
            )

        except Exception as e:
            logging.error(f"Failed to analyze commits: {str(e)}")
            return CommitStats(
                total_commits=0, contributors={}, bus_factor=0.0
            )

    def analyze_code_quality(self, repo_path: str) -> CodeQualityStats:
        """
        Analyze code quality by checking for tests and running linter.

        :param repo_path: Path to local repository
        :return: CodeQualityStats object
        """
        try:
            # Check if path exists first
            if not os.path.exists(repo_path):
                return CodeQualityStats(
                    has_tests=False, lint_errors=0, code_quality_score=0.0
                )

            repo_path_obj = Path(repo_path)

            # Check for test directories/files
            test_patterns = ['test', 'tests', 'spec', 'specs']
            has_tests = any(
                any(repo_path_obj.rglob(f"{pattern}*"))
                for pattern in test_patterns
            )

            # Run flake8 on Python files to count lint errors
            lint_errors = 0
            try:
                python_files = list(repo_path_obj.rglob("*.py"))
                if python_files:
                    # Run flake8 and count errors
                    result = subprocess.run(
                        ['flake8', '--count', '--quiet'] +
                        [str(f) for f in python_files],
                        capture_output=True,
                        text=True,
                        cwd=repo_path
                    )
                    # flake8 returns the count as the last line of stderr
                    if result.stderr:
                        try:
                            lint_errors = int(
                                result.stderr.strip().split('\n')[-1]
                            )
                        except (ValueError, IndexError):
                            lint_errors = 0
            except Exception:
                # logging.warning(f"Failed to run flake8: {str(e)}")
                lint_errors = 0

            # Calculate code quality score
            # Start with 1.0, subtract 0.05 for each lint error, minimum 0.0
            code_quality_score = max(0.0, 1.0 - (lint_errors * 0.05))

            return CodeQualityStats(
                has_tests=has_tests,
                lint_errors=lint_errors,
                code_quality_score=code_quality_score
            )

        except Exception as e:
            logging.error(f"Failed to analyze code quality: {str(e)}")
            return CodeQualityStats(
                has_tests=False, lint_errors=0, code_quality_score=0.0
            )

    def analyze_ramp_up_time(self, repo_path: str) -> dict[str, bool]:
        try:
            # Check if path exists first
            if not os.path.exists(repo_path):
                return {
                    'has_examples': False,
                    'has_dependencies': False,
                }

            repo_path_obj = Path(repo_path)

            # Check for example code
            example_patterns = [
                'examples', 'notebooks', 'demo.py', 'example.py'
            ]
            has_examples = any(
                any(repo_path_obj.rglob(f"{pattern}*"))
                for pattern in example_patterns
            )

            # Check for dependency files
            dependency_files = [
                'requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile'
            ]
            has_dependencies = any(
                (repo_path_obj / file).exists() for file in dependency_files
            )

            return {
                'has_examples': has_examples,
                'has_dependencies': has_dependencies,
            }

        except Exception as e:
            logging.error(f"Failed to analyze ramp-up time: {str(e)}")
            return {
                'has_examples': False,
                'has_dependencies': False,
            }

    def get_repository_size(self, repo_path: str) -> Dict[str, float]:
        """
        Calculate repository size and hardware compatibility scores.

        :param repo_path: Path to local repository
        :return: Dictionary with hardware compatibility scores
        """
        try:
            # Check if path exists first
            if not os.path.exists(repo_path):
                return {
                    'raspberry_pi': 0.0,
                    'jetson_nano': 0.0,
                    'desktop_pc': 0.0,
                    'aws_server': 0.0
                }

            repo_path_obj = Path(repo_path)

            # Calculate total size of repository
            total_size = 0
            for file_path in repo_path_obj.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            # Convert to GB
            size_gb = total_size / (1024 ** 3)

            # Calculate compatibility scores based on size thresholds
            size_scores = {
                'raspberry_pi': 1.0 if size_gb < 1.0 else 0.0,
                'jetson_nano': 1.0 if size_gb < 4.0 else 0.0,
                'desktop_pc': 1.0 if size_gb < 16.0 else 0.0,
                'aws_server': 1.0  # Assumed to handle any size
            }

            return size_scores

        except Exception as e:
            logging.error(f"Failed to calculate repository size: {str(e)}")
            return {
                'raspberry_pi': 0.0,
                'jetson_nano': 0.0,
                'desktop_pc': 0.0,
                'aws_server': 0.0
            }

    def read_readme(self, repo_path: str) -> Optional[str]:
        """
        Read the README file from a repository.

        :param repo_path: Path to local repository
        :return: README content as string, or None if not found
        """
        try:
            if not os.path.exists(repo_path):
                return None

            repo_path_obj = Path(repo_path)
            readme_files = list(repo_path_obj.glob("README*"))

            if not readme_files:
                return None

            readme_path = readme_files[0]
            with open(readme_path, 'r', encoding='utf-8') as f:
                return f.read()

        except Exception as e:
            logging.warning(f"Failed to read README: {str(e)}")
            return None

    def cleanup(self):
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.warning(f"Failed to clean up {temp_dir}: {str(e)}")
        self.temp_dirs.clear()
