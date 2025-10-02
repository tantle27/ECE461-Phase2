from typing import Any, Optional

from src.api.hugging_face_client import HuggingFaceClient
from src.metric_inputs.dataset_quality_input import DatasetQualityInput
from src.metrics.metric import Metric


class DatasetQualityMetric(Metric):
    LIKES_WEIGHT = 0.5
    DOWNLOADS_WEIGHT = 0.5

    def __init__(self, hf_client: Optional[HuggingFaceClient] = None):
        self.hf_client = hf_client or HuggingFaceClient()

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, DatasetQualityInput)

        # Return 0 for empty or None repo_id (non-HuggingFace URLs)
        if not metric_input.repo_id:
            return 0.0
        dataset_stats = self.hf_client.get_dataset_info(
            metric_input.repo_id
        )
        normalized_likes = dataset_stats.get("normalized_likes", 0)
        likes_score = self.LIKES_WEIGHT * normalized_likes
        normalized_downloads = dataset_stats.get("normalized_downloads", 0)
        downloads_score = self.DOWNLOADS_WEIGHT * normalized_downloads
        return likes_score + downloads_score
