from dataclasses import dataclass
from typing import Any

from src.api.git_client import GitClient


@dataclass
class SizeInput:
    repo_url: str


class SizeMetric:
    def __init__(self, git_client: GitClient | None = None):
        self.git_client = git_client or GitClient()

    async def calculate(self, metric_input: Any) -> dict[str, float]:
        assert isinstance(metric_input, SizeInput)
        return self.git_client.get_repository_size(metric_input.repo_url)
