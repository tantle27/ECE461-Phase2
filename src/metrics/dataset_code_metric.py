import os
import re
from pathlib import Path
from typing import Any, Optional

from src.api.git_client import GitClient
from src.metric_inputs.dataset_code_input import DatasetCodeInput
from src.metrics.metric import Metric


class DatasetCodeMetric(Metric):
    def __init__(self, git_client: Optional[GitClient] = None):
        self.git_client = git_client or GitClient()

        self.training_script_patterns = [
            r'train\.py$',
            r'finetune\.py$',
            r'training\.py$',
            r'train_.*\.py$',
            r'fine_tune\.py$',
            r'fine-tune\.py$',
            r'model_train\.py$',
            r'train_model\.py$',
            r'run_training\.py$',
            r'train_script\.py$',
            r'experiment\.py$',
            r'experiments/.*\.py$',
            r'scripts/train.*\.py$',
            r'scripts/finetune.*\.py$',
            r'notebooks/.*train.*\.ipynb$',
            r'notebooks/.*finetune.*\.ipynb$'
        ]

        # Enhanced dataset patterns
        self.dataset_patterns = [
            r'dataset[s]?\s*[:=]\s*["\']?([^"\'\s]+)["\']?',
            r'training\s+data[s]?\s*[:=]\s*["\']?([^"\'\s]+)["\']?',
            r'data[s]?\s*[:=]\s*["\']?([^"\'\s]+)["\']?',
            r'https?://[^\s]+dataset[^\s]*',
            r'https?://[^\s]+data[^\s]*',
            r'huggingface\.co/[^\s]+',
            r'kaggle\.com/[^\s]+',
            r'github\.com/[^\s]+data[^\s]*',
            r'zenodo\.org/[^\s]+',
            r'figshare\.com/[^\s]+',
            r'data\.world/[^\s]+',
            r'paperswithcode\.com/datasets/[^\s]+',
            r'mlcommons\.org/[^\s]+',
            r'openml\.org/d/[^\s]+'
        ]

        self.model_indicators = [
            'model', 'pretrained', 'checkpoint', 'weights', 'inference',
            'pipeline', 'api', 'serving', 'deployment'
        ]

        self.dataset_indicators = [
            'dataset', 'data', 'corpus', 'collection', 'benchmark',
            'evaluation', 'testset', 'trainset', 'validation'
        ]

        self.training_indicators = [
            'training', 'train', 'finetune', 'experiment', 'research',
            'baseline', 'reproduce', 'replication'
        ]

    async def calculate(self, metric_input: Any) -> float:
        """
        Calculate dataset and code metric score.

        Objective: To verify that the model's training dataset and source code
        are well-documented and available.

        Methodology: Analyze the model's README.md and configuration files
        (config.json) for references to datasets and the presence
        of training scripts.

        Scoring Formula: (HasDatasetInfo + HasTrainingCode) / 2
        - HasDatasetInfo is 1 if dataset information is found, 0 otherwise
        - HasTrainingCode is 1 if training scripts are found, 0 otherwise
        """
        assert isinstance(metric_input, DatasetCodeInput)

        has_dataset_info = self._check_dataset_info(metric_input.repo_url)

        has_training_code = self._check_training_code(metric_input.repo_url)

        score = (has_dataset_info + has_training_code) / 2.0

        return score

    def _determine_repository_type(self, repo_url: str) -> str:
        try:
            if not os.path.exists(repo_url):
                return 'unknown'

            repo_path = Path(repo_url)
            readme_content = self.git_client.read_readme(repo_url) or ""
            readme_lower = readme_content.lower()

            files = [f.name.lower() for f in
                     repo_path.rglob("*") if f.is_file()]
            dirs = [d.name.lower() for d in repo_path.rglob("*") if d.is_dir()]

            model_score = 0
            dataset_score = 0
            training_score = 0

            for indicator in self.model_indicators:
                if indicator in readme_lower:
                    model_score += 1

            for indicator in self.dataset_indicators:
                if indicator in readme_lower:
                    dataset_score += 1

            for indicator in self.training_indicators:
                if indicator in readme_lower:
                    training_score += 1

            model_files = ['model.py', 'inference.py',
                           'predict.py', 'serve.py', 'api.py']
            dataset_files = ['data.py', 'dataset.py',
                             'load_data.py', 'preprocess.py']
            training_files = ['train.py', 'finetune.py',
                              'experiment.py', 'baseline.py']

            for file in files:
                if any(pattern in file for pattern in model_files):
                    model_score += 1
                if any(pattern in file for pattern in dataset_files):
                    dataset_score += 1
                if any(pattern in file for pattern in training_files):
                    training_score += 1

            for dir_name in dirs:
                if 'model' in dir_name or 'checkpoint' in dir_name:
                    model_score += 1
                if 'data' in dir_name or 'dataset' in dir_name:
                    dataset_score += 1
                if 'train' in dir_name or 'experiment' in dir_name:
                    training_score += 1

            if model_score > dataset_score and model_score > training_score:
                return 'model'
            elif dataset_score > model_score \
                    and dataset_score > training_score:
                return 'dataset'
            elif training_score > model_score \
                    and training_score > dataset_score:
                return 'training'
            else:
                return 'unknown'

        except Exception:
            return 'unknown'

    def _check_dataset_info(self, repo_url: str) -> int:
        readme_content = self.git_client.read_readme(repo_url)
        if readme_content and self._find_dataset_references(readme_content):
            return 1

        config_content = self._read_config_file(repo_url)
        if config_content and self._find_dataset_references(config_content):
            return 1

        if self._find_dataset_files(repo_url):
            return 1

        return 0

    def _check_training_code(self, repo_url: str) -> int:
        try:
            if not os.path.exists(repo_url):
                return 0

            repo_path_obj = Path(repo_url)

            python_files = list(repo_path_obj.rglob("*.py"))
            for file_path in python_files:
                filename = os.path.basename(file_path).lower()
                for pattern in self.training_script_patterns:
                    if re.search(pattern, filename):
                        return 1

                if self._is_training_file_by_content(file_path):
                    return 1

            notebook_files = list(repo_path_obj.rglob("*.ipynb"))
            for file_path in notebook_files:
                filename = os.path.basename(file_path).lower()
                notebook_patterns = [
                    r'train.*\.ipynb$',
                    r'finetune.*\.ipynb$',
                    r'training.*\.ipynb$',
                    r'experiment.*\.ipynb$'
                ]
                for pattern in notebook_patterns:
                    if re.search(pattern, filename):
                        return 1

            return 0
        except Exception:
            return 0

    def _find_dataset_references(self, content: str) -> bool:
        if not content:
            return False

        content_lower = content.lower()

        for pattern in self.dataset_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True

        dataset_keywords = [
            'training data', 'data source', 'data link',
            'download data', 'data url', 'data repository', 'data file',
            'huggingface', 'kaggle', 'zenodo', 'figshare'
        ]

        for keyword in dataset_keywords:
            if keyword in content_lower:
                return True

        dataset_context_patterns = [
            r'dataset[s]?\s*[:=]',
            r'dataset[s]?\s+is\s+',
            r'dataset[s]?\s+available',
            r'dataset[s]?\s+from',
            r'dataset[s]?\s+at',
            r'dataset[s]?\s+can\s+be',
            r'using\s+dataset[s]?',
            r'train[ed]?\s+on\s+dataset[s]?',
            r'dataset[s]?\s+used',
            r'dataset[s]?\s+for\s+training'
        ]

        for pattern in dataset_context_patterns:
            if re.search(pattern, content_lower):
                return True

        return False

    def _find_dataset_files(self, repo_url: str) -> bool:
        try:
            if not os.path.exists(repo_url):
                return False

            repo_path = Path(repo_url)

            dataset_file_patterns = [
                'data.csv', 'data.json', 'data.jsonl', 'data.tsv', 'data.txt',
                'dataset.csv', 'dataset.json', 'dataset.jsonl',
                'train.csv', 'train.json', 'train.jsonl',
                'test.csv', 'test.json', 'test.jsonl',
                'validation.csv', 'validation.json', 'validation.jsonl',
                'dev.csv', 'dev.json', 'dev.jsonl'
            ]

            for pattern in dataset_file_patterns:
                if list(repo_path.rglob(pattern)):
                    return True

            # Check for data directories
            data_dirs = ['data', 'datasets',
                         'dataset', 'raw_data', 'processed_data',
                         'data_files', 'data_dir', 'data_directory',
                         'data_folder', 'data_path', 'data_location']
            for dir_name in data_dirs:
                if (repo_path / dir_name).exists():
                    return True

            return False
        except Exception:
            return False

    def _is_training_file_by_content(self, file_path: Path) -> bool:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()

            training_keywords = [
                'model.fit', 'model.train', 'trainer.train', 'train_epoch',
                'optimizer.step', 'loss.backward', 'training_loop',
                'fit(', 'train(', 'training', 'epoch', 'batch_size',
                'learning_rate', 'optimizer', 'criterion', 'loss_function',
                'train_dataloader', 'train_dataset', 'train_loader'
            ]

            for keyword in training_keywords:
                if keyword in content:
                    return True

            training_imports = [
                'from torch.optim', 'from torch.utils.data',
                'from transformers import Trainer',
                'from sklearn.model_selection',
                'import tensorflow as tf',
                'from tensorflow.keras'
            ]

            for import_pattern in training_imports:
                if import_pattern in content:
                    return True

            return False
        except Exception:
            return False

    def _read_config_file(self, repo_url: str) -> Optional[str]:
        try:
            config_path = os.path.join(repo_url, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return f.read()

            config_files = ['config.yaml',
                            'config.yml',
                            'configuration.json',
                            'settings.json']
            for config_file in config_files:
                config_path = os.path.join(repo_url, config_file)
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        return f.read()

            return None
        except Exception:
            return None
