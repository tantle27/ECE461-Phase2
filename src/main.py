import asyncio
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from src.metrics.metrics_calculator import MetricsCalculator


def validate_environment():
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token and not github_token.strip():
        print("Error: Invalid GitHub token", file=sys.stderr)
        sys.exit(1)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        try:
            with open(log_file, 'a'):
                pass
        except (OSError, IOError) as e:
            print(f"Error: Invalid log file path: {e}", file=sys.stderr)
            sys.exit(1)

    log_level = os.environ.get("LOG_LEVEL", "0")
    if log_level == "0" and log_file:
        try:
            with open(log_file, 'w'):
                pass
        except (OSError, IOError) as e:
            print(f"Error: Failed to create blank log file: {e}", file=sys.stderr)
            sys.exit(1)


validate_environment()

LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "0")
LOG_FILE = os.environ.get("LOG_FILE")

log_level_map = {"1": logging.INFO, "2": logging.DEBUG}
log_level = log_level_map.get(LOG_LEVEL_STR)

if LOG_LEVEL_STR != "0" and log_level:
    if LOG_FILE:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            filename=LOG_FILE,
            filemode='a',
            force=True,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            stream=sys.stdout,
            force=True,
        )
    logging.getLogger().setLevel(log_level)
else:
    logging.disable(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL + 1)


def _classify_url(u: str) -> str:
    s = u.strip()
    if not s:
        return "unknown"
    if "huggingface.co/datasets" in s:
        return "dataset"
    if "github.com" in s:
        return "code"
    if "huggingface.co" in s:
        return "model"
    return "unknown"


def parse_url_file(file_path: str) -> List[Tuple[Optional[str], Optional[str], str]]:
    logging.info(f"Reading URLs from: {file_path}")
    try:
        entries: List[Tuple[Optional[str], Optional[str], str]] = []
        last_code: Optional[str] = None
        last_dataset: Optional[str] = None

        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                url = line.strip()
                if not url:
                    continue
                kind = _classify_url(url)

                if kind == "code":
                    last_code = url
                    logging.debug("Line %d classified as CODE", line_num)
                elif kind == "dataset":
                    last_dataset = url
                    logging.debug("Line %d classified as DATASET", line_num)
                elif kind == "model":
                    entries.append((last_code, last_dataset, url))
                    logging.debug("Line %d classified as MODEL -> appended tuple", line_num)
                    last_code = None
                    last_dataset = None
                else:
                    logging.warning("Line %d unknown URL type: %s", line_num, url)

        logging.info(f"Found {len(entries)} model entries.")
        return entries
    except FileNotFoundError:
        msg = f"Error: URL file not found at '{file_path}'."
        logging.error(msg)
        print(msg + " Please check the path.", file=sys.stderr)
        sys.exit(1)


def calculate_net_score(metrics: Dict[str, Any]) -> float:
    weights = {
        "license": 0.30,
        "ramp_up_time": 0.20,
        "dataset_and_code_score": 0.15,
        "performance_claims": 0.10,
        "bus_factor": 0.15,
        "code_quality": 0.05,
        "dataset_quality": 0.05,
    }
    net_score = sum(metrics.get(metric, 0.0) * weight for metric, weight in weights.items())
    return min(1.0, max(0.0, net_score))


async def analyze_entry(
    entry: Tuple[Optional[str], Optional[str], str],
    process_pool: ThreadPoolExecutor,
    encountered_datasets: set,
) -> Dict[str, Any]:
    code_link, dataset_link, model_link = entry
    start_time = time.time()

    github_token = os.environ.get("GITHUB_TOKEN")
    calculator = MetricsCalculator(process_pool, github_token)
    local_metrics = await calculator.analyze_entry(
        code_link, dataset_link, model_link, encountered_datasets
    )

    net_score = calculate_net_score(local_metrics)
    total_latency_ms = int((time.time() - start_time) * 1000)

    scorecard: Dict[str, Any] = {
        "name": model_link.split("/")[-1],
        "category": "MODEL",
        "net_score": round(net_score, 2),
        "net_score_latency": total_latency_ms,
        "ramp_up_time": local_metrics.get("ramp_up_time", 0.0),
        "ramp_up_time_latency": local_metrics.get("ramp_up_time_latency", 0),
        "bus_factor": local_metrics.get("bus_factor", 0.0),
        "bus_factor_latency": local_metrics.get("bus_factor_latency", 0),
        "performance_claims": local_metrics.get("performance_claims", 0.0),
        "performance_claims_latency": local_metrics.get("performance_claims_latency", 0),
        "license": local_metrics.get("license", 0.0),
        "license_latency": local_metrics.get("license_latency", 0),
        "size_score": local_metrics.get("size_score", {}),
        "size_score_latency": local_metrics.get("size_score_latency", 0),
        "dataset_and_code_score": local_metrics.get("dataset_and_code_score", 0.0),
        "dataset_and_code_score_latency": local_metrics.get("dataset_and_code_score_latency", 0),
        "dataset_quality": local_metrics.get("dataset_quality", 0.0),
        "dataset_quality_latency": local_metrics.get("dataset_quality_latency", 0),
        "code_quality": local_metrics.get("code_quality", 0.0),
        "code_quality_latency": local_metrics.get("code_quality_latency", 0),
    }
    return scorecard


async def process_entries(entries: List[Tuple[Optional[str], Optional[str], str]]) -> None:
    logging.info("Processing %d entries", len(entries))
    max_workers = os.cpu_count() or 4
    logging.info("Using %d worker threads", max_workers)

    encountered_datasets: set[str] = set()

    with ThreadPoolExecutor(max_workers=max_workers) as process_pool:
        tasks = [analyze_entry(entry, process_pool, encountered_datasets) for entry in entries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error("Analysis task failed: %s", result)
                entry = entries[i]
                _, _, model_link = entry
                default_scorecard = {
                    "name": model_link.split("/")[-1] if model_link else "unknown",
                    "category": "MODEL",
                    "net_score": 0.0,
                    "net_score_latency": 0,
                    "ramp_up_time": 0.0,
                    "ramp_up_time_latency": 0,
                    "bus_factor": 0.0,
                    "bus_factor_latency": 0,
                    "performance_claims": 0.0,
                    "performance_claims_latency": 0,
                    "license": 0.0,
                    "license_latency": 0,
                    "size_score": {},
                    "size_score_latency": 0,
                    "dataset_and_code_score": 0.0,
                    "dataset_and_code_score_latency": 0,
                    "dataset_quality": 0.0,
                    "dataset_quality_latency": 0,
                    "code_quality": 0.0,
                    "code_quality_latency": 0,
                }
                print(json.dumps(default_scorecard, separators=(",", ":")))
            else:
                print(json.dumps(result, separators=(",", ":")))


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m src.main <URL_FILE>", file=sys.stderr)
        sys.exit(1)

    url_file = sys.argv[1]
    entries = parse_url_file(url_file)

    try:
        if entries:
            asyncio.run(process_entries(entries))
        else:
            # No model URLs found is considered a failure for the URL-file command
            print("Error: No model URLs found in the provided file.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        logging.error("Unhandled error in URL processing: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()