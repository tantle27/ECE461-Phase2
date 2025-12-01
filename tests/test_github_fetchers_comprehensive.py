"""
Test coverage for src/api/github_fetchers.py.

Tests GitHub API fetching functionality including:
- Repository tree fetching with Git Trees API
- Commit history fetching
- README file fetching and decoding
- Rate limiting and retry logic
- Error handling and edge cases
"""

import base64
import sys
from unittest.mock import MagicMock, Mock, patch

import requests

# Mock dependencies before importing the module
mock_settings = MagicMock()
mock_settings.GH_TOKEN = None
mock_config = MagicMock()
mock_config.settings = mock_settings

# Mock the config module to avoid pydantic dependency
sys.modules["src.core.config"] = mock_config


class TestHeaders:
    """Test _headers function."""

    @patch("src.api.github_fetchers.settings")
    def test_headers_without_token(self, mock_settings):
        """Test headers when no GitHub token is configured."""
        mock_settings.GH_TOKEN = None

        from src.api.github_fetchers import _headers

        result = _headers()

        assert result == {"Accept": "application/vnd.github+json"}

    @patch("src.api.github_fetchers.settings")
    def test_headers_with_token(self, mock_settings):
        """Test headers when GitHub token is configured."""
        mock_settings.GH_TOKEN = "ghp_test_token_123"

        from src.api.github_fetchers import _headers

        result = _headers()

        expected = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer ghp_test_token_123",
        }
        assert result == expected

    @patch("src.api.github_fetchers.settings")
    def test_headers_with_empty_token(self, mock_settings):
        """Test headers when GitHub token is empty string."""
        mock_settings.GH_TOKEN = ""

        from src.api.github_fetchers import _headers

        result = _headers()

        assert result == {"Accept": "application/vnd.github+json"}


class TestGetFunction:
    """Test _get function with retry logic."""

    @patch("src.api.github_fetchers.settings")
    @patch("src.api.github_fetchers.requests.get")
    @patch("src.api.github_fetchers._headers")
    def test_get_success_first_attempt(self, mock_headers, mock_requests_get, mock_settings):
        """Test successful GET request on first attempt."""
        mock_settings.http_retries = 3
        mock_settings.request_timeout_s = 30
        mock_headers.return_value = {"Accept": "application/vnd.github+json"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_requests_get.return_value = mock_response

        from src.api.github_fetchers import _get

        result = _get("https://api.github.com/test", {"param": "value"})

        assert result == {"test": "data"}
        mock_requests_get.assert_called_once_with(
            "https://api.github.com/test",
            headers={"Accept": "application/vnd.github+json"},
            params={"param": "value"},
            timeout=30,
        )

    @patch("src.api.github_fetchers.settings")
    @patch("src.api.github_fetchers.requests.get")
    @patch("src.api.github_fetchers._headers")
    @patch("time.sleep")
    def test_get_rate_limit_retry(self, mock_sleep, mock_headers, mock_requests_get, mock_settings):
        """Test retry logic when rate limited."""
        mock_settings.http_retries = 3
        mock_settings.request_timeout_s = 30
        mock_headers.return_value = {"Accept": "application/vnd.github+json"}

        # First two attempts: rate limited
        rate_limit_response = Mock()
        rate_limit_response.status_code = 403
        rate_limit_response.text = "Rate limit exceeded"

        # Third attempt: success
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"success": True}

        mock_requests_get.side_effect = [rate_limit_response, rate_limit_response, success_response]

        from src.api.github_fetchers import _get

        result = _get("https://api.github.com/test")

        assert result == {"success": True}
        assert mock_requests_get.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0
        mock_sleep.assert_any_call(2)  # 2^1

    @patch("src.api.github_fetchers.settings")
    @patch("src.api.github_fetchers.requests.get")
    @patch("src.api.github_fetchers._headers")
    @patch("time.sleep")
    def test_get_retries_exhausted(self, mock_sleep, mock_headers, mock_requests_get, mock_settings):
        """Test retry exhaustion when always rate limited."""
        mock_settings.http_retries = 2
        mock_settings.request_timeout_s = 30
        mock_headers.return_value = {"Accept": "application/vnd.github+json"}

        rate_limit_response = Mock()
        rate_limit_response.status_code = 403
        rate_limit_response.text = "Rate limit exceeded"
        mock_requests_get.return_value = rate_limit_response

        from src.api.github_fetchers import _get

        try:
            _get("https://api.github.com/test")
            raise AssertionError("Should have raised RuntimeError")
        except RuntimeError as e:
            assert str(e) == "github: retries exhausted"

        assert mock_requests_get.call_count == 2
        assert mock_sleep.call_count == 2

    @patch("src.api.github_fetchers.settings")
    @patch("src.api.github_fetchers.requests.get")
    @patch("src.api.github_fetchers._headers")
    def test_get_non_rate_limit_error(self, mock_headers, mock_requests_get, mock_settings):
        """Test immediate failure on non-rate-limit HTTP errors."""
        mock_settings.http_retries = 3
        mock_settings.request_timeout_s = 30
        mock_headers.return_value = {"Accept": "application/vnd.github+json"}

        error_response = Mock()
        error_response.status_code = 404
        error_response.raise_for_status.side_effect = requests.HTTPError("Not Found")
        mock_requests_get.return_value = error_response

        from src.api.github_fetchers import _get

        try:
            _get("https://api.github.com/test")
            raise AssertionError("Should have raised HTTPError")
        except requests.HTTPError:
            pass  # Expected

        # Should not retry on non-rate-limit errors
        assert mock_requests_get.call_count == 1

    @patch("src.api.github_fetchers.settings")
    @patch("src.api.github_fetchers.requests.get")
    @patch("src.api.github_fetchers._headers")
    def test_get_without_params(self, mock_headers, mock_requests_get, mock_settings):
        """Test GET request without parameters."""
        mock_settings.http_retries = 3
        mock_settings.request_timeout_s = 30
        mock_headers.return_value = {"Accept": "application/vnd.github+json"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_requests_get.return_value = mock_response

        from src.api.github_fetchers import _get

        result = _get("https://api.github.com/repos/owner/repo")

        assert result == {"data": "test"}
        mock_requests_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo",
            headers={"Accept": "application/vnd.github+json"},
            params=None,
            timeout=30,
        )


class TestFetchRepoTree:
    """Test fetch_repo_tree function."""

    @patch("src.api.github_fetchers._get")
    def test_fetch_repo_tree_with_ref(self, mock_get):
        """Test fetching repo tree with specific ref."""
        # Mock commit lookup
        mock_get.side_effect = [
            {"sha": "commit_sha_123"},  # Commit lookup
            {  # Tree response
                "tree": [
                    {"type": "blob", "path": "src/main.py", "size": "1024"},
                    {"type": "blob", "path": "README.md", "size": "512"},
                    {"type": "tree", "path": "docs", "size": "0"},  # Should be ignored
                    {"type": "blob", "path": "package.json", "size": "256"},
                ]
            },
        ]

        from src.api.github_fetchers import fetch_repo_tree

        result = fetch_repo_tree("owner/repo", "feature-branch")

        expected = [
            {"path": "src/main.py", "size": 1024},
            {"path": "README.md", "size": 512},
            {"path": "package.json", "size": 256},
        ]
        assert result == expected

        # Verify API calls
        assert mock_get.call_count == 2
        mock_get.assert_any_call("https://api.github.com/repos/owner/repo/commits/feature-branch")
        mock_get.assert_any_call(
            "https://api.github.com/repos/owner/repo/git/trees/commit_sha_123", params={"recursive": "1"},
        )

    @patch("src.api.github_fetchers._get")
    def test_fetch_repo_tree_without_ref(self, mock_get):
        """Test fetching repo tree without ref (uses main branch)."""
        mock_get.side_effect = [
            {"commit": {"sha": "main_sha_456"}},  # Main branch lookup
            {"tree": [{"type": "blob", "path": "index.js", "size": "2048"},]},  # Tree response
        ]

        from src.api.github_fetchers import fetch_repo_tree

        result = fetch_repo_tree("owner/repo", None)

        expected = [{"path": "index.js", "size": 2048}]
        assert result == expected

        mock_get.assert_any_call("https://api.github.com/repos/owner/repo/branches/main")
        mock_get.assert_any_call(
            "https://api.github.com/repos/owner/repo/git/trees/main_sha_456", params={"recursive": "1"},
        )

    @patch("src.api.github_fetchers._get")
    def test_fetch_repo_tree_empty_tree(self, mock_get):
        """Test fetching repo tree with empty repository."""
        mock_get.side_effect = [{"sha": "empty_sha"}, {"tree": []}]  # Empty tree

        from src.api.github_fetchers import fetch_repo_tree

        result = fetch_repo_tree("owner/empty-repo", "main")

        assert result == []

    @patch("src.api.github_fetchers._get")
    def test_fetch_repo_tree_missing_size(self, mock_get):
        """Test fetching repo tree with entries missing size."""
        mock_get.side_effect = [
            {"sha": "test_sha"},
            {
                "tree": [
                    {"type": "blob", "path": "file1.txt"},  # No size field
                    {"type": "blob", "path": "file2.txt", "size": "100"},
                ]
            },
        ]

        from src.api.github_fetchers import fetch_repo_tree

        result = fetch_repo_tree("owner/repo", "main")

        expected = [
            {"path": "file1.txt", "size": 0},  # Default to 0
            {"path": "file2.txt", "size": 100},
        ]
        assert result == expected


class TestFetchCommits:
    """Test fetch_commits function."""

    @patch("src.api.github_fetchers._get")
    def test_fetch_commits_with_ref(self, mock_get):
        """Test fetching commits with specific ref."""
        mock_get.return_value = [
            {
                "commit": {"author": {"email": "user1@example.com", "date": "2023-01-01T12:00:00Z"}},
                "author": {"login": "user1"},
            },
            {
                "commit": {"author": {"email": "user2@example.com", "date": "2023-01-02T12:00:00Z"}},
                "author": {"login": "user2"},
            },
        ]

        from src.api.github_fetchers import fetch_commits

        result = fetch_commits("owner/repo", "feature-branch")

        expected = [
            {"author_email": "user1@example.com", "author_login": "user1", "date": "2023-01-01T12:00:00Z",},
            {"author_email": "user2@example.com", "author_login": "user2", "date": "2023-01-02T12:00:00Z",},
        ]
        assert result == expected

        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/commits", params={"per_page": 100, "sha": "feature-branch"},
        )

    @patch("src.api.github_fetchers._get")
    def test_fetch_commits_without_ref(self, mock_get):
        """Test fetching commits without ref."""
        mock_get.return_value = [
            {
                "commit": {"author": {"email": "author@example.com", "date": "2023-01-01T12:00:00Z"}},
                "author": {"login": "author"},
            }
        ]

        from src.api.github_fetchers import fetch_commits

        fetch_commits("owner/repo", None)

        mock_get.assert_called_once_with("https://api.github.com/repos/owner/repo/commits", params={"per_page": 100})

    @patch("src.api.github_fetchers._get")
    def test_fetch_commits_missing_author_info(self, mock_get):
        """Test fetching commits with missing author information."""
        mock_get.return_value = [
            {"commit": {}, "author": None},  # No author field
            {"commit": {"author": {}}, "author": {"login": "user2"}},  # Empty author
        ]

        from src.api.github_fetchers import fetch_commits

        result = fetch_commits("owner/repo", "main")

        expected = [
            {"author_email": None, "author_login": None, "date": None},
            {"author_email": None, "author_login": "user2", "date": None},
        ]
        assert result == expected

    @patch("src.api.github_fetchers._get")
    def test_fetch_commits_empty_response(self, mock_get):
        """Test fetching commits with empty response."""
        mock_get.return_value = []

        from src.api.github_fetchers import fetch_commits

        result = fetch_commits("owner/repo", "main")

        assert result == []


class TestFetchReadme:
    """Test fetch_readme function."""

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_success(self, mock_get):
        """Test successful README fetching and decoding."""
        readme_content = "# Test Project\n\nThis is a test README."
        content_b64 = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")

        mock_get.return_value = {"path": "README.md", "content": content_b64}

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        expected = {
            "path": "README.md",
            "size": len(readme_content.encode("utf-8")),
            "text": readme_content,
        }
        assert result == expected

        mock_get.assert_called_once_with("https://api.github.com/repos/owner/repo/readme", params={"ref": "main"})

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_without_ref(self, mock_get):
        """Test fetching README without ref."""
        readme_content = "# Default README"
        content_b64 = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")

        mock_get.return_value = {"path": "README.md", "content": content_b64}

        from src.api.github_fetchers import fetch_readme

        fetch_readme("owner/repo", None)

        mock_get.assert_called_once_with("https://api.github.com/repos/owner/repo/readme", params={})

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_api_error(self, mock_get):
        """Test README fetching when API returns error."""
        mock_get.side_effect = requests.HTTPError("Not Found")

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        assert result is None

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_invalid_base64(self, mock_get):
        """Test README fetching with invalid base64 content."""
        mock_get.return_value = {"path": "README.md", "content": "invalid-base64-content!!!"}

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        expected = {
            "path": "README.md",
            "size": 9,  # Invalid base64 may still produce some decoded content
            "text": "{ږ'[jǺ'",  # The actual decoded content from the invalid base64
        }
        assert result == expected

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_missing_content(self, mock_get):
        """Test README fetching with missing content field."""
        mock_get.return_value = {
            "path": "README.md"
            # No content field
        }

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        expected = {"path": "README.md", "size": 0, "text": ""}
        assert result == expected

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_unicode_content(self, mock_get):
        """Test README fetching with Unicode content."""
        readme_content = "# 测试项目\n\n这是一个测试 README。🚀"
        content_b64 = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")

        mock_get.return_value = {"path": "README.md", "content": content_b64}

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        expected = {
            "path": "README.md",
            "size": len(readme_content.encode("utf-8")),
            "text": readme_content,
        }
        assert result == expected

    @patch("src.api.github_fetchers._get")
    def test_fetch_readme_missing_path(self, mock_get):
        """Test README fetching with missing path field."""
        readme_content = "# Test"
        content_b64 = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")

        mock_get.return_value = {
            "content": content_b64
            # No path field
        }

        from src.api.github_fetchers import fetch_readme

        result = fetch_readme("owner/repo", "main")

        expected = {
            "path": "README.md",  # Default value
            "size": len(readme_content.encode("utf-8")),
            "text": readme_content,
        }
        assert result == expected
