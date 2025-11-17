"""
Comprehensive tests for src/metrics.py
This file tests the main metrics evaluation functionality.
"""

import sys
import os
from unittest.mock import Mock, patch

# Import from the metrics.py file (not the metrics/ package)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.metrics import (
    InputSpec,
    MetricSpec,
    TREE,
    COMMITS,
    README,
    _m_size,
    _m_busfactor,
    _m_rampup,
    METRICS,
    evaluate_all
)


class TestInputSpec:
    """Test the InputSpec dataclass."""

    def test_input_spec_creation(self):
        """Test creating an InputSpec instance."""
        mock_fetch = Mock()
        spec = InputSpec("test_key", mock_fetch)
        assert spec.key == "test_key"
        assert spec.fetch == mock_fetch

    def test_input_spec_frozen(self):
        """Test that InputSpec is frozen (immutable)."""
        mock_fetch = Mock()
        spec = InputSpec("test_key", mock_fetch)
        
        # Should not be able to modify frozen dataclass
        try:
            spec.key = "modified"
            assert False, "Should not be able to modify frozen dataclass"
        except AttributeError:
            pass  # Expected behavior


class TestMetricSpec:
    """Test the MetricSpec dataclass."""

    def test_metric_spec_creation(self):
        """Test creating a MetricSpec instance."""
        mock_compute = Mock()
        inputs = [TREE, COMMITS]
        spec = MetricSpec("test_metric", inputs, mock_compute)
        
        assert spec.name == "test_metric"
        assert spec.inputs == inputs
        assert spec.compute == mock_compute

    def test_metric_spec_frozen(self):
        """Test that MetricSpec is frozen (immutable)."""
        mock_compute = Mock()
        spec = MetricSpec("test_metric", [TREE], mock_compute)
        
        # Should not be able to modify frozen dataclass
        try:
            spec.name = "modified"
            assert False, "Should not be able to modify frozen dataclass"
        except AttributeError:
            pass  # Expected behavior


class TestPredefinedInputSpecs:
    """Test the predefined input specifications."""

    def test_tree_input_spec(self):
        """Test the TREE input specification."""
        assert TREE.key == "tree"
        assert callable(TREE.fetch)

    def test_commits_input_spec(self):
        """Test the COMMITS input specification."""
        assert COMMITS.key == "commits"
        assert callable(COMMITS.fetch)

    def test_readme_input_spec(self):
        """Test the README input specification."""
        assert README.key == "readme"
        assert callable(README.fetch)


class TestSizeMetric:
    """Test the _m_size metric computation."""

    def test_size_small_repo(self):
        """Test size metric for small repository (≤ 1MB)."""
        data = {"tree": [{"size": "500000"}]}  # 500KB
        result = _m_size(data, "test/repo", None)
        
        assert result["score"] == 1.0
        assert result["details"]["bytes"] == 500000

    def test_size_large_repo(self):
        """Test size metric for large repository (≥ 50MB)."""
        data = {"tree": [{"size": "50000000"}]}  # 50MB
        result = _m_size(data, "test/repo", None)
        
        assert result["score"] == 0.0
        assert result["details"]["bytes"] == 50000000

    def test_size_medium_repo(self):
        """Test size metric for medium repository."""
        data = {"tree": [{"size": "25000000"}]}  # 25MB (halfway between 1MB and 50MB)
        result = _m_size(data, "test/repo", None)
        
        expected_score = max(0.0, 1.0 - (25000000 - 1_000_000) / 49_000_000)
        assert result["score"] == round(expected_score, 3)
        assert result["details"]["bytes"] == 25000000

    def test_size_empty_tree(self):
        """Test size metric with empty tree."""
        data = {"tree": []}
        result = _m_size(data, "test/repo", None)
        
        assert result["score"] == 1.0
        assert result["details"]["bytes"] == 0

    def test_size_missing_tree(self):
        """Test size metric with missing tree data."""
        data = {}
        result = _m_size(data, "test/repo", None)
        
        assert result["score"] == 1.0
        assert result["details"]["bytes"] == 0

    def test_size_multiple_files(self):
        """Test size metric with multiple files."""
        data = {"tree": [{"size": "1000000"}, {"size": "2000000"}, {"size": "500000"}]}
        result = _m_size(data, "test/repo", None)
        
        assert result["details"]["bytes"] == 3500000
        expected_score = max(0.0, 1.0 - (3500000 - 1_000_000) / 49_000_000)
        assert result["score"] == round(expected_score, 3)

    def test_size_missing_size_field(self):
        """Test size metric with files missing size field."""
        data = {"tree": [{"name": "file1"}, {"size": "1000"}]}
        result = _m_size(data, "test/repo", None)
        
        assert result["details"]["bytes"] == 1000


class TestBusFactorMetric:
    """Test the _m_busfactor metric computation."""

    def test_busfactor_single_author(self):
        """Test bus factor with single author (all commits)."""
        data = {"commits": [
            {"author_email": "dev1@example.com"},
            {"author_email": "dev1@example.com"},
            {"author_email": "dev1@example.com"}
        ]}
        result = _m_busfactor(data, "test/repo", None)
        
        assert result["score"] == 0.0  # 1.0 - 1.0 (single author has 100%)
        assert result["details"]["authors"] == 1
        assert result["details"]["top_share"] == 1.0

    def test_busfactor_multiple_authors(self):
        """Test bus factor with multiple authors."""
        data = {"commits": [
            {"author_email": "dev1@example.com"},
            {"author_email": "dev2@example.com"},
            {"author_email": "dev1@example.com"},
            {"author_email": "dev3@example.com"}
        ]}
        result = _m_busfactor(data, "test/repo", None)
        
        # dev1 has 2/4 = 0.5 share
        assert result["score"] == round(1.0 - 0.5, 3)
        assert result["details"]["authors"] == 3
        assert result["details"]["top_share"] == 0.5

    def test_busfactor_author_login_fallback(self):
        """Test bus factor using author_login when email not available."""
        data = {"commits": [
            {"author_login": "dev1"},
            {"author_login": "dev2"},
            {"author_login": "dev1"}
        ]}
        result = _m_busfactor(data, "test/repo", None)
        
        # dev1 has 2/3 share
        expected_score = round(1.0 - (2/3), 3)
        assert result["score"] == expected_score
        assert result["details"]["authors"] == 2

    def test_busfactor_empty_commits(self):
        """Test bus factor with no commits."""
        data = {"commits": []}
        result = _m_busfactor(data, "test/repo", None)
        
        assert result["score"] == 0.0  # 1.0 - 1.0 (no data = single point of failure)
        assert result["details"]["authors"] == 0

    def test_busfactor_missing_commits(self):
        """Test bus factor with missing commits data."""
        data = {}
        result = _m_busfactor(data, "test/repo", None)
        
        assert result["score"] == 0.0
        assert result["details"]["authors"] == 0

    def test_busfactor_commits_without_authors(self):
        """Test bus factor with commits missing author information."""
        data = {"commits": [{"message": "commit1"}, {"message": "commit2"}]}
        result = _m_busfactor(data, "test/repo", None)
        
        assert result["details"]["authors"] == 0


class TestRampUpMetric:
    """Test the _m_rampup metric computation."""

    def test_rampup_good_readme(self):
        """Test ramp up with substantial README."""
        data = {"readme": {"size": 4000, "text": "Detailed documentation..."}}
        result = _m_rampup(data, "test/repo", None)
        
        expected_score = min(1.0, (4000 / 4000) * 0.7 + 0.3)  # 0.7 + 0.3 = 1.0
        assert result["score"] == round(expected_score, 3)
        assert result["details"]["readme_bytes"] == 4000
        assert result["details"]["has_text"] is True

    def test_rampup_short_readme(self):
        """Test ramp up with short README."""
        data = {"readme": {"size": 1000, "text": "Short docs"}}
        result = _m_rampup(data, "test/repo", None)
        
        expected_score = min(1.0, (1000 / 4000) * 0.7 + 0.3)  # 0.175 + 0.3 = 0.475
        assert result["score"] == round(expected_score, 3)
        assert result["details"]["readme_bytes"] == 1000
        assert result["details"]["has_text"] is True

    def test_rampup_no_text(self):
        """Test ramp up with README that has no text content."""
        data = {"readme": {"size": 2000}}  # No text field
        result = _m_rampup(data, "test/repo", None)
        
        expected_score = min(1.0, (2000 / 4000) * 0.7 + 0.0)  # 0.35 + 0 = 0.35
        assert result["score"] == round(expected_score, 3)
        assert result["details"]["has_text"] is False

    def test_rampup_missing_readme(self):
        """Test ramp up with missing README."""
        data = {}
        result = _m_rampup(data, "test/repo", None)
        
        assert result["score"] == 0.0
        assert result["details"]["readme_bytes"] == 0
        assert result["details"]["has_text"] is False

    def test_rampup_empty_readme(self):
        """Test ramp up with empty README."""
        data = {"readme": {}}
        result = _m_rampup(data, "test/repo", None)
        
        assert result["score"] == 0.0
        assert result["details"]["readme_bytes"] == 0
        assert result["details"]["has_text"] is False


class TestMetricsDefinition:
    """Test the METRICS list definition."""

    def test_metrics_count(self):
        """Test that we have the expected number of metrics."""
        assert len(METRICS) == 3

    def test_metrics_names(self):
        """Test that metrics have expected names."""
        names = [m.name for m in METRICS]
        assert "size" in names
        assert "bus_factor" in names  
        assert "ramp_up" in names

    def test_metrics_inputs(self):
        """Test that metrics have correct input dependencies."""
        size_metric = next(m for m in METRICS if m.name == "size")
        assert TREE in size_metric.inputs

        bus_factor_metric = next(m for m in METRICS if m.name == "bus_factor")
        assert COMMITS in bus_factor_metric.inputs

        rampup_metric = next(m for m in METRICS if m.name == "ramp_up")
        assert README in rampup_metric.inputs


class TestEvaluateAll:
    """Test the evaluate_all function."""

    @patch('src.metrics.time.time')
    def test_evaluate_all_success(self, mock_time):
        """Test successful evaluation of all metrics."""
        mock_time.side_effect = [0.0, 1.0]  # Start and end times
        
        # Mock the fetch functions
        mock_tree_data = [{"size": "1000000"}]
        mock_commits_data = [{"author_email": "dev@example.com"}]
        mock_readme_data = {"size": 2000, "text": "Documentation"}
        
        with patch('src.api.github_fetchers.fetch_repo_tree', return_value=mock_tree_data), \
             patch('src.api.github_fetchers.fetch_commits', return_value=mock_commits_data), \
             patch('src.api.github_fetchers.fetch_readme', return_value=mock_readme_data):
            
            result = evaluate_all("test/repo", "main")
            
            assert result["repo"] == "test/repo"
            assert result["ref"] == "main"
            assert result["elapsed_ms"] == 1000  # 1 second = 1000ms
            assert len(result["metrics"]) == 3
            
            # Check that all metrics ran
            metric_names = [m["name"] for m in result["metrics"]]
            assert "size" in metric_names
            assert "bus_factor" in metric_names
            assert "ramp_up" in metric_names

    def test_evaluate_all_with_fetch_errors(self):
        """Test evaluate_all handling fetch errors gracefully."""
        # Mock fetch functions to raise exceptions
        with patch('src.api.github_fetchers.fetch_repo_tree', side_effect=Exception("Fetch error")), \
             patch('src.api.github_fetchers.fetch_commits', side_effect=Exception("API error")), \
             patch('src.api.github_fetchers.fetch_readme', side_effect=Exception("Not found")):
            
            result = evaluate_all("test/repo", None)
            
            assert result["repo"] == "test/repo"
            assert result["ref"] is None
            assert len(result["metrics"]) == 3
            
            # Should have error handling for failed metrics
            for metric in result["metrics"]:
                assert "score" in metric
                assert metric["score"] == 0.0

    def test_evaluate_all_with_compute_errors(self):
        """Test evaluate_all handling compute errors in metrics."""
        # Mock successful fetches but broken compute functions
        with patch('src.api.github_fetchers.fetch_repo_tree', return_value=[]), \
             patch('src.api.github_fetchers.fetch_commits', return_value=[]), \
             patch('src.api.github_fetchers.fetch_readme', return_value={}), \
             patch('src.metrics._m_size', side_effect=Exception("Compute error")):
            
            result = evaluate_all("test/repo")
            
            # Should handle compute errors gracefully
            size_metric = next(m for m in result["metrics"] if m["name"] == "size")
            assert size_metric["score"] == 0.0
            assert "error" in size_metric["details"]

    def test_evaluate_all_custom_metrics(self):
        """Test evaluate_all with custom metrics list."""
        # Create a simple custom metric
        def simple_compute(data, repo, ref):
            return {"score": 0.5, "details": {"custom": True}}
        
        custom_metric = MetricSpec("custom", [TREE], simple_compute)
        
        with patch('src.api.github_fetchers.fetch_repo_tree', return_value=[]):
            result = evaluate_all("test/repo", metrics=[custom_metric])
            
            assert len(result["metrics"]) == 1
            assert result["metrics"][0]["name"] == "custom"
            assert result["metrics"][0]["score"] == 0.5

    def test_evaluate_all_deduplication(self):
        """Test that duplicate input specs are deduplicated."""
        # Create metrics that both use TREE input
        def compute1(data, repo, ref):
            return {"score": 1.0}
        
        def compute2(data, repo, ref):
            return {"score": 0.5}
        
        metric1 = MetricSpec("m1", [TREE], compute1)
        metric2 = MetricSpec("m2", [TREE], compute2)
        
        with patch('src.api.github_fetchers.fetch_repo_tree') as mock_fetch:
            mock_fetch.return_value = []
            
            evaluate_all("test/repo", metrics=[metric1, metric2])
            
            # fetch_repo_tree should only be called once despite two metrics needing it
            assert mock_fetch.call_count == 1

    def test_evaluate_all_no_ref(self):
        """Test evaluate_all with no reference specified."""
        with patch('src.api.github_fetchers.fetch_repo_tree', return_value=[]), \
             patch('src.api.github_fetchers.fetch_commits', return_value=[]), \
             patch('src.api.github_fetchers.fetch_readme', return_value={}):
            
            result = evaluate_all("test/repo")
            
            assert result["repo"] == "test/repo"
            assert result["ref"] is None