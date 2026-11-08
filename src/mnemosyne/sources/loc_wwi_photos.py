"""Library of Congress — World War I photographs, via the loc.gov JSON API.

The Prints & Photographs collection (``/collections/world-war-i/``) exposes a
public, keyless JSON search API (``?fo=json``). Each result carries the item
page URL (``id``/``url``) and a list of image derivatives on ``tile.loc.gov``;
we normalize those into the canonical :class:`Asset`. No HTML scraping: the
documented JSON endpoint is the sole access path.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _first_str(value: Any) -> str | None:
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _str_list(value: Any) -> list[str]:
    return [s.strip() for s in _as_list(value) if isinstance(s, str) and s.strip()]


def _join(value: Any, sep: str = "; ") -> str:
    return sep.join(_str_list(value))


def _image_urls(result: dict[str, Any]) -> list[str]:
    """Collect candidate image URLs from a search result, de-duplicated."""
    candidates: list[Any] = [result.get("image_url")]
    item = result.get("item")
    if isinstance(item, dict):
        candidates.append(item.get("image_url"))
    urls: list[str] = []
    for source in candidates:
        for candidate in _as_list(source):
            if (
                isinstance(candidate, str)
                and candidate.startswith("http")
                and candidate not in urls
            ):
                urls.append(candidate)
    if urls:
        return urls
    # Fallback: some items only list images under ``resources``.
    for resource in _as_list(result.get("resources")):
        if not isinstance(resource, dict):
            continue
        for key in ("image", "images"):
            for candidate in _as_list(resource.get(key)):
                if (
                    isinstance(candidate, str)
                    and candidate.startswith("http")
                    and candidate not in urls
                ):
                    urls.append(candidate)
    return urls


def _item_page(result: dict[str, Any]) -> str | None:
    for key in ("url", "id"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


def _asset_id(result: dict[str, Any]) -> str | None:
    page = _item_page(result)
    if not page:
        return None
    parts = [p for p in urlsplit(page).path.split("/") if p]
    return parts[-1] if parts else None


class LocWwiPhotosConnector(Connector):
    """Search World War I photographs from the Library of Congress (JSON API)."""

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        params = {
            "q": query,
            "fo": "json",
            "c": str(max(1, min(limit, 100))),
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        results = data.get("results") if isinstance(data, dict) else data
        if not isinstance(results, list):
            return []

        assets: list[Asset] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            asset = self._parse_result(result)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _parse_result(self, result: dict[str, Any]) -> Asset | None:
        source_asset_id = _asset_id(result)
        images = _image_urls(result)
        if not source_asset_id or not images:
            return None

        item = result.get("item") if isinstance(result.get("item"), dict) else {}
        rights = (
            _first_str(result.get("rights"))
            or _first_str(item.get("rights"))
            or self.descriptor.rights
        )
        date_text = _first_str(result.get("date"))
        contributors = _str_list(result.get("contributor"))
        description = _join(result.get("description")) or _first_str(item.get("summary")) or ""

        return Asset.build(
            self.id,
            source_asset_id,
            title=_first_str(result.get("title")) or "",
            description=description,
            creator=contributors[0] if contributors else None,
            date_text=date_text,
            year=parse_year(date_text),
            rights=rights,
            license=self.descriptor.license,
            page_url=_item_page(result),
            # LoC orders ``image_url`` smallest → largest: keep the widest
            # derivative as the image and the first (thumbnail) for previews.
            image_url=images[-1],
            thumbnail_url=images[0],
            extra={
                "source": "loc-json",
                "id": result.get("id"),
                "original_format": _str_list(result.get("original_format")),
                "online_format": _str_list(result.get("online_format")),
                "subject": _str_list(result.get("subject")),
                "location": _str_list(result.get("location")),
                "contributor": contributors,
            },
        )
