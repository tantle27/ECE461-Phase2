from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from src.adapters.github_fetchers import fetch_commits, fetch_readme, fetch_repo_tree

InputKey = str


@dataclass(frozen=True)
class InputSpec:
    key: InputKey
    fetch: Callable[[str, str | None], Any]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    inputs: Iterable[InputSpec]
    compute: Callable[[dict[InputKey, Any], str, str | None], dict[str, Any]]


TREE = InputSpec("tree", fetch_repo_tree)
COMMITS = InputSpec("commits", fetch_commits)
README = InputSpec("readme", fetch_readme)


def _m_size(data: dict[InputKey, Any], repo: str, ref: str | None):
    entries = data.get("tree") or []
    total_bytes = sum(int(e.get("size", 0)) for e in entries)
    if total_bytes <= 1_000_000:
        score = 1.0
    elif total_bytes >= 50_000_000:
        score = 0.0
    else:
        score = max(0.0, 1.0 - (total_bytes - 1_000_000) / 49_000_000)
    return {"score": round(score, 3), "details": {"bytes": total_bytes}}


def _m_busfactor(data: dict[InputKey, Any], repo: str, ref: str | None):
    commits = data.get("commits") or []
    authors = []
    for c in commits:
        a = c.get("author_email") or c.get("author_login")
        if a:
            authors.append(a)
    total = max(len(commits), 1)
    freq: dict[str, int] = {}
    for a in authors:
        freq[a] = freq.get(a, 0) + 1
    top_share = (max(freq.values()) / total) if freq else 1.0
    score = 1.0 - top_share
    return {
        "score": round(score, 3),
        "details": {"authors": len(freq), "top_share": round(top_share, 3)},
    }


def _m_rampup(data: dict[InputKey, Any], repo: str, ref: str | None):
    rd = data.get("readme")
    readme_len = int((rd or {}).get("size", 0))
    has_text = bool((rd or {}).get("text"))
    score = min(1.0, (readme_len / 4000) * 0.7 + (0.3 if has_text else 0.0))
    return {"score": round(score, 3), "details": {"readme_bytes": readme_len, "has_text": has_text}}


METRICS: list[MetricSpec] = [
    MetricSpec("size", inputs=[TREE], compute=_m_size),
    MetricSpec("bus_factor", inputs=[COMMITS], compute=_m_busfactor),
    MetricSpec("ramp_up", inputs=[README], compute=_m_rampup),
]


def evaluate_all(repo: str, ref: str | None = None, metrics: list[MetricSpec] = METRICS) -> dict:
    t0 = time.time()

    needed: dict[InputKey, InputSpec] = {}
    for m in metrics:
        for i in m.inputs:
            needed[i.key] = i

    inputs_data: dict[InputKey, Any] = {}
    for key, spec in needed.items():
        try:
            inputs_data[key] = spec.fetch(repo, ref)
        except Exception:
            inputs_data[key] = None

    results = []
    for m in metrics:
        try:
            out = m.compute(inputs_data, repo, ref)
            results.append({"name": m.name, **out})
        except Exception as e:
            results.append({"name": m.name, "score": 0.0, "details": {"error": str(e)}})

    return {
        "repo": repo,
        "ref": ref,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "metrics": results,
    }
