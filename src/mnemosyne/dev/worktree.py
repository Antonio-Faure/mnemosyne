"""Throwaway git worktree for the dev agent (never switch the main checkout)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mnemosyne.logger import get_logger

log = get_logger("dev.worktree")


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
        capture_output=True, text=True, timeout=120,
    )
    _drop_stale_registration(repo, path)
    import shutil

    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin", base_branch],
        capture_output=True, text=True, timeout=180,
    )
    res = subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(path), f"origin/{base_branch}"],
        capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {res.stderr.strip()[:200]}")
    return path


def _task_marker(path: Path) -> Path:
    """Marker lives NEXT TO the worktree (no untracked file in `git status`)."""
    return path.with_name(path.name + ".task")


def _is_usable(path: Path) -> bool:
    if not (path / ".git").exists():
        return False
    probe = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--git-dir"],
        capture_output=True, text=True, timeout=30,
    )
    return probe.returncode == 0


def worktree_is_reusable(path: str | Path, task_id: int) -> bool:
    """True when the leftover worktree belongs to THIS task (killed activation)."""
    path = Path(path)
    if not _is_usable(path):
        return False
    try:
        return _task_marker(path).read_text(encoding="utf-8").strip() == str(task_id)
    except OSError:
        return False


def ensure_worktree(repo: str | Path, path: str | Path, base_branch: str, task_id: int) -> Path:
    """Reuse the worktree left by a killed run of the same task, else reset it.

    A crash never reaches the `finally` that removes the worktree: reusing it
    preserves the uncommitted work the session cache says was written. A
    worktree left by another task (or unusable) is rebuilt from origin/base.
    """
    path = Path(path)
    if worktree_is_reusable(path, task_id):
        log.info("worktree réutilisé (activation tuée de la tâche #%s)", task_id)
        return path
    worktree = add_worktree(repo, path, base_branch)
    try:
        _task_marker(worktree).write_text(str(task_id), encoding="utf-8")
    except OSError as exc:
        log.debug("cannot write the worktree task marker: %s", exc)
    return worktree


def remove_worktree(repo: str | Path, path: str | Path) -> None:
    path = Path(path)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    _task_marker(path).unlink(missing_ok=True)
