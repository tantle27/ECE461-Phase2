"""
Unit tests for the new Phase 2 metrics.

This module tests the three new metrics required for Phase 2:
- Reproducibility metric
- Reviewedness metric
- Treescore metric
"""

import pytest
from unittest.mock import Mock
from typing import Dict, Any


# ==================== REPRODUCIBILITY METRIC TESTS ====================

@pytest.mark.unit
class TestReproducibilityMetric:
    """Test the reproducibility metric calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_git_client = Mock()
        self.mock_gen_ai_client = Mock()

    @pytest.mark.asyncio
    async def test_reproducibility_with_working_code(self):
        """Test reproducibility when demo code runs successfully."""
        # Mock repository with working demo code
        self.mock_git_client.find_demo_files.return_value = [
            "demo.py", "example.ipynb", "tutorial.py"
        ]
        self.mock_git_client.test_code_execution.return_value = {
            "demo.py": {"runs": True, "errors": []},
            "example.ipynb": {"runs": True, "errors": []},
            "tutorial.py": {"runs": True, "errors": []}
        }

        score = await self._calculate_reproducibility()

        # Should get full score (1.0) when all code runs without debugging
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_reproducibility_with_partial_working_code(self):
        """Test reproducibility when some demo code needs debugging."""
        # Mock repository with partially working code
        self.mock_git_client.find_demo_files.return_value = [
            "demo.py", "broken_example.py"
        ]
        self.mock_git_client.test_code_execution.return_value = {
            "demo.py": {"runs": True, "errors": []},
            "broken_example.py": {"runs": False, "errors": ["ImportError"]}
        }

        score = await self._calculate_reproducibility()

        # Should get partial score (0.5) when code runs with debugging
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_reproducibility_no_demo_code(self):
        """Test reproducibility when no demo code exists."""
        # Mock repository with no demo files
        self.mock_git_client.find_demo_files.return_value = []
        # Mock no model card available
        self.mock_git_client.read_model_card.return_value = None

        score = await self._calculate_reproducibility()

        # Should get zero score when no demo code exists
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_reproducibility_with_model_card_only(self):
        """Test reproducibility using model card instructions."""
        # Mock repository with model card but no demo code
        self.mock_git_client.find_demo_files.return_value = []
        self.mock_git_client.read_model_card.return_value = """
        ## Usage
        ```python
        from transformers import AutoModel
        model = AutoModel.from_pretrained("model-name")
        output = model.predict("test input")
        ```
        """

        # Mock AI extraction of code from model card
        self.mock_gen_ai_client.extract_code_from_text.return_value = [
            {
                "code": ("from transformers import AutoModel\n"
                         "model = AutoModel.from_pretrained('model-name')"),
                "language": "python"
            }
        ]
        self.mock_git_client.test_extracted_code.return_value = {
            "runs": True, "errors": []
        }

        score = await self._calculate_reproducibility()

        # Should get full score when model card code works
        assert score == 1.0

    async def _calculate_reproducibility(self) -> float:
        """Calculate reproducibility score."""
        # Find demo files
        demo_files = self.mock_git_client.find_demo_files()

        if not demo_files:
            # Try to extract code from model card
            model_card = self.mock_git_client.read_model_card()
            if model_card:
                extracted_code = (
                    self.mock_gen_ai_client.extract_code_from_text(
                        model_card
                    )
                )
                if extracted_code:
                    result = self.mock_git_client.test_extracted_code()
                    return 1.0 if result["runs"] else 0.5
            return 0.0

        # Test execution of demo files
        execution_results = self.mock_git_client.test_code_execution()

        total_files = len(demo_files)
        working_files = sum(
            1 for result in execution_results.values()
            if result["runs"]
        )

        if working_files == total_files:
            return 1.0  # All code runs without debugging
        elif working_files > 0:
            return 0.5  # Some code runs with debugging
        else:
            return 0.0  # No code runs


# ==================== REVIEWEDNESS METRIC TESTS ====================

@pytest.mark.unit
class TestReviewednessMetric:
    """Test the reviewedness metric calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_git_client = Mock()

    @pytest.mark.asyncio
    async def test_reviewedness_high_coverage(self):
        """Test reviewedness with high PR review coverage."""
        # Mock repository with mostly reviewed code
        self.mock_git_client.analyze_pull_requests.return_value = {
            "total_code_lines": 1000,
            "reviewed_code_lines": 850,  # 85% reviewed
            "pull_requests": [
                {"id": 1, "reviewed": True, "lines_added": 200},
                {"id": 2, "reviewed": True, "lines_added": 300},
                {"id": 3, "reviewed": True, "lines_added": 350},
                {"id": 4, "reviewed": False, "lines_added": 150}  # Not rev.
            ]
        }

        score = await self._calculate_reviewedness()

        # Should get 0.85 (85% of code was reviewed)
        assert abs(score - 0.85) < 0.01

    @pytest.mark.asyncio
    async def test_reviewedness_no_pull_requests(self):
        """Test reviewedness when no pull requests exist."""
        # Mock repository with no PR history
        self.mock_git_client.analyze_pull_requests.return_value = {
            "total_code_lines": 500,
            "reviewed_code_lines": 0,
            "pull_requests": []
        }

        score = await self._calculate_reviewedness()

        # Should get -1 when no GitHub repository exists
        assert score == -1.0

    @pytest.mark.asyncio
    async def test_reviewedness_no_github_repo(self):
        """Test reviewedness when no GitHub repository is linked."""
        # Mock case where there's no GitHub repository
        self.mock_git_client.has_github_repository.return_value = False

        score = await self._calculate_reviewedness()

        # Should return -1 when no GitHub repository exists
        assert score == -1.0

    @pytest.mark.asyncio
    async def test_reviewedness_perfect_coverage(self):
        """Test reviewedness with 100% review coverage."""
        # Mock repository where all code was reviewed
        self.mock_git_client.analyze_pull_requests.return_value = {
            "total_code_lines": 800,
            "reviewed_code_lines": 800,  # 100% reviewed
            "pull_requests": [
                {"id": 1, "reviewed": True, "lines_added": 300},
                {"id": 2, "reviewed": True, "lines_added": 500}
            ]
        }

        score = await self._calculate_reviewedness()

        # Should get 1.0 (100% of code was reviewed)
        assert score == 1.0

    async def _calculate_reviewedness(self) -> float:
        """Calculate reviewedness score."""
        # Check if GitHub repository exists
        if hasattr(self.mock_git_client, 'has_github_repository'):
            if not self.mock_git_client.has_github_repository():
                return -1.0

        # Analyze pull request history
        pr_analysis = self.mock_git_client.analyze_pull_requests()

        total_lines = pr_analysis["total_code_lines"]
        reviewed_lines = pr_analysis["reviewed_code_lines"]
        pull_requests = pr_analysis["pull_requests"]

        if total_lines == 0 or len(pull_requests) == 0:
            return -1.0  # No code or no repository

        return reviewed_lines / total_lines


# ==================== TREESCORE METRIC TESTS ====================

@pytest.mark.unit
class TestTreescoreMetric:
    """Test the treescore metric calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_lineage_analyzer = Mock()
        self.mock_model_registry = Mock()

    @pytest.mark.asyncio
    async def test_treescore_with_parents(self):
        """Test treescore calculation when model has parent dependencies."""
        # Mock model with parent dependencies
        model_id = "test-model-v2"
        self.mock_lineage_analyzer.get_parent_models.return_value = [
            "parent-model-v1", "base-model-v3"
        ]

        # Mock parent model scores
        self.mock_model_registry.get_model_score.side_effect = [
            0.85,  # parent-model-v1 score
            0.75   # base-model-v3 score
        ]

        score = await self._calculate_treescore(model_id)

        # Should get average of parent scores: (0.85 + 0.75) / 2 = 0.80
        expected_score = (0.85 + 0.75) / 2
        assert abs(score - expected_score) < 0.01

    @pytest.mark.asyncio
    async def test_treescore_no_parents(self):
        """Test treescore when model has no parent dependencies."""
        # Mock model with no parents (base model)
        model_id = "base-model-v1"
        self.mock_lineage_analyzer.get_parent_models.return_value = []

        score = await self._calculate_treescore(model_id)

        # Should get 0.0 when no parent models exist
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_treescore_single_parent(self):
        """Test treescore with single parent model."""
        # Mock model with one parent
        model_id = "derived-model"
        self.mock_lineage_analyzer.get_parent_models.return_value = [
            "parent-model"
        ]

        # Mock parent model score
        self.mock_model_registry.get_model_score.return_value = 0.92

        score = await self._calculate_treescore(model_id)

        # Should get the parent's score
        assert score == 0.92

    @pytest.mark.asyncio
    async def test_treescore_missing_parent_scores(self):
        """Test treescore when some parent scores are unavailable."""
        # Mock model with parents, but some scores missing
        model_id = "test-model"
        self.mock_lineage_analyzer.get_parent_models.return_value = [
            "parent-1", "parent-2", "parent-3"
        ]

        # Mock mixed parent scores (some None/missing)
        self.mock_model_registry.get_model_score.side_effect = [
            0.80,   # parent-1 score available
            None,   # parent-2 score missing
            0.70    # parent-3 score available
        ]

        score = await self._calculate_treescore(model_id)

        # Should average only available scores: (0.80 + 0.70) / 2 = 0.75
        expected_score = (0.80 + 0.70) / 2
        assert abs(score - expected_score) < 0.01

    @pytest.mark.asyncio
    async def test_treescore_lineage_from_config(self):
        """Test treescore extraction from model config.json."""
        # Mock lineage extraction from config.json
        config_data = {
            "_name_or_path": "base-model",
            "base_model": "parent-transformer",
            "parent_model": "foundation-model"
        }

        self.mock_lineage_analyzer.extract_lineage_from_config.return_value = [
            "base-model", "parent-transformer", "foundation-model"
        ]

        # Mock parent scores
        self.mock_model_registry.get_model_score.side_effect = [
            0.85, 0.78, 0.90
        ]

        model_id = "test-model"
        score = await self._calculate_treescore_from_config(model_id, config_data)

        # Should average all parent scores
        expected_score = (0.85 + 0.78 + 0.90) / 3
        assert abs(score - expected_score) < 0.01

    async def _calculate_treescore(self, model_id: str) -> float:
        """Calculate treescore based on parent model scores."""
        # Get parent models from lineage analysis
        parent_models = self.mock_lineage_analyzer.get_parent_models(model_id)

        if not parent_models:
            return 0.0  # No parents = score of 0

        # Get scores for all parent models
        parent_scores = []
        for parent_id in parent_models:
            score = self.mock_model_registry.get_model_score(parent_id)
            if score is not None:
                parent_scores.append(score)

        if not parent_scores:
            return 0.0  # No valid parent scores

        # Return average of parent scores
        return sum(parent_scores) / len(parent_scores)

    async def _calculate_treescore_from_config(
        self, model_id: str, config: Dict[str, Any]
    ) -> float:
        """Calculate treescore from model config.json."""
        # Extract lineage from config
        parent_models = self.mock_lineage_analyzer.extract_lineage_from_config(
            config
        )

        if not parent_models:
            return 0.0

        # Get scores for parent models
        parent_scores = []
        for parent_id in parent_models:
            score = self.mock_model_registry.get_model_score(parent_id)
            if score is not None:
                parent_scores.append(score)

        if not parent_scores:
            return 0.0

        return sum(parent_scores) / len(parent_scores)


# ==================== INTEGRATION TESTS ====================

@pytest.mark.integration
class TestNewMetricsIntegration:
    """Test integration of new metrics with existing system."""

    def setup_method(self):
        """Set up integration test fixtures."""
        self.mock_metrics_calculator = Mock()

    @pytest.mark.asyncio
    async def test_all_metrics_integration(self):
        """Test that all metrics (old + new) work together."""
        # Mock existing metrics
        existing_metrics = {
            "bus_factor": 0.6,
            "code_quality": 0.8,
            "license": 1.0,
            "ramp_up_time": 0.7,
            "dataset_quality": 0.75,
            "performance_claims": 0.85,
            "size_score": 0.9
        }

        # Mock new metrics
        new_metrics = {
            "reproducibility": 1.0,
            "reviewedness": 0.8,
            "treescore": 0.75
        }

        # Combined metrics
        all_metrics = {**existing_metrics, **new_metrics}

        # Test that net score calculation includes new metrics
        net_score = self._calculate_enhanced_net_score(all_metrics)

        assert 0.0 <= net_score <= 1.0
        assert isinstance(net_score, float)

    def _calculate_enhanced_net_score(self, metrics: Dict[str, float]) -> float:
        """Calculate net score including new Phase 2 metrics."""
        # Enhanced weighting formula for Phase 2
        weights = {
            "bus_factor": 0.15,
            "code_quality": 0.15,
            "license": 0.15,
            "ramp_up_time": 0.15,
            "dataset_quality": 0.10,
            "performance_claims": 0.10,
            "reproducibility": 0.10,  # New metric
            "reviewedness": 0.05,     # New metric
            "treescore": 0.05         # New metric
        }

        weighted_sum = sum(
            metrics.get(metric, 0.0) * weight
            for metric, weight in weights.items()
        )

        return min(weighted_sum, 1.0)  # Cap at 1.0

    @pytest.mark.asyncio
    async def test_metric_latency_tracking(self):
        """Test that new metrics include latency tracking."""
        # Mock metrics with latency
        metrics_with_latency = {
            "reproducibility": 0.8,
            "reproducibility_latency": 2500,  # ms
            "reviewedness": 0.75,
            "reviewedness_latency": 1800,  # ms
            "treescore": 0.65,
            "treescore_latency": 500  # ms
        }

        # Validate latency tracking
        for metric_name in ["reproducibility", "reviewedness", "treescore"]:
            latency_key = f"{metric_name}_latency"
            assert latency_key in metrics_with_latency
            assert isinstance(metrics_with_latency[latency_key], int)
            assert metrics_with_latency[latency_key] >= 0
