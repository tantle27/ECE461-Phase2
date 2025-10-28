import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from concurrent.futures import ProcessPoolExecutor
from src.metrics.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


@dataclass
class ModelRating:
    id: str
    generated_at: datetime
    scores: Dict[str, Any]
    latencies: Dict[str, int]
    summary: Dict[str, Any]


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _calculate_net_score(metrics: Dict[str, Any]) -> float:
    weights = {
        "license": 0.30,
        "ramp_up_time": 0.20,
        "dataset_and_code_score": 0.15,
        "performance_claims": 0.10,
        "bus_factor": 0.15,
        "code_quality": 0.05,
        "dataset_quality": 0.05,
    }
    net = sum(metrics.get(metric, 0.0) * weight for metric, weight in weights.items())
    return min(1.0, max(0.0, net))


def _build_model_rating(
    artifact,
    model_link: str,
    metrics: Dict[str, Any],
    total_latency_ms: int,
) -> ModelRating:
    net_score = round(_calculate_net_score(metrics), 2)
    metric_keys = [
        "bus_factor",
        "code_quality",
        "dataset_quality",
        "dataset_and_code_score",
        "license",
        "performance_claims",
        "ramp_up_time",
    ]
    latency_key_map = {
        "bus_factor_latency": "bus_factor",
        "code_quality_latency": "code_quality",
        "dataset_quality_latency": "dataset_quality",
        "dataset_and_code_score_latency": "dataset_and_code_score",
        "license_latency": "license",
        "performance_claims_latency": "performance_claims",
        "ramp_up_time_latency": "ramp_up_time",
        "size_score_latency": "size_score",
    }

    scores: Dict[str, Any] = {
        key: metrics.get(key)
        for key in metric_keys
        if metrics.get(key) is not None
    }
    scores["net_score"] = net_score
    if "size_score" in metrics:
        scores["size_score"] = metrics["size_score"]

    latencies: Dict[str, int] = {
        metric_name: int(metrics.get(latency_key, 0) or 0)
        for latency_key, metric_name in latency_key_map.items()
        if latency_key in metrics
    }
    latencies["net_score"] = total_latency_ms

    summary: Dict[str, Any] = {
        "category": artifact.metadata.type.upper(),
        "name": artifact.metadata.name,
        "model_link": model_link,
    }
    if "size_score" in metrics:
        summary["size_score"] = metrics["size_score"]

    return ModelRating(
        id=artifact.metadata.id,
        generated_at=datetime.utcnow(),
        scores=scores,
        latencies=latencies,
        summary=summary,
    )


def _score_artifact_with_metrics(artifact) -> ModelRating:
    if not isinstance(artifact.data, dict):
        raise ValueError("Artifact data must be a JSON object with repository links")

    payload = artifact.data
    code_link = payload.get("code_link") or payload.get("code")
    dataset_link = payload.get("dataset_link") or payload.get("dataset")
    model_link = (
        payload.get("model_link")
        or payload.get("model_url")
        or payload.get("model")
    )

    if not model_link:
        raise ValueError("Artifact data must include 'model_link'")

    start_time = time.time()

    async def _collect() -> Dict[str, Any]:
        return await _METRICS_CALCULATOR.analyze_entry(
            code_link,
            dataset_link,
            model_link,
            set(),
        )

    metrics = _run_async(_collect())
    total_latency_ms = int((time.time() - start_time) * 1000)
    return _build_model_rating(artifact, model_link, metrics, total_latency_ms)


# MetricsCalculator instance (process pool for CPU-bound tasks)
_PROCESS_POOL = ProcessPoolExecutor(max_workers=max(1, os.cpu_count() or 4))
_METRICS_CALCULATOR = MetricsCalculator(_PROCESS_POOL, os.environ.get("GITHUB_TOKEN"))
