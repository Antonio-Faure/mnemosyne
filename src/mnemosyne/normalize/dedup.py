"""Normalization and deduplication of collected assets."""

from __future__ import annotations

import re
from collections.abc import Iterable

from mnemosyne.models import Asset

_WS_RE = re.compile(r"\s+")

#: Titles too generic to identify a work across providers.
_GENERIC_TITLES = {
    "sans titre",
    "sans titre.",
    "untitled",
    "untitled.",
    "no title",
    "title",
    "image",
}


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


def _cross_source_key(asset: Asset) -> tuple[str, str] | None:
    """Identity of a WORK across providers: title + creator, when specific enough.

    A title alone would merge unrelated records ("Sans titre", "Portrait"…), so
    a short or generic title yields no key and the asset is always kept.
    """
    title = normalize_title(asset.title)
    if len(title) < 8 or title in _GENERIC_TITLES:
        return None
    return (title, normalize_title(asset.creator or ""))


def dedup_across_sources(assets: Iterable[Asset]) -> list[Asset]:
    """Collapse the same work served by several aggregators (Europeana/DPLA/…).

    The first occurrence wins (catalog order), so the result is deterministic.
    """
    seen: set[tuple[str, str]] = set()
    out: list[Asset] = []
    for asset in assets:
        key = _cross_source_key(asset)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
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
