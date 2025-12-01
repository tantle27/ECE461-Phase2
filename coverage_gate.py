#!/usr/bin/env python3
"""
Coverage Gate Enforcement for CI Pipeline

This script enforces minimum code coverage requirements and integrates
with RESTler security testing for comprehensive quality gates.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CoverageGate:
    """Enforces code coverage requirements and quality gates."""

    def __init__(self, min_coverage: float = 60.0):
        self.min_coverage = min_coverage
        self.coverage_file = "coverage.xml"
        self.json_file = "coverage.json"

    def run_tests_with_coverage(self) -> bool:
        """Run pytest with coverage measurement."""
        logger.info("Running tests with coverage measurement...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--cov=src",
            "--cov=app",
            "--cov-report=xml",
            "--cov-report=json",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "-v",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            logger.info("Test output:")
            print(result.stdout)

            if result.stderr:
                logger.warning("Test stderr:")
                print(result.stderr)

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.error("Tests timed out")
            return False
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            return False

    def parse_coverage_xml(self) -> dict:
        """Parse coverage.xml to extract coverage metrics."""
        if not os.path.exists(self.coverage_file):
            logger.error(f"Coverage file not found: {self.coverage_file}")
            return {}

        try:
            tree = ET.parse(self.coverage_file)
            root = tree.getroot()

            # Extract overall coverage
            coverage_elem = root.find(".")
            if coverage_elem is not None:
                line_rate = float(coverage_elem.get("line-rate", 0)) * 100
                branch_rate = float(coverage_elem.get("branch-rate", 0)) * 100

                return {
                    "line_coverage": line_rate,
                    "branch_coverage": branch_rate,
                    "overall_coverage": line_rate,  # Use line coverage as overall
                    "packages": self._parse_packages(root),
                }
            else:
                logger.error("Could not find coverage data in XML")
                return {}

        except Exception as e:
            logger.error(f"Error parsing coverage XML: {e}")
            return {}

    def parse_coverage_json(self) -> dict:
        """Parse coverage.json for additional metrics."""
        if not os.path.exists(self.json_file):
            logger.warning(f"JSON coverage file not found: {self.json_file}")
            return {}

        try:
            with open(self.json_file) as f:
                data = json.load(f)

            totals = data.get("totals", {})
            return {
                "lines_covered": totals.get("covered_lines", 0),
                "lines_total": totals.get("num_statements", 0),
                "branches_covered": totals.get("covered_branches", 0),
                "branches_total": totals.get("num_branches", 0),
                "coverage_percent": totals.get("percent_covered", 0.0),
                "files": data.get("files", {}),
            }

        except Exception as e:
            logger.error(f"Error parsing coverage JSON: {e}")
            return {}

    def _parse_packages(self, root) -> dict:
        """Parse package-level coverage from XML."""
        packages = {}

        for package in root.findall(".//package"):
            package_name = package.get("name", "unknown")
            line_rate = float(package.get("line-rate", 0)) * 100
            branch_rate = float(package.get("branch-rate", 0)) * 100

            classes = []
            for class_elem in package.findall(".//class"):
                class_name = class_elem.get("name", "unknown")
                class_line_rate = float(class_elem.get("line-rate", 0)) * 100
                classes.append({"name": class_name, "coverage": class_line_rate})

            packages[package_name] = {
                "line_coverage": line_rate,
                "branch_coverage": branch_rate,
                "classes": classes,
            }

        return packages

    def check_coverage_gate(self, coverage_data: dict) -> bool:
        """Check if coverage meets minimum requirements."""
        current_coverage = coverage_data.get("overall_coverage", 0.0)

        logger.info(f"Current coverage: {current_coverage:.2f}%")
        logger.info(f"Minimum required: {self.min_coverage:.2f}%")

        if current_coverage >= self.min_coverage:
            logger.info("✅ Coverage gate PASSED")
            return True
        else:
            logger.error(f"❌ Coverage gate FAILED - {current_coverage:.2f}% < {self.min_coverage:.2f}%")
            return False

    def generate_coverage_report(self, coverage_data: dict, json_data: dict) -> str:
        """Generate detailed coverage report."""
        report_path = "coverage_gate_report.html"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Coverage Gate Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        .pass {{ color: #27ae60; background: #d5f4e6; padding: 10px; border-radius: 5px; }}
        .fail {{ color: #e74c3c; background: #ffeaea; padding: 10px; border-radius: 5px; }}
        .summary {{ background: #ecf0f1; padding: 20px; margin: 20px 0; border-radius: 5px; }}
        .metric {{ display: inline-block; margin: 10px 20px; }}
        .metric-value {{ font-size: 2em; font-weight: bold; }}
        .metric-label {{ font-size: 0.9em; color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
        .low-coverage {{ background-color: #ffebee; }}
        .good-coverage {{ background-color: #e8f5e8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Code Coverage Gate Report</h1>
        <p>Generated: {coverage_data.get('timestamp', 'Unknown')}</p>
    </div>

    <div class="summary">
        <h2>Coverage Summary</h2>
        <div class="metric">
            <div class="metric-value">{coverage_data.get('overall_coverage', 0):.1f}%</div>
            <div class="metric-label">Overall Coverage</div>
        </div>
        <div class="metric">
            <div class="metric-value">{coverage_data.get('line_coverage', 0):.1f}%</div>
            <div class="metric-label">Line Coverage</div>
        </div>
        <div class="metric">
            <div class="metric-value">{coverage_data.get('branch_coverage', 0):.1f}%</div>
            <div class="metric-label">Branch Coverage</div>
        </div>
        <div class="metric">
            <div class="metric-value">{json_data.get('lines_covered', 0)}</div>
            <div class="metric-label">Lines Covered</div>
        </div>
    </div>

    <div class="{'pass' if coverage_data.get('overall_coverage', 0) >= self.min_coverage else 'fail'}">
        <h2>Gate Status: {'PASSED' if coverage_data.get('overall_coverage', 0) >= self.min_coverage else 'FAILED'}</h2>
        <p>Minimum required coverage: {self.min_coverage}%</p>
        <p>Current coverage: {coverage_data.get('overall_coverage', 0):.2f}%</p>
    </div>

    <h2>Package Coverage Details</h2>
    <table>
        <thead>
            <tr>
                <th>Package</th>
                <th>Line Coverage</th>
                <th>Branch Coverage</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
"""

        packages = coverage_data.get("packages", {})
        for package_name, package_data in packages.items():
            line_cov = package_data.get("line_coverage", 0)
            branch_cov = package_data.get("branch_coverage", 0)
            status_class = "good-coverage" if line_cov >= self.min_coverage else "low-coverage"

            html_content += f"""
            <tr class="{status_class}">
                <td>{package_name}</td>
                <td>{line_cov:.1f}%</td>
                <td>{branch_cov:.1f}%</td>
                <td>{'✅ Good' if line_cov >= self.min_coverage else '⚠️ Below threshold'}</td>
            </tr>
"""

        html_content += """
        </tbody>
    </table>

    <h2>Files with Low Coverage</h2>
    <table>
        <thead>
            <tr>
                <th>File</th>
                <th>Coverage</th>
                <th>Lines Missing</th>
            </tr>
        </thead>
        <tbody>
"""

        files = json_data.get("files", {})
        low_coverage_files = [
            (f, data)
            for f, data in files.items()
            if data.get("summary", {}).get("percent_covered", 100) < self.min_coverage
        ]

        for file_path, file_data in sorted(
            low_coverage_files, key=lambda x: x[1].get("summary", {}).get("percent_covered", 0)
        ):
            summary = file_data.get("summary", {})
            coverage_pct = summary.get("percent_covered", 0)
            missing_lines = file_data.get("missing_lines", [])

            html_content += f"""
            <tr class="low-coverage">
                <td>{file_path}</td>
                <td>{coverage_pct:.1f}%</td>
                <td>{len(missing_lines)} lines</td>
            </tr>
"""

        html_content += """
        </tbody>
    </table>

    <h2>Recommendations</h2>
    <ul>
"""

        if coverage_data.get("overall_coverage", 0) < self.min_coverage:
            html_content += f"<li>Increase test coverage to meet the {self.min_coverage}% minimum requirement</li>"

        if low_coverage_files:
            html_content += f"<li>Focus on {len(low_coverage_files)} files with low coverage</li>"

        if coverage_data.get("branch_coverage", 0) < coverage_data.get("line_coverage", 0):
            html_content += "<li>Improve branch coverage by testing edge cases and error conditions</li>"

        html_content += """
    </ul>

    <footer style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #7f8c8d;">
        <p>Coverage reports available in: htmlcov/index.html</p>
    </footer>
</body>
</html>
"""

        with open(report_path, "w") as f:
            f.write(html_content)

        logger.info(f"Coverage report generated: {report_path}")
        return report_path

    def run_security_tests(self) -> bool:
        """Run RESTler security tests if available."""
        restler_script = Path("run_restler_tests.py")
        if not restler_script.exists():
            logger.warning("RESTler script not found, skipping security tests")
            return True

        logger.info("Running RESTler security tests...")

        try:
            result = subprocess.run(
                [sys.executable, str(restler_script), "--ci", "--suite", "smoke"],
                capture_output=True,
                text=True,
                timeout=1800,
            )

            if result.stdout:
                logger.info("RESTler output:")
                print(result.stdout)

            if result.stderr:
                logger.warning("RESTler stderr:")
                print(result.stderr)

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.warning("RESTler tests timed out")
            return False
        except Exception as e:
            logger.warning(f"Error running RESTler tests: {e}")
            return False


def main():
    """Main entry point for coverage gate enforcement."""
    parser = argparse.ArgumentParser(description="Enforce coverage gate for CI")
    parser.add_argument("--min-coverage", type=float, default=60.0, help="Minimum coverage percentage required")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests (use existing coverage data)")
    parser.add_argument("--skip-security", action="store_true", help="Skip security tests")
    parser.add_argument("--ci", action="store_true", help="Run in CI mode (fail on coverage below threshold)")

    args = parser.parse_args()

    gate = CoverageGate(args.min_coverage)

    try:
        # Run tests with coverage if not skipping
        if not args.skip_tests:
            logger.info("Running test suite with coverage measurement...")
            if not gate.run_tests_with_coverage():
                logger.error("Tests failed - coverage gate cannot proceed")
                return 1

        # Parse coverage data
        coverage_data = gate.parse_coverage_xml()
        json_data = gate.parse_coverage_json()

        if not coverage_data:
            logger.error("No coverage data available")
            return 1

        # Generate coverage report
        report_path = gate.generate_coverage_report(coverage_data, json_data)

        # Check coverage gate
        coverage_passed = gate.check_coverage_gate(coverage_data)

        # Run security tests if not skipping
        security_passed = True
        if not args.skip_security:
            security_passed = gate.run_security_tests()

        # Final result
        if args.ci:
            if not coverage_passed:
                logger.error("Coverage gate failed in CI mode")
                return 1
            if not security_passed:
                logger.error("Security tests failed in CI mode")
                return 1

        logger.info(f"Coverage gate completed. Report: {report_path}")
        logger.info(f"Coverage: {'PASS' if coverage_passed else 'FAIL'}")
        logger.info(f"Security: {'PASS' if security_passed else 'FAIL'}")

        return 0 if (coverage_passed and security_passed) else 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
