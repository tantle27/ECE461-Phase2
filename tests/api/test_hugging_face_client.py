import math
from unittest.mock import MagicMock, patch

from src.api.hugging_face_client import HuggingFaceClient
from src.constants import MAX_DATASET_DOWNLOADS, MAX_DATASET_LIKES


class TestHuggingFaceClient:
    def setup_method(self):
        self.client = HuggingFaceClient()

    def test_normalize_log_zero(self):
        assert self.client.normalize_log(0, 100) == 0.0
        assert self.client.normalize_log(-5, 100) == 0.0

    def test_normalize_log_typical(self):
        value = 100
        max_value = 1000
        expected = math.log1p(value) / math.log1p(max_value)
        assert abs(self.client.normalize_log(value, max_value) - expected) < 1e-6

    def test_normalize_log_above_max(self):
        value = 2000
        max_value = 1000
        assert self.client.normalize_log(value, max_value) == 1.0

    @patch("src.api.hugging_face_client.HfApi")
    def test_get_dataset_info(self, mock_hfapi):
        mock_info = MagicMock()
        mock_info.likes = 100
        mock_info.downloads = 200
        mock_hfapi.return_value.dataset_info.return_value = mock_info
        client = HuggingFaceClient()
        result = client.get_dataset_info("repo-id")
        expected_likes = client.normalize_log(100, MAX_DATASET_LIKES)
        expected_downloads = client.normalize_log(200, MAX_DATASET_DOWNLOADS)
        assert result["normalized_likes"] == expected_likes
        assert result["normalized_downloads"] == expected_downloads

    @patch("src.api.hugging_face_client.HfApi")
    def test_get_dataset_info_none_values(self, mock_hfapi):
        mock_info = MagicMock()
        mock_info.likes = None
        mock_info.downloads = None
        mock_hfapi.return_value.dataset_info.return_value = mock_info
        client = HuggingFaceClient()
        result = client.get_dataset_info("repo-id")
        assert result["normalized_likes"] == 0.0
        assert result["normalized_downloads"] == 0.0

    @patch("src.api.hugging_face_client.hf_hub_download")
    def test_download_file(self, mock_download):
        mock_download.return_value = "/fake/path/file.txt"
        client = HuggingFaceClient()
        result = client.download_file("repo-id", "file.txt", local_dir="/tmp")
        mock_download.assert_called_once_with(
            repo_id="repo-id", filename="file.txt", local_dir="/tmp"
        )
        assert result == "/fake/path/file.txt"
