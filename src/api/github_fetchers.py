from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import requests

from src.core.config import settings

_GH = "https://api.github.com"


def _headers() -> Dict[str, str]:
    h = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    for attempt in range(settings.http_retries):
        r = requests.get(url, headers=_headers(), params=params, timeout=settings.request_timeout_s)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("github: retries exhausted")


def fetch_repo_tree(repo: str, ref: str | None) -> List[Dict[str, Any]]:
    """
    Returns [{"path": str, "size": int}, ...]
    Uses the Git Trees API to get a full (recursive) listing with sizes.
    """
    owner, name = repo.split("/", 1)
    # Resolve ref to SHA first
    if ref:
        commit = _get(f"{_GH}/repos/{owner}/{name}/commits/{ref}")
        sha = commit["sha"]
    else:
        branch = _get(f"{_GH}/repos/{owner}/{name}/branches/main")
        sha = branch["commit"]["sha"]

    tree = _get(f"{_GH}/repos/{owner}/{name}/git/trees/{sha}", params={"recursive": "1"})
    out = []
    for e in tree.get("tree", []):
        if e.get("type") == "blob":
            out.append({"path": e.get("path"), "size": int(e.get("size", 0))})
    return out


def fetch_commits(repo: str, ref: str | None, window_days: int = 180) -> List[Dict[str, Any]]:
    """
    Returns commits as [{"author_email":..., "author_login":..., "date":...}, ...]
    """
    owner, name = repo.split("/", 1)
    params: Dict[str, Any] = {"per_page": 100}
    if ref:
        params["sha"] = ref
    # Keep it simple: one page
    commits = _get(f"{_GH}/repos/{owner}/{name}/commits", params=params)
    out = []
    for c in commits:
        commit = c.get("commit", {})
        author = commit.get("author") or {}
        out.append(
            {
                "author_email": author.get("email"),
                "author_login": (c.get("author") or {}).get("login"),
                "date": author.get("date"),
            }
        )
    return out


def fetch_readme(repo: str, ref: str | None) -> Dict[str, Any] | None:
    """
    Returns {"path": "README.md", "size": int, "text": str} or None
    """
    owner, name = repo.split("/", 1)
    params: Dict[str, Any] = {}
    if ref:
        params["ref"] = ref
    try:
        md = _get(f"{_GH}/repos/{owner}/{name}/readme", params=params)
    except Exception:
        return None

    # content is base64, but for scoring we only need size; text is optional
    import base64

    content_b64 = md.get("content", "")
    text = ""
    try:
        text = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    return {"path": md.get("path", "README.md"), "size": len(text.encode("utf-8")), "text": text}
