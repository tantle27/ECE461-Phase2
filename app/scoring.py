import asyncio
import hashlib
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast
logger = logging.getLogger(__name__)
try:
    from app.secrets_loader import load_registry_secrets
    load_registry_secrets()
except Exception:
    logger.exception("secrets_loader failed - continuing without Secrets Manager")
from src.metrics.metrics_calculator import MetricsCalculator


@dataclass
class ModelRating:
    id: str
    generated_at: datetime
    scores: dict[str, Any]
    latencies: dict[str, int]
    summary: dict[str, Any]





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


# Heuristic fast metrics removed.


def _score_artifact_with_metrics(artifact) -> ModelRating:
    if not isinstance(artifact.data, dict):
        raise ValueError("Artifact data must be a JSON object with repository links")

    payload = artifact.data
    code_link_raw = payload.get("code_link") or payload.get("code") or None
    dataset_link_raw = payload.get("dataset_link") or payload.get("dataset") or None
    model_link = payload.get("model_link") or payload.get("model_url") or payload.get("model")

    if not model_link:
        raise ValueError("Artifact data must include 'model_link'")

    model_link_str = str(model_link).strip() if model_link else ""
    code_link: Optional[str] = (
        str(code_link_raw).strip() if isinstance(code_link_raw, str) else None
    )
    dataset_link: Optional[str] = (
        str(dataset_link_raw).strip() if isinstance(dataset_link_raw, str) else None
    )

    # Coerce blank strings to None
    if code_link == "":
        code_link = None
    if dataset_link == "":
        dataset_link = None

    logger.info(
        f"Scoring artifact {artifact.metadata.id}: code_link={code_link}, "
        f"dataset_link={dataset_link}, model_link={model_link_str}"
    )

    start_time = time.time()

    # Always compute legitimate metrics via MetricsCalculator

    async def _collect() -> dict[str, Any]:
        calc = _get_metrics_calculator()
        return await calc.analyze_entry(code_link, dataset_link, model_link_str, set())

    metrics = _run_async(_collect())
    total_latency_ms = int((time.time() - start_time) * 1000)
    metrics = _ensure_nonzero_metrics(artifact, model_link_str, metrics)
    logger.info(
        "SCORE_FIX: metrics summary id=%s keys=%s critical=%s",
        artifact.metadata.id,
        sorted(metrics.keys()),
        {k: metrics.get(k) for k in ("license", "bus_factor", "code_quality", "dataset_quality")},
    )
    return _build_model_rating(artifact, model_link_str, metrics, total_latency_ms)


def _rate_one(artifact) -> ModelRating:
    """Small wrapper to rate a single artifact, suitable for thread pool execution."""
    return _score_artifact_with_metrics(artifact)


def rate_artifacts_concurrently(artifacts: list[Any], max_workers: int | None = None) -> list[ModelRating]:
    """Rate multiple artifacts concurrently using ThreadPoolExecutor.

    - Uses thread pool to avoid ProcessPool limitations on Lambda.
    - Returns a list of ModelRating in the same order as input artifacts.
    - Exceptions are logged and skipped to keep other ratings proceeding.
    """
    if not artifacts:
        return []
    workers = max_workers or max(4, (os.cpu_count() or 4))
    results: dict[int, ModelRating] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_rate_one, art): idx for idx, art in enumerate(artifacts)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                rating = fut.result()
                results[idx] = rating
            except Exception as exc:
                logger.exception("Concurrent rating failed for idx=%s: %s", idx, exc)
    # Preserve input order
    ordered: list[ModelRating] = []
    for i in range(len(artifacts)):
        if i in results:
            ordered.append(results[i])
    return ordered


def _ensure_nonzero_metrics(artifact, model_link: str, metrics: dict[str, Any]) -> dict[str, Any]:
    critical = [
        "bus_factor",
        "code_quality",
        "license",
        "ramp_up_time",
        "dataset_quality",
        "performance_claims",
        "dataset_and_code_score",
    ]
    if any(metrics.get(key) not in (None, 0, 0.0, -1) for key in critical):
        return metrics
    logger.warning(
        "SCORE_FIX: metrics missing for %s (code=%s) – keeping raw zeros",
        artifact.metadata.id,
        (artifact.data or {}).get("code_link"),
    )
    return metrics


# MetricsCalculator instance (use ThreadPoolExecutor for Lambda compatibility)
# Lambda's /dev/shm is read-only, preventing ProcessPoolExecutor semaphore creation
_THREAD_POOL = ThreadPoolExecutor(max_workers=max(1, os.cpu_count() or 4))
_METRICS_CALCULATOR: MetricsCalculator | None = None


def _get_metrics_calculator() -> MetricsCalculator:
    """Lazy initialization of MetricsCalculator to ensure GH_TOKEN is loaded from secrets."""
    global _METRICS_CALCULATOR
    if _METRICS_CALCULATOR is None:
        gh_token = os.environ.get("GH_TOKEN")
        logger.info("Initializing MetricsCalculator with GH_TOKEN=%s", "present" if gh_token else "missing")
        _METRICS_CALCULATOR = MetricsCalculator(cast(ProcessPoolExecutor, _THREAD_POOL), gh_token)
    return _METRICS_CALCULATOR
