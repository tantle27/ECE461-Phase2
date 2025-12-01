"""Simple ADA Test Runner"""

import os
import subprocess
import sys


def run_simple_ada_tests(url="http://localhost:5000"):
    """Run simplified ADA tests."""

    # Set environment variable for test URL
    env = os.environ.copy()
    env["ADA_TEST_URL"] = url

    print(f"Running ADA tests against: {url}")

    # Run simplified tests
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/ada/test_simple_keyboard.py",
        "tests/ada/test_simple_contrast.py",
        "tests/ada/test_simple_accessibility.py",
        "-v",
        "--tb=short",
    ]

    result = subprocess.run(cmd, env=env)
    return result.returncode == 0


def run_keyboard_tests(url="http://localhost:5000"):
    """Run only keyboard navigation tests."""
    env = os.environ.copy()
    env["ADA_TEST_URL"] = url

    cmd = [sys.executable, "-m", "pytest", "tests/ada/test_simple_keyboard.py", "-v"]
    result = subprocess.run(cmd, env=env)
    return result.returncode == 0


def run_contrast_tests(url="http://localhost:5000"):
    """Run only color contrast tests."""
    env = os.environ.copy()
    env["ADA_TEST_URL"] = url

    cmd = [sys.executable, "-m", "pytest", "tests/ada/test_simple_contrast.py", "-v"]
    result = subprocess.run(cmd, env=env)
    return result.returncode == 0


def run_accessibility_tests(url="http://localhost:5000"):
    """Run only general accessibility tests."""
    env = os.environ.copy()
    env["ADA_TEST_URL"] = url

    cmd = [sys.executable, "-m", "pytest", "tests/ada/test_simple_accessibility.py", "-v"]
    result = subprocess.run(cmd, env=env)
    return result.returncode == 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run simplified ADA tests")
    parser.add_argument("--url", default="http://localhost:5000", help="URL to test")
    parser.add_argument(
        "--type", choices=["all", "keyboard", "contrast", "accessibility"], default="all", help="Type of tests to run",
    )

    args = parser.parse_args()

    if args.type == "keyboard":
        success = run_keyboard_tests(args.url)
    elif args.type == "contrast":
        success = run_contrast_tests(args.url)
    elif args.type == "accessibility":
        success = run_accessibility_tests(args.url)
    else:
        success = run_simple_ada_tests(args.url)

    sys.exit(0 if success else 1)
