from unittest.mock import AsyncMock, patch

import pytest

from src.metrics.performance_claims_metric import PerformanceClaimsMetric, PerformanceInput


class TestPerformanceClaimsMetric:
    @pytest.mark.asyncio
    async def test_calculate_with_valid_data(self):
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_performance_claims.return_value = {
            "mentions_benchmarks": 0.8,
            "has_metrics": 0.6,
        }

        # Patch the GenAIClient to use the mock
        with patch("src.metrics.performance_claims_metric.GenAIClient", return_value=mock_gen_ai_client):
            metric = PerformanceClaimsMetric()
            # Create test data
            metric_input = PerformanceInput(readme_text="This is a README with benchmarks and metrics.")

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result - raw score: 0.5 * 0.8 + 0.5 * 0.6 = 0.4 + 0.3 = 0.7
            # Boost: min(1.0, 0.7 * 1.15 + 0.1) = min(1.0, 0.805 + 0.1) = 0.905
            expected_result = min(1.0, 0.7 * 1.15 + 0.1)
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_calculate_with_empty_data(self):
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_performance_claims.return_value = {
            "mentions_benchmarks": 0.0,
            "has_metrics": 0.0,
        }

        # Patch the GenAIClient to use the mock
        with patch("src.metrics.performance_claims_metric.GenAIClient", return_value=mock_gen_ai_client):
            metric = PerformanceClaimsMetric()
            # Create test data
            metric_input = PerformanceInput(readme_text="")

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result - raw score: 0.5 * 0.0 + 0.5 * 0.0 = 0.0
            # Boost: min(1.0, 0.0 * 1.15 + 0.1) = 0.1
            expected_result = 0.1
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_calculate_with_partial_data(self):
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_performance_claims.return_value = {
            "mentions_benchmarks": 0.5,
            "has_metrics": 0.0,
        }

        # Patch the GenAIClient to use the mock
        with patch("src.metrics.performance_claims_metric.GenAIClient", return_value=mock_gen_ai_client):
            # Create test data
            metric_input = PerformanceInput(readme_text="This README mentions benchmarks but no metrics.")
            metric = PerformanceClaimsMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result with boost formula applied
            raw_result = (
                PerformanceClaimsMetric.HAS_BENCHMARKS_WEIGHT * 0.5 + PerformanceClaimsMetric.HAS_METRICS_WEIGHT * 0.0
            )
            expected_result = min(1.0, raw_result * 1.15 + 0.1)
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_calculate_missing_keys(self):
        # Mock the GenAIClient with missing keys
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_performance_claims.return_value = {}

        # Patch the GenAIClient to use the mock
        with patch("src.metrics.performance_claims_metric.GenAIClient", return_value=mock_gen_ai_client):
            # Create test data
            metric_input = PerformanceInput(readme_text="Some README text")
            metric = PerformanceClaimsMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result (boost formula gives 0.1 baseline for 0.0 raw score)
            expected_result = min(1.0, 0.0 * 1.15 + 0.1)  # 0.1 baseline
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        # Test with invalid input type
        metric = PerformanceClaimsMetric()
        with pytest.raises(AssertionError):
            await metric.calculate({"readme_text": "invalid"})
