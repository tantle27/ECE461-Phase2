from typing import Any, Optional

from src.api.gen_ai_client import GenAIClient
from src.api.git_client import GitClient
from src.metric_inputs.ramp_up_time_input import RampUpTimeInput
from src.metrics.metric import Metric


class RampUpTimeMetric(Metric):
    LLM_README_WEIGHT = 0.6
    HAS_EXAMPLES_WEIGHT = 0.25
    HAS_DEPENDENCIES_WEIGHT = 0.15

    def __init__(
        self,
        git_client: Optional[GitClient] = None,
        gen_ai_client: Optional[GenAIClient] = None
    ):
        self.git_client = git_client or GitClient()
        self.gen_ai_client = gen_ai_client or GenAIClient()

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, RampUpTimeInput)
        llm_score = await self.gen_ai_client.get_readme_clarity(
            metric_input.readme_text
        )
        repo_results = self.git_client.analyze_ramp_up_time(
            metric_input.repo_path
        )
        examples_score = repo_results.get('has_examples', False)
        dependencies_score = repo_results.get('has_dependencies', False)
        return (
            self.LLM_README_WEIGHT * llm_score +
            self.HAS_EXAMPLES_WEIGHT * examples_score +
            self.HAS_DEPENDENCIES_WEIGHT * dependencies_score
        )
