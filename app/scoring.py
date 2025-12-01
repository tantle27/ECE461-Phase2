import asyncio
import hashlib
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
try:
    from app.secrets_loader import load_registry_secrets

    load_registry_secrets()
except Exception:
    import logging

    logging.exception("secrets_loader failed - continuing without Secrets Manager")
from src.metrics.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


@dataclass
class ModelRating:
    id: str
    generated_at: datetime
    scores: dict[str, Any]
    latencies: dict[str, int]
    summary: dict[str, Any]


_FAST_RATING_MODE = os.environ.get("FAST_RATING_MODE", "auto").lower()


def _should_use_lightweight_metrics() -> bool:
    """Determine whether to skip expensive scoring."""
    return False
def _generate_lightweight_metrics(artifact, model_link: str) -> dict[str, Any]:
    """Produce deterministic pseudo-metrics without network access."""
    base = f"{artifact.metadata.id}:{artifact.metadata.name}:{model_link}"
    digest = hashlib.sha256(base.encode("utf-8", "ignore")).digest()

    def pick(idx: int, lo: float = 0.35, hi: float = 0.95) -> float:
        span = hi - lo
        return round(lo + (digest[idx] / 255.0) * span, 3)

    def latency(idx: int) -> int:
        return 20 + int(digest[idx] % 40)

    metrics = {
        "bus_factor": pick(0),
        "bus_factor_latency": latency(1),
        "code_quality": pick(2),
        "code_quality_latency": latency(3),
        "dataset_quality": pick(4, 0.3, 0.9),
        "dataset_quality_latency": latency(5),
        "dataset_and_code_score": pick(6, 0.4, 1.0),
        "dataset_and_code_score_latency": latency(7),
        "license": pick(8, 0.5, 1.0),
        "license_latency": latency(9),
        "performance_claims": pick(10, 0.25, 0.85),
        "performance_claims_latency": latency(11),
        "ramp_up_time": pick(12, 0.3, 0.9),
        "ramp_up_time_latency": latency(13),
        "reviewedness": pick(14, 0.2, 0.8),
        "reviewedness_latency": latency(15),
        "reproducibility": pick(16, 0.2, 0.85),
        "reproducibility_latency": latency(17),
        "tree_score": pick(18, 0.25, 0.9),
        "tree_score_latency": latency(19),
        "size_score": {
            "raspberry_pi": pick(20, 0.1, 0.6),
            "jetson_nano": pick(21, 0.2, 0.7),
            "desktop_pc": pick(22, 0.3, 0.9),
            "aws_server": pick(23, 0.4, 0.95),
        },
        "size_score_latency": latency(24),
    }

    return metrics


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


def _calculate_net_score(metrics: dict[str, Any]) -> float:
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


def _build_model_rating(artifact, model_link: str, metrics: dict[str, Any], total_latency_ms: int,) -> ModelRating:
    net_score = round(_calculate_net_score(metrics), 2)
    metric_keys = [
        "bus_factor",
        "code_quality",
        "dataset_quality",
        "dataset_and_code_score",
        "license",
        "performance_claims",
        "ramp_up_time",
        "reproducibility",
        "reviewedness",
        "tree_score",
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
        "reproducibility_latency": "reproducibility",
        "reviewedness_latency": "reviewedness",
        "tree_score_latency": "tree_score",
    }

    scores: dict[str, Any] = {key: metrics.get(key) for key in metric_keys if metrics.get(key) is not None}

    # Add placeholder scores for OpenAPI spec compliance (if not present)
    if "reproducibility" not in scores:
        scores["reproducibility"] = 0.0
    if "reviewedness" not in scores:
        scores["reviewedness"] = 0.0
    if "tree_score" not in scores:
        scores["tree_score"] = 0.0
    scores["net_score"] = net_score
    if "size_score" in metrics:
        scores["size_score"] = metrics["size_score"]

    latencies: dict[str, int] = {
        metric_name: int(metrics.get(latency_key, 0) or 0)
        for latency_key, metric_name in latency_key_map.items()
        if latency_key in metrics
    }
    latencies["net_score"] = total_latency_ms

    # Add placeholder latencies for OpenAPI spec compliance (if not present)
    if "reproducibility" not in latencies:
        latencies["reproducibility"] = 0
    if "reviewedness" not in latencies:
        latencies["reviewedness"] = 0
    if "tree_score" not in latencies:
        latencies["tree_score"] = 0

    summary: dict[str, Any] = {
        "category": artifact.metadata.type.upper(),
        "name": artifact.metadata.name,
        "model_link": model_link,
    }
    if "size_score" in metrics:
        summary["size_score"] = metrics["size_score"]

    return ModelRating(
        id=artifact.metadata.id, generated_at=datetime.utcnow(), scores=scores, latencies=latencies, summary=summary,
    )


def _score_artifact_with_metrics(artifact) -> ModelRating:
    if not isinstance(artifact.data, dict):
        raise ValueError("Artifact data must be a JSON object with repository links")

    payload = artifact.data
    code_link: str | None = payload.get("code_link") or payload.get("code") or None
    dataset_link: str | None = payload.get("dataset_link") or payload.get("dataset") or None
    model_link = payload.get("model_link") or payload.get("model_url") or payload.get("model")

    if not model_link:
        raise ValueError("Artifact data must include 'model_link'")

    # Type narrowing: model_link is now guaranteed to be str (not None)
    model_link_str = cast(str, model_link)

    logger.info(
        f"Scoring artifact {artifact.metadata.id}: code_link={code_link}, "
        f"dataset_link={dataset_link}, model_link={model_link_str}"
    )

    start_time = time.time()

    if _should_use_lightweight_metrics():
        metrics = _generate_lightweight_metrics(artifact, model_link_str)
        total_latency_ms = int((time.time() - start_time) * 1000) or 5
    else:
        logger.info("Using full metrics calculation for artifact %s", artifact.metadata.id)
        async def _collect() -> dict[str, Any]:
            return await _METRICS_CALCULATOR.analyze_entry(code_link, dataset_link, model_link_str, set(),)

        metrics = _run_async(_collect())
        total_latency_ms = int((time.time() - start_time) * 1000)
    return _build_model_rating(artifact, model_link_str, metrics, total_latency_ms)


# MetricsCalculator instance (use ThreadPoolExecutor for Lambda compatibility)
# Lambda's /dev/shm is read-only, preventing ProcessPoolExecutor semaphore creation
_THREAD_POOL = ThreadPoolExecutor(max_workers=max(1, os.cpu_count() or 4))
_METRICS_CALCULATOR = MetricsCalculator(cast(ProcessPoolExecutor, _THREAD_POOL), os.environ.get("GH_TOKEN"))
