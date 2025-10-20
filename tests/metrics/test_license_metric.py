from unittest.mock import Mock, patch

import pytest

from src.metrics.license_metric import LicenseInput, LicenseMetric


class TestLicenseMetric:
    def setup_method(self):
        self.metric = LicenseMetric()

    @pytest.mark.asyncio
    async def test_calculate_permissive_license_mit(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

Some description here.

## License

This project is licensed under the MIT License.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_permissive_license_apache(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

Licensed under the Apache License, Version 2.0.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_lgpl_license(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

This project is licensed under the GNU Lesser General Public License v2.1.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.5

    @pytest.mark.asyncio
    async def test_calculate_copyleft_license_gpl(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

This project is licensed under the GNU General Public License v3.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.1

    @pytest.mark.asyncio
    async def test_calculate_copyleft_license_agpl(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

This project is licensed under the GNU Affero General Public License v3.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.1

    @pytest.mark.asyncio
    async def test_calculate_no_license_section(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

Some description here.

## Installation

Run `pip install package`.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_no_readme(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = None

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_unknown_license(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

This project uses a custom proprietary license.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_license_with_british_spelling(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## Licence

This project is licensed under the MIT License.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_license_with_licensing_heading(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## Licensing

This project is licensed under the BSD License.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_license_case_insensitive(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## license

This project is licensed under the MIT license.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_license_multiple_headings(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

This project is licensed under the MIT License.

## Installation

Run `pip install package`.

## Contributing

Please read our contributing guidelines.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 1.0

    @pytest.mark.asyncio
    async def test_calculate_license_empty_section(self):
        mock_git_client = Mock()
        mock_git_client.read_readme.return_value = """
# Project Title

## License

## Installation

Run `pip install package`.
        """.strip()

        metric = LicenseMetric(mock_git_client)
        result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_invalid_type(self):
        with pytest.raises(AssertionError):
            await self.metric.calculate("invalid_input")

    @pytest.mark.asyncio
    async def test_calculate_with_git_client_integration(self):
        with patch("src.metrics.license_metric.GitClient") as mock_git_client_class:
            mock_git_client = Mock()
            mock_git_client.read_readme.return_value = """
# Project Title

## License

This project is licensed under the MIT License.
            """.strip()
            mock_git_client_class.return_value = mock_git_client

            metric = LicenseMetric()
            result = await metric.calculate(LicenseInput(repo_url="/test/repo"))

            assert result == 1.0

    def test_extract_license_from_readme(self):
        readme_content = """
# Project Title

Some description.

## License

This project is licensed under the MIT License.

## Installation

Run `pip install package`.
        """.strip()

        result = self.metric._extract_license_from_readme(readme_content)
        assert "This project is licensed under the MIT License." in result

    def test_score_license_permissive(self):
        assert self.metric._score_license("MIT License") == 1.0
        assert self.metric._score_license("Apache 2.0") == 1.0
        assert self.metric._score_license("BSD License") == 1.0

    def test_score_license_lgpl(self):
        assert self.metric._score_license("LGPL v2.1") == 0.5
        assert self.metric._score_license("GNU Lesser General Public License") == 0.5

    def test_score_license_copyleft(self):
        assert self.metric._score_license("GPL v3") == 0.1
        assert self.metric._score_license("AGPL v3") == 0.1

    def test_score_license_unknown(self):
        assert self.metric._score_license("Custom License") == 0.0
        assert self.metric._score_license("Proprietary") == 0.0
