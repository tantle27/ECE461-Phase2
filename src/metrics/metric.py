from abc import ABC, abstractmethod
from typing import Any


class Metric(ABC):
    @abstractmethod
    async def calculate(self, metric_input: Any) -> float:
        pass
