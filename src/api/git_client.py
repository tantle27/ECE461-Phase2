import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
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
                clone_url,
                dst,
                depth=1,
                single_branch=True,
                env={"GIT_TERMINAL_PROMPT": "0"},
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
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=25)
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
        except Exception:
            return CommitStats(total_commits=0, contributors={}, bus_factor=0.0)

        try:
            repo = Repo(repo_path)
            try:
                if repo.git.rev_parse("--is-shallow-repository") == "true":
                    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                    repo.git.fetch("--depth=100", f"--shallow-since={since}")
            except Exception:
                pass

            since_date = datetime.now() - timedelta(days=365)
            commits = list(repo.iter_commits(since=since_date, max_count=100))

            contribs: dict[str, int] = {}
            for c in commits:
                author = getattr(c.author, "email", None) or getattr(c.author, "name", None)
                if author:
                    contribs[author] = contribs.get(author, 0) + 1

            total = len(commits)
            if total == 0:
                return CommitStats(0, {}, 0.0)

            concentration = sum((n / total) ** 2 for n in contribs.values())
            bus = max(0.0, min(1.0, 1.0 - concentration))
            return CommitStats(total, dict(sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)), bus)
        except Exception as e:
            logging.error("commit analysis failed: %s", e)
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
                return {"raspberry_pi": 0.0, "jetson_nano": 0.0, "desktop_pc": 0.0, "aws_server": 0.0}
            p = Path(repo_path)
            total = 0
            for fp in p.rglob("*"):
                if any(part == ".git" for part in fp.parts):
                    continue
                if fp.is_file():
                    total += fp.stat().st_size
            size_gb = total / (1024**3)
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