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


def perceptual_hash(image_bytes: bytes) -> str | None:
    """Optional pHash; returns None when Pillow/imagehash are not installed."""
    try:
        import io

        import imagehash
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return str(imagehash.phash(image))
    except Exception:  # noqa: BLE001 - bad/corrupt image
        return None


class DedupIndex:
    """In-memory near-duplicate filter across a single run.

    Exact ids are always dropped. When `use_phash` is enabled and media deps are
    present, images within a small Hamming distance are considered duplicates.
    """

    def __init__(self, use_phash: bool = False, max_hamming: int = 6):
        self.use_phash = use_phash
        self.max_hamming = max_hamming
        self._ids: set[str] = set()
        self._title_keys: set[tuple[str, str]] = set()
        self._hashes: list[object] = []

    def is_duplicate(self, asset: Asset, image_bytes: bytes | None = None) -> bool:
        if asset.id in self._ids:
            return True
        title_key = (asset.source_id, normalize_title(asset.title))
        if title_key[1] and title_key in self._title_keys:
            return True
        if self.use_phash and image_bytes is not None:
            h = perceptual_hash(image_bytes)
            if h is not None:
                from mnemosyne.normalize.dedup import _phash_close  # local import avoids dep

                if any(_phash_close(h, other, self.max_hamming) for other in self._hashes):
                    return True
                self._hashes.append(h)
        return False

    def add(self, asset: Asset) -> None:
        self._ids.add(asset.id)
        title = normalize_title(asset.title)
        if title:
            self._title_keys.add((asset.source_id, title))


def _phash_close(a: str, b: str, max_hamming: int) -> bool:
    try:
        import imagehash
    except ImportError:
        return False
    try:
        return (imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)) <= max_hamming
    except Exception:  # noqa: BLE001
        return False
