from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.metrics.ramp_up_time_metric import RampUpTimeInput, RampUpTimeMetric


class TestRampUpTimeMetric:

    @pytest.mark.asyncio
    async def test_calculate_with_perfect_score(self):
        """Test calculate method with perfect score (all components maxed)."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 1.0

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True,
            'has_dependencies': True
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="Excellent README with clear instructions",
                repo_path="/path/to/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = (
                RampUpTimeMetric.LLM_README_WEIGHT * 1.0 +
                RampUpTimeMetric.HAS_EXAMPLES_WEIGHT * 1 +
                RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT * 1
            )
            assert result == expected_result
            assert result == 1.0  # Should be exactly 1.0

            # Verify method calls
            mock_gen_ai_client.get_readme_clarity.assert_called_once_with(
                "Excellent README with clear instructions"
            )
            mock_git_client.analyze_ramp_up_time.assert_called_once_with(
                "/path/to/repo"
            )

    @pytest.mark.asyncio
    async def test_calculate_with_zero_score(self):
        """Test calculate method with zero score (all components empty)."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.0

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': False,
            'has_dependencies': False
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="",
                repo_path="/path/to/empty/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = 0.0
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_calculate_with_partial_scores(self):
        """Test calculate method with partial scores."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.7

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True,
            'has_dependencies': False
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="Good README but could be clearer",
                repo_path="/path/to/partial/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = (
                RampUpTimeMetric.LLM_README_WEIGHT * 0.7 +
                RampUpTimeMetric.HAS_EXAMPLES_WEIGHT * 1 +
                RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT * 0
            )
            assert result == expected_result
            assert result == pytest.approx(0.67, abs=0.01)
            # 0.6*0.7 + 0.25*1 + 0.15*0

    @pytest.mark.asyncio
    async def test_calculate_with_only_readme_quality(self):
        """Test calculate method with only README quality
        (no examples or dependencies)."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.8

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': False,
            'has_dependencies': False
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="Clear README without dependencies or examples",
                repo_path="/path/to/readme-only/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result (only README weight contributes)
            expected_result = RampUpTimeMetric.LLM_README_WEIGHT * 0.8
            assert result == expected_result
            assert result == pytest.approx(0.48, abs=0.01)  # 0.6 * 0.8

    @pytest.mark.asyncio
    async def test_calculate_with_only_examples_and_dependencies(self):
        """Test calculate method with only examples and
        dependencies (poor README)."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.1

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True,
            'has_dependencies': True
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="Poor README",
                repo_path="/path/to/well-structured/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = (
                RampUpTimeMetric.LLM_README_WEIGHT * 0.1 +
                RampUpTimeMetric.HAS_EXAMPLES_WEIGHT * 1 +
                RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT * 1
            )
            assert result == expected_result
            assert result == pytest.approx(0.46, abs=0.01)
            # 0.6*0.1 + 0.25*1 + 0.15*1

    @pytest.mark.asyncio
    async def test_calculate_missing_keys_in_repo_results(self):
        """Test calculate method when GitClient returns missing keys."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.5

        # Mock the GitClient with missing keys
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {}

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="README with missing repo data",
                repo_path="/path/to/incomplete/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result (should default to False for missing keys)
            expected_result = RampUpTimeMetric.LLM_README_WEIGHT * 0.5
            assert result == expected_result
            assert result == pytest.approx(0.3, abs=0.01)  # 0.6 * 0.5

    @pytest.mark.asyncio
    async def test_calculate_partial_keys_in_repo_results(self):
        """Test calculate method when GitClient returns only some keys."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.6

        # Mock the GitClient with only one key
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True
            # 'has_dependencies' is missing
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="README with partial repo data",
                repo_path="/path/to/partial/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = (
                RampUpTimeMetric.LLM_README_WEIGHT * 0.6 +
                RampUpTimeMetric.HAS_EXAMPLES_WEIGHT * 1 +
                RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT * 0
                # False for missing key
            )
            assert result == expected_result
            assert result == pytest.approx(0.61, abs=0.01)
            # 0.6*0.6 + 0.25*1 + 0.15*0

    @pytest.mark.asyncio
    async def test_calculate_invalid_input_type(self):
        """Test calculate method with invalid input type."""
        metric = RampUpTimeMetric()
        with pytest.raises(AssertionError):
            await metric.calculate(
                {"readme_text": "invalid", "repo_path": "/path"}
            )

    @pytest.mark.asyncio
    async def test_calculate_none_input(self):
        """Test calculate method with None input."""
        metric = RampUpTimeMetric()
        with pytest.raises(AssertionError):
            await metric.calculate(None)

    @pytest.mark.asyncio
    async def test_calculate_string_input(self):
        """Test calculate method with string input."""
        metric = RampUpTimeMetric()
        with pytest.raises(AssertionError):
            await metric.calculate("invalid input")

    @pytest.mark.asyncio
    async def test_weight_constants_sum_to_one(self):
        """Test that the weight constants sum to 1.0."""
        total_weight = (
            RampUpTimeMetric.LLM_README_WEIGHT +
            RampUpTimeMetric.HAS_EXAMPLES_WEIGHT +
            RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT
        )
        assert total_weight == pytest.approx(1.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_weight_constants_values(self):
        """Test that the weight constants have expected values."""
        assert RampUpTimeMetric.LLM_README_WEIGHT == 0.6
        assert RampUpTimeMetric.HAS_EXAMPLES_WEIGHT == 0.25
        assert RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT == 0.15

    @pytest.mark.asyncio
    async def test_calculate_with_gen_ai_client_exception(self):
        """Test calculate method when GenAIClient raises an exception."""
        # Mock the GenAIClient to raise an exception
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.side_effect = Exception(
            "GenAI API error"
        )

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True,
            'has_dependencies': True
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="README text",
                repo_path="/path/to/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method and expect exception
            with pytest.raises(Exception, match="GenAI API error"):
                await metric.calculate(metric_input)

    @pytest.mark.asyncio
    async def test_calculate_with_git_client_exception(self):
        """Test calculate method when GitClient raises an exception."""
        # Mock the GenAIClient
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.8

        # Mock the GitClient to raise an exception
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.side_effect = Exception(
            "Git analysis error"
        )

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="README text",
                repo_path="/path/to/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method and expect exception
            with pytest.raises(Exception, match="Git analysis error"):
                await metric.calculate(metric_input)

    @pytest.mark.asyncio
    async def test_calculate_with_edge_case_scores(self):
        """Test calculate method with edge case floating point scores."""
        # Mock the GenAIClient with very small but non-zero score
        mock_gen_ai_client = AsyncMock()
        mock_gen_ai_client.get_readme_clarity.return_value = 0.001

        # Mock the GitClient
        mock_git_client = MagicMock()
        mock_git_client.analyze_ramp_up_time.return_value = {
            'has_examples': True,
            'has_dependencies': False
        }

        # Patch both clients
        with patch(
            "src.metrics.ramp_up_time_metric.GenAIClient",
            return_value=mock_gen_ai_client
        ), patch(
            "src.metrics.ramp_up_time_metric.GitClient",
            return_value=mock_git_client
        ):
            # Create test data
            metric_input = RampUpTimeInput(
                readme_text="Very poor README",
                repo_path="/path/to/repo"
            )
            metric = RampUpTimeMetric()

            # Call the calculate method
            result = await metric.calculate(metric_input)

            # Assert the result
            expected_result = (
                RampUpTimeMetric.LLM_README_WEIGHT * 0.001 +
                RampUpTimeMetric.HAS_EXAMPLES_WEIGHT * 1 +
                RampUpTimeMetric.HAS_DEPENDENCIES_WEIGHT * 0
            )
            assert result == expected_result
            assert result == pytest.approx(0.2506, abs=0.0001)
            # 0.6*0.001 + 0.25*1 + 0.15*0
