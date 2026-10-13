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


def test_ensure_worktree_reuses_a_killed_activation(tmp_path, monkeypatch):
    """A crash never runs the removal: the leftover worktree is reused as-is."""
    from mnemosyne.dev.worktree import ensure_worktree, remove_worktree, worktree_is_reusable

    monkeypatch.setattr("mnemosyne.dev.worktree._is_usable", lambda path: True)

    def fake_add(repo, path, base_branch):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "wip.txt").write_text("fresh", encoding="utf-8")
        return path

    monkeypatch.setattr("mnemosyne.dev.worktree.add_worktree", fake_add)

    repo = tmp_path / "repo"
    path = tmp_path / "agent-worktree"

    worktree = ensure_worktree(repo, path, "main", 42)
    assert (worktree / "wip.txt").read_text(encoding="utf-8") == "fresh"
    assert worktree_is_reusable(path, 42) is True
    assert worktree_is_reusable(path, 43) is False

    # killed activation: uncommitted work is still there at the next activation
    (path / "wip.txt").write_text("uncommitted work", encoding="utf-8")
    again = ensure_worktree(repo, path, "main", 42)
    assert again == path
    assert (again / "wip.txt").read_text(encoding="utf-8") == "uncommitted work"

    # another task resets the worktree instead of inheriting foreign work
    reset = ensure_worktree(repo, path, "main", 43)
    assert (reset / "wip.txt").read_text(encoding="utf-8") == "fresh"

    remove_worktree(repo, reset)
    assert not path.with_name(path.name + ".task").exists()
