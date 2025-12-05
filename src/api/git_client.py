import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse


@dataclass
class CommitStats:
    total_commits: int
    contributors: dict[str, int]
    bus_factor: float


@dataclass
class CodeQualityStats:
    has_tests: bool
    lint_errors: int
    code_quality_score: float


class GitClient:
    def __init__(self, GH_TOKEN: str | None = None):
        self.temp_dirs: list[str] = []
        token = GH_TOKEN or os.environ.get("GH_TOKEN") or None
        self.GH_TOKEN = token.strip() if token else None
        self.git_bin = os.environ.get("GIT_PYTHON_GIT_EXECUTABLE") or shutil.which("git") or "/usr/bin/git"

    # ---------- URL helpers ----------

    def _normalize_git_url(self, url: str) -> str:
        patterns = [
            r"/tree/[^/]+/?$",
            r"/blob/[^/]+/.*$",
            r"/commits?/[^/]+/?$",
            r"/releases?/?.*$",
            r"/issues?/?.*$",
            r"/pull/?.*$",
            r"/wiki/?.*$",
        ]
        normalized = url.rstrip("/")
        for p in patterns:
            normalized = re.sub(p, "", normalized)
        return normalized

    def _inject_token(self, url: str) -> str:
        if not self.GH_TOKEN:
            return url
        if url.startswith("git@github.com:"):
            path = url.split(":", 1)[1]
            url = f"https://github.com/{path}"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return url
        if parsed.username:
            return url
        tok = quote(self.GH_TOKEN, safe="")
        netloc = f"{tok}:x-oauth-basic@{parsed.netloc}"
        return urlunparse(parsed._replace(netloc=netloc))

    # ---------- clone strategies ----------

    def _clone_with_gitpython(self, clone_url: str, dst: str) -> bool:
        try:
            from git import Repo  # type: ignore

            Repo.clone_from(
                clone_url, dst, depth=1, single_branch=True, env={"GIT_TERMINAL_PROMPT": "0"},
            )
            return True
        except Exception as e:
            logging.warning("GitPython clone failed: %s", e)
            return False

    def _clone_with_cli(self, clone_url: str, dst: str) -> bool:
        try:
            cmd = [
                self.git_bin,
                "clone",
                "--depth=1",
                "--single-branch",
                "--no-tags",
                clone_url,
                dst,
            ]
            env = os.environ.copy()
            env.setdefault("GIT_TERMINAL_PROMPT", "0")
            subprocess.run(cmd, check=True, capture_output=True, env=env, timeout=25)
            return True
        except subprocess.CalledProcessError as e:
            msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            if "Authentication failed" in msg or "fatal: Invalid" in msg:
                logging.error("Authentication failed for %s", clone_url)
            else:
                logging.error("git clone failed: %s", msg.strip())
            return False
        except subprocess.TimeoutExpired:
            logging.error("git clone timed out")
            return False
        except Exception as e:
            logging.error("git clone error: %s", e)
            return False

    def clone_repository(self, url: str) -> str | None:
        normalized = self._normalize_git_url(url)
        clone_url = self._inject_token(normalized)
        tmp = tempfile.mkdtemp(prefix="model_analysis_", dir="/tmp")
        self.temp_dirs.append(tmp)

        # Try GitPython first, then fall back to git CLI
        ok = self._clone_with_gitpython(clone_url, tmp)
        if not ok:
            ok = self._clone_with_cli(clone_url, tmp)

        if not ok:
            return None
        return tmp

    # ---------- analyses ----------

    def analyze_commits(self, repo_path: str) -> CommitStats:
        try:
            from git import Repo  # type: ignore
        except Exception as e:
            logging.error("GitPython not available: %s", e)
            return CommitStats(total_commits=0, contributors={}, bus_factor=0.0)

        try:
            if not os.path.exists(repo_path):
                logging.warning("analyze_commits: repo_path does not exist: %s", repo_path)
                return CommitStats(total_commits=0, contributors={}, bus_factor=0.0)
            
            repo = Repo(repo_path)
            
            # Try to fetch more commits if this is a shallow clone
            try:
                is_shallow = repo.git.rev_parse("--is-shallow-repository") == "true"
                if is_shallow:
                    logging.info("analyze_commits: shallow repo detected, attempting to fetch more commits")
                    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                    repo.git.fetch("--depth=100", f"--shallow-since={since}")
            except Exception as e:
                logging.debug("analyze_commits: fetch failed (non-critical): %s", e)

            # First try: commits from last 365 days
            since_date = datetime.now() - timedelta(days=365)
            commits = list(repo.iter_commits(since=since_date, max_count=100))
            
            # If no commits found, try without date filter (shallow repos may not have date info)
            if len(commits) == 0:
                logging.info("analyze_commits: no commits with date filter, trying without filter")
                commits = list(repo.iter_commits(max_count=100))
            
            logging.info("analyze_commits: found %d commits in %s", len(commits), repo_path)

            contribs: dict[str, int] = {}
            for c in commits:
                author = getattr(c.author, "email", None) or getattr(c.author, "name", None)
                if author:
                    contribs[author] = contribs.get(author, 0) + 1

            total = len(commits)
            if total == 0:
                logging.warning("analyze_commits: no commits found after all attempts")
                return CommitStats(0, {}, 0.0)

            concentration = sum((n / total) ** 2 for n in contribs.values())
            bus = max(0.0, min(1.0, 1.0 - concentration))
            logging.info("analyze_commits: %d commits, %d contributors, bus_factor=%.3f", total, len(contribs), bus)
            return CommitStats(total, dict(sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)), bus)
        except Exception as e:
            logging.error("commit analysis failed for %s: %s", repo_path, e)
            return CommitStats(0, {}, 0.0)

    def analyze_code_quality(self, repo_path: str) -> CodeQualityStats:
        try:
            if not os.path.exists(repo_path):
                return CodeQualityStats(False, 0, 0.0)

            p = Path(repo_path)
            test_patterns = ["test", "tests", "spec", "specs"]
            has_tests = any(any(p.rglob(f"{pat}*")) for pat in test_patterns)

            lint_errors = 0
            try:
                py_files = list(p.rglob("*.py"))
                if py_files:
                    mains = [f for f in py_files if "/test" not in str(f) and "/tests/" not in str(f)]
                    files = (mains[:30] + py_files[:20])[:50]
                    if files:
                        res = subprocess.run(
                            ["flake8", "--count", "--quiet", *map(str, files)],
                            capture_output=True,
                            text=True,
                            cwd=repo_path,
                            timeout=5,
                        )
                        if res.stderr:
                            try:
                                lint_errors = int(res.stderr.strip().split("\n")[-1])
                            except Exception:
                                lint_errors = 0
            except subprocess.TimeoutExpired:
                lint_errors = 0
            except Exception:
                lint_errors = 0

            score = max(0.0, 1.0 - (lint_errors * 0.05))
            return CodeQualityStats(has_tests, lint_errors, score)
        except Exception as e:
            logging.error("code quality analysis failed: %s", e)
            return CodeQualityStats(False, 0, 0.0)

    def analyze_ramp_up_time(self, repo_path: str) -> dict[str, bool]:
        try:
            if not os.path.exists(repo_path):
                return {"has_examples": False, "has_dependencies": False}
            p = Path(repo_path)
            has_examples = any(any(p.rglob(f"{pat}*")) for pat in ["examples", "notebooks", "demo.py", "example.py"])
            has_deps = any((p / f).exists() for f in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"])
            return {"has_examples": has_examples, "has_dependencies": has_deps}
        except Exception as e:
            logging.error("ramp-up analysis failed: %s", e)
            return {"has_examples": False, "has_dependencies": False}

    def get_repository_size(self, repo_path: str) -> dict[str, float]:
        try:
            if not os.path.exists(repo_path):
                return {
                    "raspberry_pi": 0.0,
                    "jetson_nano": 0.0,
                    "desktop_pc": 0.0,
                    "aws_server": 0.0,
                }
            p = Path(repo_path)
            total = 0
            for fp in p.rglob("*"):
                if any(part == ".git" for part in fp.parts):
                    continue
                if fp.is_file():
                    total += fp.stat().st_size
            size_gb = total / (1024 ** 3)
            return {
                "raspberry_pi": 1.0 if size_gb < 1.0 else 0.0,
                "jetson_nano": 1.0 if size_gb < 4.0 else 0.0,
                "desktop_pc": 1.0 if size_gb < 16.0 else 0.0,
                "aws_server": 1.0,
            }
        except Exception as e:
            logging.error("size calc failed: %s", e)
            return {"raspberry_pi": 0.0, "jetson_nano": 0.0, "desktop_pc": 0.0, "aws_server": 0.0}

    def read_readme(self, repo_path: str) -> str | None:
        try:
            if not os.path.exists(repo_path):
                return None
            p = Path(repo_path)
            files = list(p.glob("README*"))
            if not files:
                return None
            with open(files[0], encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.warning("readme read failed: %s", e)
            return None

    def cleanup(self):
        for d in self.temp_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception as e:
                logging.warning("cleanup failed for %s: %s", d, e)
        self.temp_dirs.clear()

    def has_github_repository(self, repo_url: str | None = None) -> bool:
        if not repo_url:
            return False
        return "github.com" in repo_url.lower()

    def analyze_pull_requests(self, repo_path: str) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "total_code_lines": 0,
            "reviewed_code_lines": 0,
            "pull_requests": [],
        }
        try:
            from git import Repo  # type: ignore

            repo = Repo(repo_path)
            commits = list(repo.iter_commits(max_count=200))
            for commit in commits:
                total_lines = 0
                try:
                    total_lines = int(commit.stats.total.get("lines", 0))
                except Exception:
                    total_lines = 0
                stats["total_code_lines"] += total_lines
                message_lower = (commit.message or "").lower()
                is_merge = len(commit.parents or []) > 1
                reviewed = is_merge or "reviewed-by" in message_lower or "merge pull request" in message_lower
                if reviewed:
                    stats["reviewed_code_lines"] += total_lines
                stats["pull_requests"].append(
                    {
                        "id": commit.hexsha,
                        "reviewed": reviewed,
                        "lines_added": total_lines,
                    }
                )
        except Exception as exc:
            logging.error("pull request analysis failed: %s", exc)
        return stats

    def estimate_reviewedness(self, repo_path: str, repo_url: str | None = None) -> float:
        if repo_url and not self.has_github_repository(repo_url):
            return -1.0
        analysis = self.analyze_pull_requests(repo_path)
        total_lines = analysis.get("total_code_lines", 0)
        pull_requests = analysis.get("pull_requests", []) or []
        if total_lines <= 0 or not pull_requests:
            return -1.0
        reviewed_lines = analysis.get("reviewed_code_lines", 0)
        return max(0.0, min(1.0, reviewed_lines / total_lines))

    def estimate_reproducibility(self, repo_path: str) -> float:
        try:
            if not os.path.exists(repo_path):
                return 0.0
            readme = (self.read_readme(repo_path) or "").lower()
            install_indicators = [
                "pip install",
                "conda install",
                "requirements.txt",
                "pip3 install",
                "docker pull",
            ]
            run_indicators = [
                "python ",
                "python3 ",
                "hf",
                "transformers",
                "usage",
                "quickstart",
            ]
            has_install = any(token in readme for token in install_indicators)
            has_run = any(token in readme for token in run_indicators)
            repo_path_obj = Path(repo_path)
            has_examples = any((repo_path_obj / name).exists() for name in ("examples", "notebooks"))
            has_requirements = any((repo_path_obj / file).exists() for file in ("requirements.txt", "environment.yml"))

            if (has_install or has_requirements) and (has_run or has_examples):
                return 1.0
            if has_install or has_run or has_examples or has_requirements:
                return 0.5
            return 0.0
        except Exception as exc:
            logging.error("reproducibility analysis failed: %s", exc)
            return 0.0
