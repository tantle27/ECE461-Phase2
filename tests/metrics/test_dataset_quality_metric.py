from unittest.mock import patch

import pytest

from src.metrics.dataset_quality_metric import DatasetQualityInput, DatasetQualityMetric


class TestDatasetQualityMetric:
    def setup_method(self):
        self.metric = DatasetQualityMetric()

    @pytest.mark.asyncio
    async def test_calculate_typical(self):
        metric_input = DatasetQualityInput(repo_id="test-repo")
        with patch(
            "src.api.hugging_face_client.HuggingFaceClient.get_dataset_info"
        ) as mock_get_info:
            mock_get_info.return_value = {"normalized_likes": 0.8, "normalized_downloads": 0.6}
            result = await self.metric.calculate(metric_input)
            raw_expected = 0.5 * 0.8 + 0.5 * 0.6  # = 0.7
            # Boost: min(1.0, 0.7 * 1.25 + 0.15) = min(1.0, 0.875 + 0.15) = 1.0
            expected = min(1.0, raw_expected * 1.25 + 0.15)
            assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_zero(self):
        metric_input = DatasetQualityInput(repo_id="test-repo")
        with patch(
            "src.api.hugging_face_client.HuggingFaceClient.get_dataset_info"
        ) as mock_get_info:
            mock_get_info.return_value = {"normalized_likes": 0.0, "normalized_downloads": 0.0}
            result = await self.metric.calculate(metric_input)
            # Raw score: 0.5 * 0.0 + 0.5 * 0.0 = 0.0
            # Boost: min(1.0, 0.0 * 1.25 + 0.15) = 0.15
            assert result == 0.15

    @pytest.mark.asyncio
    async def test_calculate_one(self):
        metric_input = DatasetQualityInput(repo_id="test-repo")
        with patch(
            "src.api.hugging_face_client.HuggingFaceClient.get_dataset_info"
        ) as mock_get_info:
            mock_get_info.return_value = {"normalized_likes": 1.0, "normalized_downloads": 1.0}
            result = await self.metric.calculate(metric_input)
            assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        with pytest.raises(AssertionError):
            await self.metric.calculate({"repo_id": "test-repo"})
