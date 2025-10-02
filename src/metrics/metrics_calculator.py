import asyncio
import logging
import re
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from src.api.gen_ai_client import GenAIClient
from src.api.git_client import GitClient
from src.api.hugging_face_client import HuggingFaceClient
from src.metric_inputs.bus_factor_input import BusFactorInput
from src.metric_inputs.code_quality_input import CodeQualityInput
from src.metric_inputs.dataset_quality_input import DatasetQualityInput
from src.metric_inputs.license_input import LicenseInput
from src.metric_inputs.performance_input import PerformanceInput
from src.metric_inputs.ramp_up_time_input import RampUpTimeInput
from src.metric_inputs.size_input import SizeInput
from src.metrics.bus_factor_metric import BusFactorMetric
from src.metrics.code_quality_metric import CodeQualityMetric
from src.metrics.dataset_quality_metric import DatasetQualityMetric
from src.metrics.license_metric import LicenseMetric
from src.metrics.performance_claims_metric import PerformanceClaimsMetric
from src.metrics.ramp_up_time_metric import RampUpTimeMetric
from src.metrics.size_metric import SizeMetric


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
    url = url.rstrip('/')

    # Pattern for datasets: huggingface.co/datasets/{org}/{name} or
    # huggingface.co/datasets/{name}
    dataset_match = re.search(
        r"huggingface\.co/datasets/([^/?#]+(?:/[^/?#]+)?)", url
    )
    if dataset_match:
        return dataset_match.group(1)

    # Pattern for regular models: huggingface.co/{org}/{name} or
    # huggingface.co/{name}.
    # But exclude spaces: huggingface.co/spaces/{org}/{name}
    model_match = re.search(
        r"huggingface\.co/(?!spaces/)([^/?#]+(?:/[^/?#]+)?)", url
    )
    if model_match:
        return model_match.group(1)

    raise ValueError(f"Invalid Hugging Face URL: {url}")


def is_code_repository(url: str) -> bool:
    """
    Determines if a URL is a code repository
    (GitHub, GitLab, or Hugging Face Spaces).
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    return (
        'github.com' in parsed.netloc or
        'gitlab.com' in parsed.netloc or
        ('huggingface.co' in parsed.netloc and '/spaces/' in parsed.path)
    )


def is_dataset_url(url: str) -> bool:
    """
    Determines if a URL is a dataset URL.
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    return (
        ('huggingface.co' in parsed.netloc and '/datasets/' in parsed.path) or
        'image-net.org' in parsed.netloc or
        'kaggle.com' in parsed.netloc or
        'archive.ics.uci.edu' in parsed.netloc or  # UCI ML Repository
        # Add other dataset source patterns as needed
        '/datasets/' in parsed.path
    )


def is_model_url(url: str) -> bool:
    """
    Determines if a URL is a Hugging Face model URL.
    """
    if not url:
        return False
    parsed = urlparse(url.lower())
    return (
        'huggingface.co' in parsed.netloc and
        '/datasets/' not in parsed.path and
        '/spaces/' not in parsed.path
    )


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

    def __init__(
        self,
        process_pool: ProcessPoolExecutor,
        github_token: Optional[str] = None
    ):
        """
        Initialize the metrics calculator with necessary API clients and
        metric instances.

        Args:
            process_pool: ProcessPoolExecutor for CPU-bound operations
            github_token: Optional GitHub token for API access
        """
        self.git_client = GitClient(github_token)
        self.gen_ai_client = GenAIClient()
        self.hf_client = HuggingFaceClient()
        self.process_pool = process_pool
        self.thread_pool = ThreadPoolExecutor(max_workers=10)

        # Initialize metric instances
        self.bus_factor_metric = BusFactorMetric(self.git_client)
        self.code_quality_metric = CodeQualityMetric(self.git_client)
        self.license_metric = LicenseMetric(self.git_client)
        self.size_metric = SizeMetric(self.git_client)
        self.ramp_up_time_metric = RampUpTimeMetric(
            self.git_client, self.gen_ai_client
        )
        self.dataset_quality_metric = DatasetQualityMetric(self.hf_client)
        self.performance_claims_metric = PerformanceClaimsMetric(
            self.gen_ai_client
        )

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

    async def analyze_repository(self, url: str) -> Dict[str, Any]:
        """
        Clones and analyzes a single repository,
        running all metric calculations
        in parallel for optimal performance.

        Args:
            url: Repository URL to analyze

        Returns:
            Dictionary containing all computed metrics and their latencies
        """
        logging.info(f"Starting async analysis for: {url}")
        loop = asyncio.get_running_loop()

        repo_path = await loop.run_in_executor(
            self.thread_pool, self.git_client.clone_repository, url
        )

        if not repo_path:
            logging.error(f"Failed to clone repository: {url}")
            return self._get_default_metrics()

        try:
            # Extract repo_id if this is a Hugging Face dataset URL
            repo_id = None
            if "huggingface.co/datasets/" in url:
                try:
                    repo_id = extract_hf_repo_id(url)
                except ValueError as e:
                    logging.error(str(e))
            bus_factor_task = self._run_cpu_bound(
                self.bus_factor_metric.calculate,
                BusFactorInput(repo_url=repo_path))
            code_quality_task = self._run_cpu_bound(
                self.code_quality_metric.calculate,
                CodeQualityInput(repo_url=repo_path))
            license_task = self._run_cpu_bound(
                self.license_metric.calculate,
                LicenseInput(repo_url=repo_path))
            readme_text = self.git_client.read_readme(repo_path) or ""
            ramp_up_task = self._run_cpu_bound(
                self.ramp_up_time_metric.calculate,
                RampUpTimeInput(
                    repo_path=repo_path,
                    readme_text=readme_text))
            dataset_quality_task = self._run_cpu_bound(
                self.dataset_quality_metric.calculate,
                DatasetQualityInput(repo_id=repo_id)
                if repo_id else DatasetQualityInput(repo_id="")
            )
            performance_claims_task = self._run_cpu_bound(
                self.performance_claims_metric.calculate,
                PerformanceInput(
                    readme_text=readme_text)
            )
            size_task = self._run_cpu_bound(
                self.size_metric.calculate,
                SizeInput(repo_url=repo_path))

            (bus_factor_score, bus_lat), \
                (code_quality_score, qual_lat), \
                (license_score, license_lat), \
                (ramp_up_score, ramp_lat), \
                (dataset_quality_score, dataset_lat), \
                (performance_claims_score, perf_lat), \
                (size_score, size_lat) = \
                await asyncio.gather(bus_factor_task,
                                     code_quality_task,
                                     license_task,
                                     ramp_up_task,
                                     dataset_quality_task,
                                     performance_claims_task,
                                     size_task)

            return {
                'bus_factor': bus_factor_score,
                'bus_factor_latency': bus_lat,
                'code_quality': code_quality_score,
                'code_quality_latency': qual_lat,
                'license': license_score,
                'license_latency': license_lat,
                'ramp_up_time': ramp_up_score,
                'ramp_up_time_latency': ramp_lat,
                'dataset_quality': dataset_quality_score,
                'dataset_quality_latency': dataset_lat,
                'size_score': size_score,
                'size_score_latency': size_lat,
                'performance_claims': performance_claims_score,
                'performance_claims_latency': perf_lat,
            }
        finally:
            self.git_client.cleanup()

    async def analyze_entry(
        self,
        code_link: Optional[str],
        dataset_link: Optional[str],
        model_link: str,
        encountered_datasets: set
    ) -> Dict[str, Any]:
        """
        Analyzes a complete entry with code, dataset, and model links.

        Handles cases where code/dataset links may be empty and determines
        the appropriate analysis strategy based on available information.
        Tracks encountered datasets to support shared dataset inference.

        Args:
            code_link: Optional URL to code repository
            dataset_link: Optional URL to dataset (HF datasets, ImageNet, etc.)
            model_link: Required URL to ML model (typically Hugging Face)
            encountered_datasets: Set to track previously seen datasets

        Returns:
            Dictionary containing all computed metrics and combined scores
        """
        logging.info(
            "Analyzing entry - Code: %s, Dataset: %s, Model: %s",
            code_link, dataset_link, model_link
        )

        # Determine the primary repository to analyze
        primary_repo_url = None
        if code_link and is_code_repository(code_link):
            primary_repo_url = code_link
        elif is_code_repository(model_link):
            primary_repo_url = model_link

        # If no code repository available,
        # try to analyze the model URL as repository
        if not primary_repo_url:
            primary_repo_url = model_link

        # Handle dataset tracking
        if dataset_link:
            encountered_datasets.add(dataset_link)

        # Analyze the primary repository
        repo_metrics = (await self.analyze_repository(primary_repo_url)
                        if primary_repo_url else self._get_default_metrics())

        # Add dataset quality analysis if we have a dataset
        if dataset_link and is_dataset_url(dataset_link):
            dataset_quality_metrics = await self._analyze_dataset_quality(
                dataset_link
            )
            repo_metrics.update(dataset_quality_metrics)

        # Calculate dataset and code score
        dataset_and_code_score = self._calculate_dataset_and_code_score(
            code_link, dataset_link, repo_metrics
        )
        repo_metrics['dataset_and_code_score'] = dataset_and_code_score
        repo_metrics['dataset_and_code_score_latency'] = 0  # Placeholder

        return repo_metrics

    async def _analyze_dataset_quality(
        self, dataset_link: str
    ) -> Dict[str, Any]:
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
                    self.dataset_quality_metric.calculate,
                    DatasetQualityInput(repo_id=repo_id)
                )
                return {
                    'dataset_quality': dataset_quality_score,
                    'dataset_quality_latency': dataset_lat,
                }
            else:
                # For non-Hugging Face datasets, we can't
                # calculate quality with current tools
                # Return a neutral score (0.5) to indicate "unknown quality"
                logging.info(
                    "Dataset quality not supported for non-HF dataset: "
                    f"{dataset_link}"
                )
                return {
                    'dataset_quality': 0.5,  # Neutral score for unsupported
                    'dataset_quality_latency': 0,
                }
        except ValueError as e:
            logging.error(
                f"Failed to extract repo_id from dataset URL "
                f"{dataset_link}: {e}"
            )
        except Exception as e:
            logging.error(
                f"Failed to analyze dataset quality for "
                f"{dataset_link}: {e}"
                )

        return {
            'dataset_quality': 0.0,
            'dataset_quality_latency': 0,
        }

    def _calculate_dataset_and_code_score(
        self,
        code_link: Optional[str],
        dataset_link: Optional[str],
        repo_metrics: Dict[str, Any]
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
        has_training_code = \
            1.0 if (code_link and is_code_repository(code_link)) else 0.0

        # Apply the formula from project plan
        return (0.6 * has_dataset_info) + (0.4 * has_training_code)

    def _get_default_metrics(self) -> Dict[str, Any]:
        """
        Returns a default metric structure with zero values
        when analysis fails.

        Returns:
            Dictionary with default metric values and latencies
        """
        return {
            'bus_factor': 0.0, 'bus_factor_latency': 0,
            'code_quality': 0.0, 'code_quality_latency': 0,
            'license': 0.0, 'license_latency': 0,
            'ramp_up_time': 0.0, 'ramp_up_time_latency': 0,
            'size_score': {}, 'size_score_latency': 0,
            'performance_claims': 0.0, 'performance_claims_latency': 0,
            'dataset_quality': 0.0, 'dataset_quality_latency': 0,
        }
