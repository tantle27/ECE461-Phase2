import logging
from typing import Any, Optional

from src.api.git_client import GitClient
from src.metric_inputs.bus_factor_input import BusFactorInput
from src.metrics.metric import Metric


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

        # Calculate bus factor based on contributor concentration
        concentration = sum(
            (count / commit_stats.total_commits) ** 2
            for count in commit_stats.contributors.values()
        )

        # For exactly two equal contributors, set bus_factor to 0.5
        if (len(commit_stats.contributors) == 2 and
                all(count == commit_stats.total_commits / 2
                    for count in commit_stats.contributors.values())):
            bus_factor = 0.5
        else:
            bus_factor = max(0.0, 1.0 - concentration)

        logging.info(f"Bus factor calculated: {bus_factor}")
        return bus_factor
