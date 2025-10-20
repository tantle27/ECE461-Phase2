from unittest.mock import Mock, patch

import pytest

from src.metrics.size_metric import SizeInput, SizeMetric


class TestSizeMetric:
    def setup_method(self):
        self.metric = SizeMetric()

    @pytest.mark.asyncio
    async def test_calculate_raspberry_pi_compatible(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 1.0,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 1.0, "jetson_nano": 1.0, "desktop_pc": 1.0, "aws_server": 1.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_jetson_nano_compatible(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 0.0,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 0.0, "jetson_nano": 1.0, "desktop_pc": 1.0, "aws_server": 1.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_desktop_pc_compatible(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 0.0,
            "jetson_nano": 0.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 0.0, "jetson_nano": 0.0, "desktop_pc": 1.0, "aws_server": 1.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_aws_server_only(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 0.0,
            "jetson_nano": 0.0,
            "desktop_pc": 0.0,
            "aws_server": 1.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 0.0, "jetson_nano": 0.0, "desktop_pc": 0.0, "aws_server": 1.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_all_incompatible(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 0.0,
            "jetson_nano": 0.0,
            "desktop_pc": 0.0,
            "aws_server": 0.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 0.0, "jetson_nano": 0.0, "desktop_pc": 0.0, "aws_server": 0.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_mixed_compatibility(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {
            "raspberry_pi": 0.0,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0,
        }

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 0.0, "jetson_nano": 1.0, "desktop_pc": 1.0, "aws_server": 1.0}
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        with pytest.raises(AssertionError):
            await self.metric.calculate(123)

    @pytest.mark.asyncio
    async def test_calculate_with_git_client_integration(self):
        with patch("src.metrics.size_metric.GitClient") as mock_git_client_class:
            mock_git_client = Mock()
            mock_git_client.get_repository_size.return_value = {
                "raspberry_pi": 1.0,
                "jetson_nano": 1.0,
                "desktop_pc": 1.0,
                "aws_server": 1.0,
            }
            mock_git_client_class.return_value = mock_git_client

            metric = SizeMetric()
            result = await metric.calculate(SizeInput(repo_url="/test/repo"))

            expected = {
                "raspberry_pi": 1.0,
                "jetson_nano": 1.0,
                "desktop_pc": 1.0,
                "aws_server": 1.0,
            }
            assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_empty_dict(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {}

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        assert result == {}

    @pytest.mark.asyncio
    async def test_calculate_partial_dict(self):
        mock_git_client = Mock()
        mock_git_client.get_repository_size.return_value = {"raspberry_pi": 1.0, "desktop_pc": 0.0}

        metric = SizeMetric(mock_git_client)
        result = await metric.calculate(SizeInput(repo_url="/test/repo"))

        expected = {"raspberry_pi": 1.0, "desktop_pc": 0.0}
        assert result == expected
