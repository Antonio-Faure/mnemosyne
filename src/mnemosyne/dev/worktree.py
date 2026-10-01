"""Throwaway git worktree for the dev agent (never switch the main checkout)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def add_worktree(repo: str | Path, path: str | Path, base_branch: str) -> Path:
    repo = Path(repo)
    path = Path(path)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin", base_branch],
        capture_output=True,
        text=True,
    )
    res = subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(path), f"origin/{base_branch}"],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {res.stderr.strip()[:200]}")
    return path


def remove_worktree(repo: str | Path, path: str | Path) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
        capture_output=True,
        text=True,
    )
