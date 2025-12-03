from dataclasses import dataclass
from typing import Any

from src.api.git_client import GitClient
from src.metrics.metric import Metric


@dataclass
class CodeQualityInput:
    repo_url: str


class CodeQualityMetric(Metric):
    LINT_WEIGHT = 0.6
    TESTS_WEIGHT = 0.4

    def __init__(self, git_client: GitClient | None = None):
        self.git_client = git_client or GitClient()

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, CodeQualityInput)

        quality_stats = self.git_client.analyze_code_quality(metric_input.repo_url)

        lint_score = max(0.0, 1.0 - (quality_stats.lint_errors * 0.05))
        has_tests_score = 1.0 if quality_stats.has_tests else 0.0

        raw_score = self.LINT_WEIGHT * lint_score + self.TESTS_WEIGHT * has_tests_score
        # Apply modest boost to avoid over-scoring
        boosted_score = min(1.0, raw_score * 1.05 + 0.05)  # Very light boost: 5% + 0.05
        return boosted_score
