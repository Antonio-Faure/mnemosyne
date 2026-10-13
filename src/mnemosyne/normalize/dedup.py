"""Normalization and deduplication of collected assets."""

from __future__ import annotations

import re
from collections.abc import Iterable

from mnemosyne.models import Asset

_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    return _WS_RE.sub(" ", (title or "").strip().lower())


def normalize(assets: Iterable[Asset]) -> list[Asset]:
    """Drop unusable records and collapse exact duplicates by canonical id."""
    seen: set[str] = set()
    out: list[Asset] = []
    for asset in assets:
        if not asset.image_url and not asset.thumbnail_url:
            continue
        if asset.id in seen:
            continue
        seen.add(asset.id)
        out.append(asset)
    return out


class DedupIndex:
    """In-memory duplicate filter across a single run.

    Exact ids are always dropped, plus same-title records from the same source.
    (A perceptual-hash branch existed but was never fed image bytes — removed;
    see git history if near-duplicate detection is wired later.)
    """

    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._title_keys: set[tuple[str, str]] = set()

    def is_duplicate(self, asset: Asset) -> bool:
        if asset.id in self._ids:
            return True
        title_key = (asset.source_id, normalize_title(asset.title))
        return bool(title_key[1] and title_key in self._title_keys)

    def add(self, asset: Asset) -> None:
        self._ids.add(asset.id)
        title = normalize_title(asset.title)
        if title:
            self._title_keys.add((asset.source_id, title))
