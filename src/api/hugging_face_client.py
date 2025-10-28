import math

from huggingface_hub import HfApi, hf_hub_download

from src.constants import MAX_DATASET_DOWNLOADS, MAX_DATASET_LIKES


class HuggingFaceClient:

    def __init__(self):
        self.api = HfApi()

    def normalize_log(self, value: int, max_value: int) -> float:
        if value <= 0:
            return 0.0
        return min(math.log1p(value) / math.log1p(max_value), 1.0)

    def get_dataset_info(self, repo_id: str) -> dict:
        info = self.api.dataset_info(repo_id)
        normalized_likes = self.normalize_log(
            info.likes if info.likes is not None else 0, MAX_DATASET_LIKES
        )
        normalized_downloads = self.normalize_log(
            info.downloads if info.downloads is not None else 0, MAX_DATASET_DOWNLOADS
        )
        return {"normalized_likes": normalized_likes, "normalized_downloads": normalized_downloads}

    def download_file(self, repo_id: str, filename: str, local_dir: str = "./") -> str:
        return hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_dir,
        )
