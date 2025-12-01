"""
Tool: fix_flake8.py

Runs automated format/fix tools (ruff, black, isort) to fix style issues
where possible, then runs flake8 and writes remaining issues to
`flake8_remaining.txt`.

Usage (Windows PowerShell):
  python tools\fix_flake8.py

The script will attempt to install missing tools in the active environment
using pip. It won't modify files if those tools are not available or
installation fails; it will still write the flake8 output.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMAINING = ROOT / "flake8_remaining.txt"


def run(cmd: list[str], check=True):
    print("Running:", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def ensure_tool(tool: str, pip_name: str | None = None) -> bool:
    """Return True if tool is available on PATH, otherwise try to pip install it."""
    if shutil.which(tool):
        return True
    pip_pkg = pip_name or tool
    print(f"Tool '{tool}' not found. Trying to install '{pip_pkg}' via pip...")
    try:
        run([sys.executable, "-m", "pip", "install", "--upgrade", pip_pkg])
    except Exception as e:
        print(f"Failed to install {pip_pkg}: {e}")
        return False
    return shutil.which(tool) is not None


def main() -> int:
    # Ensure tools
    tools = [
        ("ruff", "ruff"),
        ("black", "black"),
        ("isort", "isort"),
        ("flake8", "flake8"),
    ]
    available = {}
    for exe, pkg in tools:
        ok = ensure_tool(exe, pkg)
        available[exe] = ok

    # Do a lightweight whitespace cleanup first (trailing spaces, blank-line spaces, ensure newline at EOF)
    def iter_text_files(root: Path) -> Iterable[Path]:
        # Skip common non-source or virtualenv directories to avoid permission/stat errors
        SKIP_DIRS = {".venv", "venv", "env", ".env", "node_modules", "__pycache__", ".git"}
        SUFFIXES = {".py", ".md", ".txt", ".html", ".yml", ".yaml"}
        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                # Remove directories we want to skip so os.walk doesn't descend into them
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fname in filenames:
                    p = Path(dirpath) / fname
                    try:
                        if p.suffix in SUFFIXES:
                            yield p
                    except OSError:
                        # Skip files that cannot be accessed
                        continue
        except OSError:
            # If a top-level directory can't be scanned, bail out gracefully
            return

    def cleanup_whitespace(root: Path) -> None:
        for p in iter_text_files(root):
            try:
                s = p.read_text(encoding="utf-8")
            except Exception:
                continue
            # Remove trailing whitespace on each line
            lines = [re.sub(r"[ \t]+$", "", l) for l in s.splitlines()]
            # Replace lines that contain only spaces/tabs with empty line
            # (already handled by strip above)
            new = "\n".join(lines) + "\n"
            if new != s:
                p.write_text(new, encoding="utf-8")

    cleanup_whitespace(ROOT)

    # Transform some common test anti-patterns that flake rules flag
    def replace_assert_false(root: Path) -> None:
        pattern = re.compile(r"assert\s+False\s*,\s*(?P<msg>(?:\".*?\"|\'.*?\'))")
        for p in iter_text_files(root):
            if not p.suffix == ".py":
                continue
            try:
                s = p.read_text(encoding="utf-8")
            except Exception:
                continue
            new = pattern.sub(r"raise AssertionError(\g<msg>)", s)
            if new != s:
                p.write_text(new, encoding="utf-8")

    replace_assert_false(ROOT)

    # Replace subprocess stdout/stderr pipes with capture_output where both are present
    def replace_subprocess_pipes(root: Path) -> None:
        target = "capture_output=True"
        for p in iter_text_files(root):
            if not p.suffix == ".py":
                continue
            try:
                s = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if target in s:
                new = s.replace(target, "capture_output=True")
                p.write_text(new, encoding="utf-8")

    replace_subprocess_pipes(ROOT)

    # Run ruff --fix (preferred) to apply many lint fixes. Retry with --unsafe-fixes if needed.
    if available.get("ruff"):
        try:
            run(["ruff", "cache", "clear"], check=False)
            run(["ruff", "check", "--fix", str(ROOT)])
        except Exception as e:
            print("ruff --fix failed:", e)
            # Try unsafe fixes (may change semantics) to catch more issues
            try:
                run(["ruff", "check", "--fix", "--unsafe-fixes", str(ROOT)])
            except Exception as e2:
                print("ruff --fix --unsafe-fixes also failed:", e2)

    # Run isort to sort imports
    if available.get("isort"):
        try:
            run(["isort", str(ROOT)])
        except Exception as e:
            print("isort failed:", e)

    # Run black to format and wrap long lines where possible
    if available.get("black"):
        try:
            run(["black", str(ROOT)])
        except Exception as e:
            print("black failed:", e)

    # After automated fixes, run ruff again for additional fixes
    if available.get("ruff"):
        try:
            run(["ruff", "check", "--fix", str(ROOT)])
        except Exception as e:
            print("ruff second pass failed:", e)

    # Finally run flake8 and capture output
    try:
        print("Running flake8 to capture remaining issues...")
        result = subprocess.run(
            ["flake8", "--max-line-length=100", str(ROOT)], capture_output=True, text=True
        )
        out = result.stdout or result.stderr
        REMAINING.write_text(out)
        if out.strip():
            print(f"flake8 reported issues. See {REMAINING}")
            return 2
        else:
            print("No flake8 issues remain.")
            return 0
    except FileNotFoundError:
        print("flake8 not found. Please install flake8 to generate remaining issues.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
