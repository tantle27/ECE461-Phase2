import asyncio
import logging
import re
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

from src.api.gen_ai_client import GenAIClient
from src.api.git_client import GitClient
from src.api.hugging_face_client import HuggingFaceClient
from src.metrics.bus_factor_metric import BusFactorInput, BusFactorMetric
from src.metrics.code_quality_metric import CodeQualityInput, CodeQualityMetric
from src.metrics.dataset_quality_metric import DatasetQualityInput, DatasetQualityMetric
from src.metrics.dataset_code_metric import DatasetCodeMetric, DatasetCodeInput
from src.metrics.license_metric import LicenseInput, LicenseMetric
from src.metrics.performance_claims_metric import PerformanceClaimsMetric, PerformanceInput
from src.metrics.ramp_up_time_metric import RampUpTimeInput, RampUpTimeMetric
from src.metrics.size_metric import SizeInput, SizeMetric
logger = logging.getLogger(__name__)


def extract_hf_repo_id(url: str) -> str:
    """
    Extracts the repo_id from a Hugging Face URL (dataset or model).
    Examples:
    - https://huggingface.co/datasets/allenai/c4 -> allenai/c4
    - https://huggingface.co/ibm-granite/granite-docling-258M ->
      ibm-granite/granite-docling-258M
    - https://huggingface.co/datasets/bookcorpus/bookcorpus ->
      bookcorpus/bookcorpus
    """
    # Remove trailing slashes and fragments
    url = url.rstrip("/")

    # Pattern for datasets: huggingface.co/datasets/{org}/{name} or
    # huggingface.co/datasets/{name}
    dataset_match = re.search(r"huggingface\.co/datasets/([^/?#]+(?:/[^/?#]+)?)", url)
    if dataset_match:
        return dataset_match.group(1)

    # Pattern for regular models: huggingface.co/{org}/{name} or
    # huggingface.co/{name}.
    # But exclude spaces: huggingface.co/spaces/{org}/{name}
    model_match = re.search(r"huggingface\.co/(?!spaces/)([^/?#]+(?:/[^/?#]+)?)", url)
    if model_match:
        return model_match.group(1)

    raise ValueError(f"Invalid Hugging Face URL: {url}")


def is_code_repository(url: str) -> bool:
    """
    Determines if a URL is a cloneable code repository:
    - GitHub, GitLab, Bitbucket
    - Hugging Face repos (models and spaces). Datasets are excluded here.

    Note: Hugging Face model pages are backed by git repos and can be cloned
    via HTTPS (with or without .git suffix). We treat them as code repos so
    we can compute metrics (README, size, basic signals) instead of zeros.
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    host = parsed.netloc
    path = parsed.path or ""
    if any(h in host for h in ("github.com", "gitlab.com", "bitbucket.org")):
        return True
    if "huggingface.co" in host:
        # Exclude datasets from code repo classification
        if "/datasets/" in path:
            return False
        return True  # models and spaces
    return False


def is_dataset_url(url: str) -> bool:
    """
    Determines if a URL is a dataset URL.
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    return (
        ("huggingface.co" in parsed.netloc and "/datasets/" in parsed.path)
        or "image-net.org" in parsed.netloc
        or "kaggle.com" in parsed.netloc
        or "archive.ics.uci.edu" in parsed.netloc  # UCI ML Repository
        or
        # Add other dataset source patterns as needed
        "/datasets/" in parsed.path
    )


def is_model_url(url: str) -> bool:
    """
    Determines if a URL is a Hugging Face model URL.
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    return "huggingface.co" in parsed.netloc and "/datasets/" not in parsed.path and "/spaces/" not in parsed.path


class MetricsCalculator:
    """
    Comprehensive metrics calculator for ML model evaluation.

    Analyzes code repositories, datasets, and ML models to compute various
    quality metrics including bus factor, code quality, license compliance,
    ramp-up time, dataset quality,
    performance claims, and overall size metrics.
    Supports concurrent execution and handles
    different URL types (GitHub, GitLab, Hugging Face datasets/models/spaces).

    The calculator can process entries containing
    code, dataset, and model links,
    handling cases where code or dataset links may be missing.
    """

    def __init__(self, process_pool: ProcessPoolExecutor, GH_TOKEN: str | None = None):
        """
        Initialize the metrics calculator with necessary API clients and
        metric instances.

        Args:
            process_pool: ProcessPoolExecutor for CPU-bound operations
            GH_TOKEN: Optional[str] = None
        """
        self.git_client = GitClient(GH_TOKEN)
        self.gen_ai_client = GenAIClient()
        self.hf_client = HuggingFaceClient()
        self.process_pool = process_pool
        self.thread_pool = ThreadPoolExecutor(max_workers=10)

        # Initialize metric instances
        self.bus_factor_metric = BusFactorMetric(self.git_client)
        self.code_quality_metric = CodeQualityMetric(self.git_client)
        self.license_metric = LicenseMetric(self.git_client)
        self.size_metric = SizeMetric(self.git_client)
        self.ramp_up_time_metric = RampUpTimeMetric(self.git_client, self.gen_ai_client)
        self.dataset_quality_metric = DatasetQualityMetric(self.hf_client)
        self.performance_claims_metric = PerformanceClaimsMetric(self.gen_ai_client)
        self.dataset_code_metric = DatasetCodeMetric(self.git_client)

    async def _run_cpu_bound(self, func, *args) -> Any:
        """
        Runs a CPU-bound function in the process pool and measures latency.

        Args:
            func: Function to execute
            *args: Arguments to pass to the function

        Returns:
            Tuple of (result, latency_ms)
        """
        loop = asyncio.get_running_loop()
        start_time = time.time()

        # For async functions, run them directly in the current event loop
        if asyncio.iscoroutinefunction(func):
            result = await func(*args)
        else:
            result = await loop.run_in_executor(self.process_pool, func, *args)

        latency = int((time.time() - start_time) * 1000)
        return result, latency

    async def analyze_repository(self, url: str) -> dict[str, Any]:
        """
        Clones and analyzes a single repository,
        running all metric calculations
        in parallel for optimal performance.

        Args:
            url: Repository URL to analyze

        Returns:
            Dictionary containing all computed metrics and their latencies
        """
        logger.info("METRICS: begin_repo_analysis url=%s", url)

        # Early exit for Hugging Face model URLs without code repository
        # These will have all zero scores anyway, no need to clone
        if is_model_url(url) and not is_code_repository(url):
            logger.info("METRICS: skip repo clone (model-only) url=%s", url)
            return self._get_default_metrics()

        loop = asyncio.get_running_loop()

        repo_path = await loop.run_in_executor(self.thread_pool, self.git_client.clone_repository, url)

        if not repo_path:
            logger.error(f"Failed to clone repository: {url}")
            return self._get_default_metrics()

        logger.info("METRICS: cloned repo url=%s path=%s", url, repo_path)

        try:
            # Extract repo_id if this is a Hugging Face dataset URL
            repo_id = None
            if "huggingface.co/datasets/" in url:
                try:
                    repo_id = extract_hf_repo_id(url)
                except ValueError as e:
                    logger.error(str(e))
            bus_factor_task = self._run_cpu_bound(self.bus_factor_metric.calculate, BusFactorInput(repo_url=repo_path))
            code_quality_task = self._run_cpu_bound(
                self.code_quality_metric.calculate, CodeQualityInput(repo_url=repo_path)
            )
            license_task = self._run_cpu_bound(self.license_metric.calculate, LicenseInput(repo_url=repo_path))
            readme_text = self.git_client.read_readme(repo_path) or ""
            ramp_up_task = self._run_cpu_bound(
                self.ramp_up_time_metric.calculate, RampUpTimeInput(repo_path=repo_path, readme_text=readme_text),
            )
            dataset_quality_task = self._run_cpu_bound(
                self.dataset_quality_metric.calculate,
                (DatasetQualityInput(repo_id=repo_id) if repo_id else DatasetQualityInput(repo_id="")),
            )
            performance_claims_task = self._run_cpu_bound(
                self.performance_claims_metric.calculate, PerformanceInput(readme_text=readme_text)
            )
            size_task = self._run_cpu_bound(self.size_metric.calculate, SizeInput(repo_url=repo_path))

            reproducibility_task = self._run_cpu_bound(self.git_client.estimate_reproducibility, repo_path)
            reviewedness_task = self._run_cpu_bound(
                self.git_client.estimate_reviewedness, repo_path, url
            )
            dataset_code_task = self._run_cpu_bound(
                self.dataset_code_metric.calculate, DatasetCodeInput(repo_url=repo_path)
            )

            (
                (bus_factor_score, bus_lat),
                (code_quality_score, qual_lat),
                (license_score, license_lat),
                (ramp_up_score, ramp_lat),
                (dataset_quality_score, dataset_lat),
                (performance_claims_score, perf_lat),
                (size_score, size_lat),
                (reproducibility_score, reproducibility_lat),
                (reviewedness_score, reviewed_lat),
                (dataset_code_score, dataset_code_lat),
            ) = await asyncio.gather(
                bus_factor_task,
                code_quality_task,
                license_task,
                ramp_up_task,
                dataset_quality_task,
                performance_claims_task,
                size_task,
                reproducibility_task,
                reviewedness_task,
                dataset_code_task,
            )

            results = {
                "bus_factor": bus_factor_score,
                "bus_factor_latency": bus_lat,
                "code_quality": code_quality_score,
                "code_quality_latency": qual_lat,
                "license": license_score,
                "license_latency": license_lat,
                "ramp_up_time": ramp_up_score,
                "ramp_up_time_latency": ramp_lat,
                "dataset_quality": dataset_quality_score,
                "dataset_quality_latency": dataset_lat,
                "size_score": size_score,
                "size_score_latency": size_lat,
                "performance_claims": performance_claims_score,
                "performance_claims_latency": perf_lat,
                "reproducibility": reproducibility_score,
                "reproducibility_latency": reproducibility_lat,
                "reviewedness": reviewedness_score,
                "reviewedness_latency": reviewed_lat,
                "dataset_code_score": dataset_code_score,
                "dataset_code_score_latency": dataset_code_lat,
            }
            logger.info(
                "METRICS: repo_scores url=%s summary=%s",
                url,
                {
                    "bus_factor": round(bus_factor_score, 3),
                    "code_quality": round(code_quality_score, 3),
                    "license": round(license_score, 3),
                    "dataset_quality": round(dataset_quality_score, 3)
                    if isinstance(dataset_quality_score, (int, float))
                    else dataset_quality_score,
                    "dataset_code_score": dataset_code_score,
                    "reviewedness": reviewedness_score,
                    "reproducibility": reproducibility_score,
                },
            )
            return results
        finally:
            self.git_client.cleanup()

    async def analyze_entry(
        self, code_link: str | None, dataset_link: str | None, model_link: str, encountered_datasets: set,
    ) -> dict[str, Any]:
        """
        Analyzes a complete entry with code, dataset, and model links.

        Handles cases where code/dataset links may be empty and determines
        the appropriate analysis strategy based on available information.
        Tracks encountered datasets to support shared dataset inference.

        Args:
            code_link: Optional[str]
            dataset_link: Optional[str]
            model_link: Required URL to ML model (typically Hugging Face)
            encountered_datasets: Set to track previously seen datasets

        Returns:
            Dictionary containing all computed metrics and combined scores
        """
        logger.info(
            "METRICS: analyze_entry code_link=%s dataset_link=%s model_link=%s",
            code_link,
            dataset_link,
            model_link,
        )

        # Determine the primary repository to analyze
        primary_repo_url = None
        if code_link and is_code_repository(code_link):
            primary_repo_url = code_link
            logger.info("METRICS: primary repo from code_link=%s", code_link)
        elif is_code_repository(model_link):
            primary_repo_url = model_link
            logger.info("METRICS: primary repo from model_link=%s", model_link)

        # If no code repository available,
        # try to analyze the model URL as repository
        if not primary_repo_url:
            primary_repo_url = model_link
            logger.info("METRICS: fallback primary repo=%s", model_link)
        else:
            logger.info("METRICS: selected primary repo=%s", primary_repo_url)

        # Handle dataset tracking
        if dataset_link:
            encountered_datasets.add(dataset_link)

        # Analyze the primary repository
        repo_metrics = (
            await self.analyze_repository(primary_repo_url) if primary_repo_url else self._get_default_metrics()
        )

        # Add dataset quality analysis if we have a dataset
        if dataset_link and is_dataset_url(dataset_link):
            dataset_quality_metrics = await self._analyze_dataset_quality(dataset_link)
            repo_metrics.update(dataset_quality_metrics)

        # Calculate dataset and code score
        dataset_code = repo_metrics.get("dataset_code_score")
        if dataset_code is not None:
            dataset_and_code_score = dataset_code
        else:
            dataset_and_code_score = self._calculate_dataset_and_code_score(code_link, dataset_link, repo_metrics)
            logger.info(
                "SCORE_FIX: dataset_code_score missing; using heuristic for code=%s dataset=%s",
                code_link,
                dataset_link,
            )
        repo_metrics["dataset_and_code_score"] = dataset_and_code_score
        repo_metrics["dataset_and_code_score_latency"] = repo_metrics.get("dataset_code_score_latency", 0)

        tree_score = repo_metrics.get("tree_score")
        if tree_score is None:
            repo_metrics["tree_score"] = 0.0
            repo_metrics["tree_score_latency"] = 0
        logger.info(
            "METRICS: combined metrics model=%s net_inputs=%s",
            model_link,
            {
                "dataset_code_score": repo_metrics.get("dataset_code_score"),
                "dataset_quality": repo_metrics.get("dataset_quality"),
                "code_link": code_link,
                "dataset_link": dataset_link,
            },
        )

        return repo_metrics

    async def _analyze_dataset_quality(self, dataset_link: str) -> dict[str, Any]:
        """
        Analyzes dataset quality for the given dataset link.

        Currently supports Hugging Face datasets only.
        For other dataset sources, returns a neutral quality score
        since analysis tools are not available.

        Args:
            dataset_link: URL of the dataset to analyze

        Returns:
            Dictionary with dataset_quality score and latency
        """
        try:
            # Only analyze Hugging Face datasets
            # since that's what the metric supports
            if "huggingface.co/datasets/" in dataset_link:
                repo_id = extract_hf_repo_id(dataset_link)
                dataset_quality_score, dataset_lat = await self._run_cpu_bound(
                    self.dataset_quality_metric.calculate, DatasetQualityInput(repo_id=repo_id)
                )
                return {
                    "dataset_quality": dataset_quality_score,
                    "dataset_quality_latency": dataset_lat,
                }
            else:
                # For non-Hugging Face datasets, we can't
                # calculate quality with current tools
                # Return a neutral score (0.5) to indicate "unknown quality"
                logger.info("Dataset quality not supported for non-HF dataset: " f"{dataset_link}")
                return {
                    "dataset_quality": 0.5,  # Neutral score for unsupported
                    "dataset_quality_latency": 0,
                }
        except ValueError as e:
            logger.error(f"Failed to extract repo_id from dataset URL " f"{dataset_link}: {e}")
        except Exception as e:
            logger.error(f"Failed to analyze dataset quality for " f"{dataset_link}: {e}")

        return {
            "dataset_quality": 0.0,
            "dataset_quality_latency": 0,
        }

    def _calculate_dataset_and_code_score(
        self, code_link: str | None, dataset_link: str | None, repo_metrics: dict[str, Any]
    ) -> float:
        """
        Calculates a combined dataset and code score based on availability.

        According to project plan: Score =
                (0.6 * HasDatasetInfo) + (0.4 * HasTrainingCode)

        Args:
            code_link: Optional code repository URL
            dataset_link: Optional dataset URL
            repo_metrics: Previously computed repository metrics

        Returns:
            Combined score between 0.0 and 1.0
        """
        # Check for dataset information (0 or 1)
        has_dataset_info = 1.0 if dataset_link else 0.0

        # Check for training code (0 or 1)
        has_training_code = 1.0 if (code_link and is_code_repository(code_link)) else 0.0

        # Apply the formula from project plan
        score = (0.6 * has_dataset_info) + (0.4 * has_training_code)
        logger.info(
            "METRICS: heuristic dataset_and_code score=%s dataset_link=%s code_link=%s",
            score,
            dataset_link,
            code_link,
        )
        return score

    def _get_default_metrics(self) -> dict[str, Any]:
        """
        Returns a default metric structure with zero values
        when analysis fails.

        Returns:
            Dictionary with default metric values and latencies
        """
        logger.info("METRICS: default metrics returned (analysis failed)")
        return {
            "bus_factor": 0.0,
            "bus_factor_latency": 0,
            "code_quality": 0.0,
            "code_quality_latency": 0,
            "license": 0.0,
            "license_latency": 0,
            "ramp_up_time": 0.0,
            "ramp_up_time_latency": 0,
            "size_score": {},
            "size_score_latency": 0,
            "performance_claims": 0.0,
            "performance_claims_latency": 0,
            "dataset_quality": 0.0,
            "dataset_quality_latency": 0,
            "reproducibility": 0.0,
            "reproducibility_latency": 0,
            "reviewedness": -1.0,
            "reviewedness_latency": 0,
            "tree_score": 0.0,
            "tree_score_latency": 0,
            "dataset_code_score": None,
            "dataset_code_score_latency": 0,
        }
