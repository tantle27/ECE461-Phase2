import logging
import re
from typing import Any, Optional

from src.api.git_client import GitClient
from src.metric_inputs.license_input import LicenseInput
from src.metrics.metric import Metric


class LicenseMetric(Metric):
    def __init__(self, git_client: Optional[GitClient] = None):
        self.git_client = git_client or GitClient()
        self.permissive_licenses = {
            'mit', 'apache 2.0', 'apache-2.0', 'apache2', 'apache license',
            'apache license, version 2.0', 'bsd', 'bsd-2-clause',
            'bsd-3-clause', 'bsd-4-clause', 'isc', 'unlicense', 'cc0', 'zlib',
            'boost', 'mpl', 'mozilla public license', 'eclipse public license'
        }

        self.lgpl_licenses = {
            'lgpl', 'lgpl-2.1', 'lgplv2.1', 'lesser general public license',
            'gnu lesser general public license'
        }

        self.copyleft_licenses = {
            'gpl', 'gpl-2', 'gpl-3', 'gplv2', 'gplv3', 'agpl', 'agpl-3',
            'gnu general public license', 'gnu affero general public license'
        }

    async def calculate(self, metric_input: Any) -> float:
        assert isinstance(metric_input, LicenseInput)

        readme_content = self.git_client.read_readme(metric_input.repo_url)
        if not readme_content:
            logging.warning(
                f"License: No README found for {metric_input.repo_url}"
                )
            return 0.0

        license_text = self._extract_license_from_readme(readme_content)
        if not license_text:
            logging.warning(
                f"License: No license text found \
                    in README for {metric_input.repo_url}"
                )
            return 0.0

        score = self._score_license(license_text)
        logging.info(f"License score: {score} for {metric_input.repo_url}")
        return score

    def _extract_license_from_readme(
            self, readme_content: str) -> Optional[str]:
        # First try to find a dedicated license section
        license_patterns = [
            r'^#+\s*license\s*$',  # # License, ## License, etc.
            r'^#+\s*licence\s*$',  # # Licence (British spelling)
            r'^#+\s*licensing\s*$',  # # Licensing
        ]

        lines = readme_content.split('\n')
        license_section_start = None

        for i, line in enumerate(lines):
            for pattern in license_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    license_section_start = i
                    break
            if license_section_start is not None:
                break

        if license_section_start is not None:
            license_lines: list[str] = []
            for i in range(license_section_start + 1, len(lines)):
                line = lines[i].strip()

                # Stop at next heading (starts with #)
                if line.startswith('#'):
                    break

                # Skip empty lines at the beginning
                if not license_lines and not line:
                    continue

                license_lines.append(line)

            result = ' '.join(license_lines).strip()
            if result:
                return result

        # If no dedicated license section, search for specific license mentions
        license_mentions = []
        for line in lines:
            line_lower = line.lower()
            # Look for specific license patterns that indicate actual licenses
            # Avoid generic mentions of "license" that don't specify a type
            if any(license in line_lower for license in [
                'mit license', 'apache 2.0', 'apache license',
                'gpl', 'gpl-2', 'gpl-3',
                'bsd license', 'bsd-2', 'bsd-3',
                'lgpl', 'mpl', 'eclipse'
            ]):
                license_mentions.append(line.strip())

        if license_mentions:
            return ' '.join(license_mentions[:3])  # Take first 3 mentions

        return None

    def _score_license(self, license_text: str) -> float:
        license_lower = license_text.lower()

        # Check for permissive licenses (1.0 score)
        for license_name in self.permissive_licenses:
            if license_name in license_lower:
                return 1.0

        # Check for LGPLv2.1 itself (0.5 score)
        for license_name in self.lgpl_licenses:
            if license_name in license_lower:
                return 0.5

        # Check for strong copyleft licenses (0.1 score)
        for license_name in self.copyleft_licenses:
            if license_name in license_lower:
                return 0.1

        return 0.0
