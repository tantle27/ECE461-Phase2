import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.api.git_client import GitClient
from src.metrics.metric import Metric


@dataclass
class BusFactorInput:
    repo_url: str


class BusFactorMetric(Metric):
    def __init__(self, git_client: Optional[GitClient] = None):
        self.git_client = git_client or GitClient()

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, BusFactorInput)

        commit_stats = self.git_client.analyze_commits(metric_input.repo_url)
        if not commit_stats or commit_stats.total_commits == 0:
            logging.warning(f"Bus factor: \
                            No commits found for {metric_input.repo_url}")
            return 0.0  # No commits means minimum bus factor

        logging.info(
            f"Bus factor: Found {commit_stats.total_commits} commits, \
                {len(commit_stats.contributors)} contributors")
        logging.info(
            "Bus factor calculated using contributor concentration: %.3f",
            commit_stats.bus_factor
        )
        return commit_stats.bus_factor
