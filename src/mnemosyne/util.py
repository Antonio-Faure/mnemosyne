"""Small shared helpers: atomic writes, stable ids, year parsing."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path

_YEAR_RE = re.compile(r"(1[0-9]{3}|20[0-9]{2})")


def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def atomic_write_bytes(path: str | os.PathLike, data: bytes) -> Path:
    """Write `data` to `path` atomically via a sibling `.tmp` file.

    A killed process can never leave a partially written final artifact.
    """
    p = Path(path)
    ensure_dir(p.parent)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return p


def atomic_write_text(path: str | os.PathLike, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def stable_id(*parts: object) -> str:
    """Deterministic short id from arbitrary parts (used for Asset ids)."""
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def parse_year(text: str | None) -> int | None:
    """Extract a plausible 4-digit year from free text, else None."""
    if not text:
        return None
    match = _YEAR_RE.search(str(text))
    if not match:
        return None
    try:
        year = int(match.group(1))
    except ValueError:
        return None
    return year if 1000 <= year <= datetime.now(UTC).year + 1 else None


def finish_text(value: object) -> str | None:
    """Normalize an agent 'finish' value (str, or Stirrup FinishParams) to text."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    for attr in ("reason", "summary", "text"):
        candidate = getattr(value, attr, None)
        if isinstance(candidate, str) and candidate:
            return candidate
    return str(value)


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def cleanup_orphan_tmp(directory: str | os.PathLike) -> int:
    """Remove leftover `*.tmp` files from a crash. Returns count removed."""
    root = Path(directory)
    if not root.exists():
        return 0
    removed = 0
    for tmp in root.rglob("*.tmp"):
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
            removed += 1
    return removed
