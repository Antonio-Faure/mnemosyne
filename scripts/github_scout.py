"""Scout GitHub for small, specialized agent systems with visible design traces.

The purpose: feed the architect-taste corpus with real decision stories —
small repos (like mnemosyne) whose README/docs/issues/commit messages show
WHY a design was chosen and what was rejected. Discovery is an API problem
(no browser): this script finds and ranks candidates; the deep reading is
delegated to the bi-agent.

Usage (host, authenticated gh):
    python scripts/github_scout.py --out data/architect-corpus/candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

#: searches that surface small, opinionated agent systems
QUERIES = (
    "topic:llm-agent stars:5..500 pushed:>2026-01-01",
    '"agent" "orchestration" stars:3..300 pushed:>2026-01-01',
    '"agent" "mailbox" OR "task queue" stars:3..300 pushed:>2026-01-01',
    '"agent supervisor" OR "turn-taking" stars:3..300 pushed:>2026-01-01',
    "topic:autonomous-agents stars:5..500 pushed:>2026-01-01",
)


def gh_api(path: str) -> dict | list:
    """Authenticated GitHub API call through the gh CLI (auth + rate limits)."""
    res = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, timeout=60
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh api {path}: {res.stderr.strip()[:200]}")
    return json.loads(res.stdout)


def search_repositories(query: str, per_page: int = 30) -> list[dict]:
    """Search via the URL (form fields make gh post, which this endpoint rejects)."""
    from urllib.parse import quote_plus

    page = gh_api(f"search/repositories?q={quote_plus(query)}&per_page={per_page}")
    return page.get("items", [])


def design_files(repo_full: str) -> list[str]:
    """README/docs/*.md that smell like design deliberation (why, not what)."""
    try:
        tree = gh_api(f"repos/{repo_full}/git/trees/HEAD?recursive=1")
    except Exception:  # noqa: BLE001 - a repo without a tree is not a candidate
        return []
    interesting = []
    for entry in tree.get("tree", []):
        path = entry.get("path", "")
        if not path.endswith(".md") or entry.get("type") != "blob":
            continue
        low = path.lower()
        if any(
            marker in low
            for marker in (
                "vision", "architecture", "design", "adr", "rfc",
                "decision", "why", "philosophy", "principles", "roadmap",
            )
        ):
            interesting.append(path)
    return interesting[:12]


def candidate_signal(repo: dict, docs: list[str]) -> int:
    """Cheap ranking: small + alive + design docs + issues that argue."""
    score = 0
    stars = repo.get("stargazers_count") or 0
    if 5 <= stars <= 500:
        score += 2  # the small-specialized zone
    if docs:
        score += min(4, len(docs))
    if repo.get("open_issues_count"):
        score += 1
    if repo.get("description") and any(
        w in repo["description"].lower()
        for w in ("agent", "orchestr", "autonom", "multi-agent", "bi-agent")
    ):
        score += 2
    return score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/architect-corpus/candidates.jsonl")
    parser.add_argument("--limit", type=int, default=40, help="max candidates out")
    args = parser.parse_args()

    seen: dict[str, dict] = {}
    for query in QUERIES:
        try:
            repos = search_repositories(query)
        except Exception as exc:  # noqa: BLE001 - one bad query must not stop the scout
            print(f"query failed: {query} ({exc})", file=sys.stderr)
            continue
        for repo in repos:
            seen[repo["full_name"]] = repo

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scored = []
    for full_name, repo in seen.items():
        docs = design_files(full_name)
        scored.append((candidate_signal(repo, docs), full_name, repo, docs))
    scored.sort(reverse=True, key=lambda row: row[0])

    with open(out_path, "w", encoding="utf-8") as handle:
        for score, full_name, repo, docs in scored[: args.limit]:
            handle.write(
                json.dumps(
                    {
                        "repo": full_name,
                        "score": score,
                        "stars": repo.get("stargazers_count"),
                        "description": repo.get("description"),
                        "pushed_at": repo.get("pushed_at"),
                        "url": repo.get("html_url"),
                        "design_docs": docs,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"{len(scored[: args.limit])} candidats (sur {len(scored)}) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
