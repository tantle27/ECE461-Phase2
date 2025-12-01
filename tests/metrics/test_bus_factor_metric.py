from unittest.mock import Mock, patch

import pytest

from src.api.git_client import CommitStats
from src.metrics.bus_factor_metric import BusFactorInput, BusFactorMetric


class TestBusFactorMetric:
    def setup_method(self):
        self.metric = BusFactorMetric()

    @pytest.mark.asyncio
    async def test_calculate_perfect_distribution(self):
        mock_git_client = Mock()
        mock_git_client.analyze_commits.return_value = CommitStats(
            total_commits=100,
            contributors={"author1": 20, "author2": 20, "author3": 20, "author4": 20, "author5": 20,},
            bus_factor=0.8,
        )

        metric = BusFactorMetric(mock_git_client)
        result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

        # Perfect distribution: each author has 20/100 = 0.2 proportion
        # concentration = 5 * (0.2)^2 = 5 * 0.04 = 0.2
        # bus_factor = 1 - 0.2 = 0.8
        expected = 0.8
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_single_author(self):
        mock_git_client = Mock()
        mock_git_client.analyze_commits.return_value = CommitStats(
            total_commits=100, contributors={"author1": 100}, bus_factor=0.0
        )

        metric = BusFactorMetric(mock_git_client)
        result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

        # Single author: concentration = (100/100)^2 = 1.0
        # bus_factor = 1 - 1.0 = 0.0
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_mixed_distribution(self):
        mock_git_client = Mock()
        mock_git_client.analyze_commits.return_value = CommitStats(
            total_commits=100, contributors={"author1": 50, "author2": 30, "author3": 20}, bus_factor=0.62,
        )

        metric = BusFactorMetric(mock_git_client)
        result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

        # concentration = (0.5)^2 + (0.3)^2 + (0.2)^2
        # = 0.25 + 0.09 + 0.04 = 0.38
        # bus_factor = 1 - 0.38 = 0.62
        expected = 0.62
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_empty_repo(self):
        mock_git_client = Mock()
        mock_git_client.analyze_commits.return_value = CommitStats(total_commits=0, contributors={}, bus_factor=0.0)

        metric = BusFactorMetric(mock_git_client)
        result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_none_commit_stats(self):
        mock_git_client = Mock()
        mock_git_client.analyze_commits.return_value = None

        metric = BusFactorMetric(mock_git_client)
        result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        with pytest.raises(AssertionError):
            await self.metric.calculate(123)

    @pytest.mark.asyncio
    async def test_calculate_with_git_client_integration(self):
        with patch("src.metrics.bus_factor_metric.GitClient") as mock_git_client_class:
            mock_git_client = Mock()
            mock_git_client.analyze_commits.return_value = CommitStats(
                total_commits=50, contributors={"author1": 25, "author2": 15, "author3": 10}, bus_factor=0.62,
            )
            mock_git_client_class.return_value = mock_git_client

            metric = BusFactorMetric()
            result = await metric.calculate(BusFactorInput(repo_url="/test/repo"))

            # concentration = (0.5)^2 + (0.3)^2 + (0.2)^2 =
            # 0.25 + 0.09 + 0.04 = 0.38
            # bus_factor = 1 - 0.38 = 0.62
            expected = 0.62
            assert abs(result - expected) < 1e-6
