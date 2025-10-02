from typing import Any, Dict, Optional

from src.api.git_client import GitClient
from src.metric_inputs.size_input import SizeInput


class SizeMetric:
    def __init__(self, git_client: Optional[GitClient] = None):
        self.git_client = git_client or GitClient()

    async def calculate(self, metric_input: Any) -> Dict[str, float]:
        assert isinstance(metric_input, SizeInput)
        return self.git_client.get_repository_size(metric_input.repo_url)
