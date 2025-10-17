import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.metrics.dataset_code_metric import DatasetCodeInput, DatasetCodeMetric


class TestDatasetCodeMetric:
    def setup_method(self):
        self.metric = DatasetCodeMetric()

    @pytest.mark.asyncio
    async def test_calculate_both_dataset_and_training_code(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Training

        ## Dataset
        This model was trained on the IMDB dataset available at:
        https://huggingface.co/datasets/imdb

        ## Training
        Run the training script with: python train.py
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "train.py").touch()
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "utils.py").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_only_dataset_info(self):
        mock_git_client = Mock()

        mock_git_client.read_readme.return_value = """
        # Model Documentation

        ## Data Source
        The training data comes from the Kaggle competition:
        https://www.kaggle.com/competitions/sentiment-analysis

        ## Usage
        This model can be used for sentiment analysis.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "inference.py").touch()
            (Path(temp_dir) / "utils.py").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.5

    @pytest.mark.asyncio
    async def test_calculate_only_training_code(self):
        mock_git_client = Mock()

        mock_git_client.read_readme.return_value = """
        # Model Implementation

        This is a machine learning model for classification.

        ## Installation
        pip install -r requirements.txt
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files with training script
            (Path(temp_dir) / "finetune.py").touch()
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "data_loader.py").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.5

    @pytest.mark.asyncio
    async def test_calculate_neither_dataset_nor_training_code(self):
        mock_git_client = Mock()

        mock_git_client.read_readme.return_value = """
        # Model Documentation

        This is a pre-trained model for text classification.

        ## Usage
        ```python
        from transformers import pipeline
        classifier = pipeline("text-classification")
        ```
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "inference.py").touch()
            (Path(temp_dir) / "requirements.txt").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_with_config_file_dataset_info(self):
        mock_git_client = Mock()

        mock_git_client.read_readme.return_value = """
        # Model Documentation

        This is a machine learning model.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "inference.py").touch()

            config_content = """
            {
                "model_name": "bert-base-uncased",
                "dataset": "https://huggingface.co/datasets/glue",
                "training_data": "https://www.kaggle.com/datasets/sentiment140"
            }
            """

            metric = DatasetCodeMetric(mock_git_client)

            with patch.object(metric,
                              '_read_config_file',
                              return_value=config_content
                              ):
                result = await metric.calculate(
                    DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.5

    @pytest.mark.asyncio
    async def test_calculate_various_training_script_patterns(self):
        """Test detection of various training script naming patterns."""
        mock_git_client = Mock()

        mock_git_client.read_readme.return_value = """
        # Model Documentation

        This is a machine learning model.
        """

        test_cases = [
            ('train.py', 1.0),
            ('finetune.py', 1.0),
            ('training.py', 1.0),
            ('train_model.py', 1.0),
            ('fine_tune.py', 1.0),
            ('run_training.py', 1.0),
            ('model.py', 0.0),
            ('inference.py', 0.0)
        ]

        for filename, expected_score in test_cases:
            with tempfile.TemporaryDirectory() as temp_dir:
                (Path(temp_dir) / filename).touch()

                metric = DatasetCodeMetric(mock_git_client)
                result = await metric.calculate(
                    DatasetCodeInput(repo_url=temp_dir))

                expected = 0.5 if expected_score == 1.0 else 0.0
                assert result == expected, f"Failed for filename: {filename}"

    @pytest.mark.asyncio
    async def test_calculate_various_dataset_patterns(self):
        mock_git_client = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "model.py").touch()

            test_cases = [
                ("Dataset: https://huggingface.co/datasets/imdb", 0.5),
                ("Training data: kaggle.com/competitions/sentiment", 0.5),
                ("Data source: zenodo.org/record/12345", 0.5),
                ("Download from: figshare.com/articles/dataset", 0.5),
                ("No dataset information here", 0.0),
                ("This is just regular text", 0.0)
            ]

            for readme_content, expected_score in test_cases:
                mock_git_client.read_readme.return_value = readme_content

                metric = DatasetCodeMetric(mock_git_client)
                result = await metric.calculate(
                    DatasetCodeInput(repo_url=temp_dir))

                assert result == expected_score, \
                    f"Failed for content: {readme_content}"

    @pytest.mark.asyncio
    async def test_calculate_empty_readme_and_no_files(self):
        mock_git_client = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_git_client.read_readme.return_value = ""

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_readme_none(self):
        mock_git_client = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_git_client.read_readme.return_value = None

            (Path(temp_dir) / "model.py").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.0

    @pytest.mark.asyncio
    async def test_determine_repository_type_model(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Pre-trained Model

        This is a pre-trained BERT model for text classification.
        The model weights are available for download.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create model-related files
            (Path(temp_dir) / "model.py").touch()
            (Path(temp_dir) / "inference.py").touch()
            (Path(temp_dir) / "checkpoints").mkdir()

            metric = DatasetCodeMetric(mock_git_client)
            repo_type = metric._determine_repository_type(temp_dir)

            assert repo_type == 'model'

    @pytest.mark.asyncio
    async def test_determine_repository_type_dataset(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Dataset Collection

        This repository contains the IMDB movie review dataset.
        The data is available in CSV format.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dataset-related files
            (Path(temp_dir) / "data.csv").touch()
            (Path(temp_dir) / "dataset.py").touch()
            (Path(temp_dir) / "data").mkdir()

            metric = DatasetCodeMetric(mock_git_client)
            repo_type = metric._determine_repository_type(temp_dir)

            assert repo_type == 'dataset'

    @pytest.mark.asyncio
    async def test_determine_repository_type_training(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Training Code

        This repository contains training scripts for fine-tuning BERT.
        Run the experiments with the provided scripts.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "train.py").touch()
            (Path(temp_dir) / "experiment.py").touch()
            (Path(temp_dir) / "experiments").mkdir()

            metric = DatasetCodeMetric(mock_git_client)
            repo_type = metric._determine_repository_type(temp_dir)

            assert repo_type == 'training'

    @pytest.mark.asyncio
    async def test_find_dataset_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dataset files
            (Path(temp_dir) / "data.csv").touch()
            (Path(temp_dir) / "train.json").touch()
            (Path(temp_dir) / "data").mkdir()

            metric = DatasetCodeMetric()
            has_dataset_files = metric._find_dataset_files(temp_dir)

            assert has_dataset_files is True

    @pytest.mark.asyncio
    async def test_is_training_file_by_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a file with training content
            training_file = Path(temp_dir) / "custom_training.py"
            training_file.write_text("""
            import torch
            from torch.optim import Adam

            def train_model():
                model = MyModel()
                optimizer = Adam(model.parameters())
                for epoch in range(10):
                    model.train()
                    for batch in train_dataloader:
                        optimizer.zero_grad()
                        loss = model(batch)
                        loss.backward()
                        optimizer.step()
            """)

            metric = DatasetCodeMetric()
            is_training = metric._is_training_file_by_content(training_file)

            assert is_training is True

    @pytest.mark.asyncio
    async def test_calculate_with_jupyter_notebooks(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Model Training Notebooks

        This repository contains Jupyter notebooks for training models.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "train_model.ipynb").touch()
            (Path(temp_dir) / "finetune_bert.ipynb").touch()
            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.5

    @pytest.mark.asyncio
    async def test_calculate_with_enhanced_dataset_patterns(self):
        mock_git_client = Mock()

        test_cases = [
            ("Dataset: https://data.world/sentiment-analysis", 0.5),
            ("Training data: https://paperswithcode.com/datasets/imdb", 0.5),
            ("Download from: https://mlcommons.org/datasets/", 0.5),
            ("OpenML dataset: https://openml.org/d/12345", 0.5),
            ("No dataset information", 0.0)
        ]

        for readme_content, expected_score in test_cases:
            mock_git_client.read_readme.return_value = readme_content

            with tempfile.TemporaryDirectory() as temp_dir:
                (Path(temp_dir) / "model.py").touch()

                metric = DatasetCodeMetric(mock_git_client)
                result = await metric.calculate(
                    DatasetCodeInput(repo_url=temp_dir))

                assert result == expected_score, \
                    f"Failed for content: {readme_content}"

    @pytest.mark.asyncio
    async def test_calculate_with_data_directories(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
        # Model Documentation

        This is a machine learning model.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "data").mkdir()
            (Path(temp_dir) / "model.py").touch()

            metric = DatasetCodeMetric(mock_git_client)
            result = await metric.calculate(
                DatasetCodeInput(repo_url=temp_dir))

            assert result == 0.5
