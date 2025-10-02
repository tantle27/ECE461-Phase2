from typing import Any, Optional

from src.api.gen_ai_client import GenAIClient
from src.metric_inputs.performance_input import PerformanceInput
from src.metrics.metric import Metric


class PerformanceClaimsMetric(Metric):
    HAS_METRICS_WEIGHT = 0.5
    HAS_BENCHMARKS_WEIGHT = 0.5

    def __init__(self, gen_ai_client: Optional[GenAIClient] = None):
        self.gen_ai_client = gen_ai_client or GenAIClient()

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, PerformanceInput)
        result = await self.gen_ai_client.get_performance_claims(
            metric_input.readme_text
            )
        return (
            self.HAS_BENCHMARKS_WEIGHT * result.get("mentions_benchmarks", 0) +
            self.HAS_METRICS_WEIGHT * result.get("has_metrics", 0)
        )
