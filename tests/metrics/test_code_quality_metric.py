from unittest.mock import Mock, patch

import pytest

from src.api.git_client import CodeQualityStats
from src.metrics.code_quality_metric import CodeQualityInput, CodeQualityMetric


class TestCodeQualityMetric:
    def setup_method(self):
        self.metric = CodeQualityMetric()

    @pytest.mark.asyncio
    async def test_calculate_perfect_score(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=True, lint_errors=0, code_quality_score=1.0
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # Perfect score: 0.6 * 1.0 + 0.4 * 1.0 = 1.0
        expected = 1.0
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_no_tests_no_errors(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=False, lint_errors=0, code_quality_score=1.0
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # No tests, no errors: 0.6 * 1.0 + 0.4 * 0.0 = 0.6
        # Boost: min(1.0, 0.6 * 1.05 + 0.05) = min(1.0, 0.63 + 0.05) = 0.68
        expected = 0.68
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_with_lint_errors(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=True, lint_errors=10, code_quality_score=0.5  # 1.0 - (10 * 0.05) = 0.5
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # With lint errors and tests: 0.6 * 0.5 + 0.4 * 1.0 = 0.3 + 0.4 = 0.7
        # Boost: min(1.0, 0.7 * 1.05 + 0.05) = min(1.0, 0.735 + 0.05) = 0.785
        expected = 0.785
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_max_lint_errors(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=True, lint_errors=25, code_quality_score=0.0  # 25 * 0.05 = 1.25, clamped to 0
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # Max lint errors with tests: 0.6 * 0.0 + 0.4 * 1.0 = 0.4
        # Boost: min(1.0, 0.4 * 1.05 + 0.05) = min(1.0, 0.42 + 0.05) = 0.47
        expected = 0.47
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_no_tests_with_errors(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=False, lint_errors=5, code_quality_score=0.75  # 1.0 - (5 * 0.05) = 0.75
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # No tests, some errors: 0.6 * 0.75 + 0.4 * 0.0 = 0.45
        # Boost: min(1.0, 0.45 * 1.05 + 0.05) = min(1.0, 0.4725 + 0.05) = 0.5225
        expected = 0.5225
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_worst_case(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=False, lint_errors=25, code_quality_score=0.0
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        # Worst case: 0.6 * 0.0 + 0.4 * 0.0 = 0.0
        # Boost: min(1.0, 0.0 * 1.05 + 0.05) = min(1.0, 0.05) = 0.05
        expected = 0.05
        assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        with pytest.raises(AssertionError):
            await self.metric.calculate(123)

    @pytest.mark.asyncio
    async def test_calculate_with_git_client_integration(self):
        with patch("src.metrics.code_quality_metric.GitClient") as mock_git_client_class:
            mock_git_client = Mock()
            mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
                has_tests=True, lint_errors=8, code_quality_score=0.6  # 1.0 - (8 * 0.05) = 0.6
            )
            mock_git_client_class.return_value = mock_git_client

            metric = CodeQualityMetric()
            result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

            # With tests and some errors: 0.6 * 0.6 + 0.4 * 1.0 = 0.36 + 0.4 = 0.76
            # Boost: min(1.0, 0.76 * 1.05 + 0.05) = min(1.0, 0.798 + 0.05) = 0.848
            expected = 0.848
            assert abs(result - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_calculate_weights_used_correctly(self):
        mock_git_client = Mock()
        mock_git_client.analyze_code_quality.return_value = CodeQualityStats(
            has_tests=True, lint_errors=0, code_quality_score=1.0
        )

        metric = CodeQualityMetric(mock_git_client)
        result = await metric.calculate(CodeQualityInput(repo_url="/test/repo"))

        raw_expected = CodeQualityMetric.LINT_WEIGHT * 1.0 + CodeQualityMetric.TESTS_WEIGHT * 1.0
        # Apply boost: min(1.0, raw_expected * 1.05 + 0.05)
        expected = min(1.0, raw_expected * 1.05 + 0.05)
        assert abs(result - expected) < 1e-6
        assert CodeQualityMetric.LINT_WEIGHT == 0.6
        assert CodeQualityMetric.TESTS_WEIGHT == 0.4
