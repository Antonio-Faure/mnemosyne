"""The dev worktree cleanup must never prune globally (shared repo with the host).

A global `git worktree prune` in the container unregisters the host's
worktrees (different absolute paths look missing) and vice versa — two tasks
died to this (Imaginerio #73, and host-side merges mid-operation).
"""

from __future__ import annotations

from pathlib import Path

from mnemosyne.dev.worktree import _drop_stale_registration


def test_drop_stale_registration_only_touches_the_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    admin = repo / ".git" / "worktrees"
    (admin / "agent-worktree").mkdir(parents=True)
    (admin / "agent-worktree" / "gitdir").write_text(
        str(tmp_path / "agent-worktree" / ".git"), encoding="utf-8"
    )
    (admin / "helpers-worktree").mkdir(parents=True)
    (admin / "helpers-worktree" / "gitdir").write_text(
        str(tmp_path / "helpers-worktree" / ".git"), encoding="utf-8"
    )

    _drop_stale_registration(repo, tmp_path / "agent-worktree")

    assert not (admin / "agent-worktree").exists()
    assert (admin / "helpers-worktree").exists()
