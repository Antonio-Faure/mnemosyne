"""Throwaway git worktree for the dev agent (never switch the main checkout)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _drop_stale_registration(repo: Path, path: Path) -> None:
    """Drop the admin entry of THIS worktree only — never a global prune.

    The repo is shared with the host, whose worktrees live at different
    absolute paths: from here they all look missing, so `git worktree prune`
    silently unregisters them mid-operation (and the host's prune does the
    same to ours). Scope the cleanup to the exact path we manage.
    """
    admin_root = repo / ".git" / "worktrees"
    if not admin_root.is_dir():
        return
    import shutil

    wanted = str(path / ".git")
    for admin in admin_root.iterdir():
        try:
            marker = (admin / "gitdir").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if marker == wanted:
            shutil.rmtree(admin, ignore_errors=True)
            return


def add_worktree(repo: str | Path, path: str | Path, base_branch: str) -> Path:
    repo = Path(repo)
    path = Path(path)
    # The path is disposable: a killed run can leave it as a broken registration,
    # a locked worktree, or a plain directory — each defeats `worktree add`.
    # Clean up in escalation order until the path is really gone.
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
        capture_output=True, text=True,
    )
    _drop_stale_registration(repo, path)
    import shutil

    shutil.rmtree(path, ignore_errors=True)
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
