"""Retention of harness session recordings (the harness never prunes them)."""

from __future__ import annotations

import time
from pathlib import Path

from mnemosyne.browser.recordings import prune_recordings, recordings_root


def _make(root: Path, name: str, age_s: float = 7200, size: int = 1024) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "video.mp4").write_bytes(b"0" * size)
    when = time.time() - age_s
    import os as _os

    _os.utime(d, (when, when))
    return d


def test_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BH_AGENT_WORKSPACE", str(tmp_path / "ws"))
    assert recordings_root() == tmp_path / "ws" / "recordings"


def test_keeps_n_newest_and_deletes_older(tmp_path):
    root = tmp_path / "recordings"
    for i in range(5):
        _make(root, f"rec-{i}", age_s=(10 - i) * 3600)  # rec-4 newest
    result = prune_recordings(root=root, keep=2, grace_s=0)
    assert result.kept == 2
    assert set(result.removed) == {"rec-0", "rec-1", "rec-2"}
    assert not (root / "rec-0").exists()
    assert (root / "rec-4").exists() and (root / "rec-3").exists()
    assert result.freed_bytes >= 3 * 1024


def test_grace_period_protects_fresh_recording(tmp_path):
    root = tmp_path / "recordings"
    _make(root, "old", age_s=7200)
    _make(root, "fresh", age_s=60)
    result = prune_recordings(root=root, keep=0, grace_s=3600)
    assert result.removed == ("old",)
    assert (root / "fresh").exists(), "a session may still be recording"
    assert result.skipped_active == ("fresh",)


def test_active_marker_is_never_deleted(tmp_path):
    root = tmp_path / "recordings"
    _make(root, "live", age_s=7200)
    (root / ".active-live").write_text("", encoding="utf-8")
    result = prune_recordings(root=root, keep=0, grace_s=0)
    assert result.removed == ()
    assert result.skipped_active == ("live",)
    assert (root / "live").exists()


def test_dry_run_changes_nothing(tmp_path):
    root = tmp_path / "recordings"
    _make(root, "a", age_s=7200)
    result = prune_recordings(root=root, keep=0, grace_s=0, dry_run=True)
    assert result.removed == ("a",)
    assert (root / "a").exists()


def test_missing_root_is_not_an_error(tmp_path):
    assert prune_recordings(root=tmp_path / "nope").removed == ()
