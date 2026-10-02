"""Retention for browser session recordings.

`browser-harness` writes one directory per session under
`$BH_AGENT_WORKSPACE/recordings/<name>/` (~37 MB for a two-minute video) and
never removes anything. Left alone, a machine that runs one session a day grows
by ~13 GB a year, and the growth is invisible until the disk fills.

We therefore keep the most recent directories and delete the rest. Two
guarantees: a directory younger than `grace_s` is never touched (a session may
be recording right now), and a directory currently marked active by the harness
(`.active-<name>`) is never touched.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PruneResult:
    removed: tuple[str, ...] = ()
    kept: int = 0
    freed_bytes: int = 0
    skipped_active: tuple[str, ...] = ()


def recordings_root(root: Path | str | None = None) -> Path:
    """Where the harness stores recordings."""
    if root is not None:
        return Path(root)
    workspace = Path(
        os.environ.get("BH_AGENT_WORKSPACE")
        or Path("data") / "browser-harness" / "agent-workspace"
    )
    return workspace / "recordings"


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def prune_recordings(
    root: Path | str | None = None,
    keep: int = 8,
    grace_s: int = 3600,
    dry_run: bool = False,
) -> PruneResult:
    """Delete all but the `keep` most recent recording directories."""
    base = recordings_root(root)
    if not base.is_dir():
        return PruneResult()
    active = {p.name.removeprefix(".active-") for p in base.glob(".active-*")}
    now = time.time()
    dirs = [p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")]
    # mtime, not name: harness names are free-form ("rec-2026…", "gallica-final").
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    skipped: list[str] = []
    freed = 0
    for index, path in enumerate(dirs):
        if index < max(keep, 0):
            continue
        if path.name in active:
            skipped.append(path.name)
            continue
        if now - path.stat().st_mtime < grace_s:
            skipped.append(path.name)
            continue
        size = _dir_size(path)
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
        freed += size
    return PruneResult(
        removed=tuple(removed),
        kept=min(keep, len(dirs)),
        freed_bytes=freed,
        skipped_active=tuple(skipped),
    )
