"""Deutsches Museum Digital (Munich) via the public Omeka S REST API.

The portal (digital.deutsches-museum.de) runs Omeka S. Its public JSON API
lives at ``/api`` and permits anonymous read access to public items:

* ``GET {base}/items?search=<query>&per_page=<n>`` returns item representations
  (JSON-LD) with Dublin Core metadata (``dcterms:*``) and thumbnails;
* each item embeds its ``o:media``; an image media exposes ``o:original_url``
  (full file) and ``thumbnail_display_urls`` (derivatives).

We normalize each item into the canonical ``Asset``: nothing of Omeka's shape
leaks past this connector. Rights are per-object (``dcterms:rights`` /
``dcterms:license``); the collection mixes public-domain and Creative Commons
works, so the descriptor keeps ``license: varies``.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.deutsches_museum")

_MAX_PER_PAGE = 100


def _first_value(item: dict, *keys: str) -> str | None:
    """First literal value for any of the given Dublin Core keys.

    Omeka S represents every property as a list of value objects
    (``{"@value": ...}``); resource references (no ``@value``) are skipped.
    """
    for key in keys:
        values = item.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                text = value.get("@value")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return None


def _image_media(item: dict) -> dict | None:
    """First embedded image media of an item that carries an original file."""
    media = item.get("o:media")
    if not isinstance(media, list):
        return None
    for entry in media:
        if not isinstance(entry, dict):
            continue
        media_type = str(entry.get("o:media_type") or "")
        if media_type and not media_type.startswith("image"):
            continue
        if entry.get("o:original_url"):
            return entry
    return None


def _thumb_from(obj: dict | None, size: str) -> str | None:
    if not isinstance(obj, dict):
        return None
    thumbs = obj.get("thumbnail_display_urls")
    if isinstance(thumbs, dict):
        url = thumbs.get(size)
        if isinstance(url, str) and url:
            return url
    return None


class DeutschesMuseumConnector(Connector):
    async def search(
        self, query: str, limit: int = 20, **filters: Any
    ) -> list[Asset]:
        per_page = str(min(max(limit, 1), _MAX_PER_PAGE))
        params = {"search": query, "per_page": per_page}
        url = self.descriptor.base_url + "/items"
        data = await self.http.get_json(url, params=params)
        if not isinstance(data, list):
            log.debug(
                "deutsches_museum: unexpected payload (%s)",
                type(data).__name__,
            )
            return []

        assets: list[Asset] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            asset = self._to_asset(item)
            if asset is None:
                continue
            assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _to_asset(self, item: dict) -> Asset | None:
        item_id = item.get("o:id")
        if item_id is None:
            return None
        media = _image_media(item)
        original = media.get("o:original_url") if media else None
        image_url = original or _thumb_from(item, "large")
        if not image_url:
            return None
        thumbnail = (
            _thumb_from(media, "large")
            or _thumb_from(item, "medium")
            or _thumb_from(item, "large")
            or image_url
        )

        title = item.get("o:title") or _first_value(item, "dcterms:title") or ""
        date_text = _first_value(
            item,
            "dcterms:date",
            "dcterms:created",
            "dcterms:issued",
            "dcterms:temporal",
        )
        rights = _first_value(item, "dcterms:rights", "dcterms:license")
        license = (
            _first_value(item, "dcterms:license", "dcterms:rights")
            or self.descriptor.license
        )

        iiif_id = None
        if media is not None:
            data = media.get("o:data")
            if isinstance(data, dict):
                iiif_id = data.get("@id")

        media_type = media.get("o:media_type") if media else None

        return Asset.build(
            self.id,
            str(item_id),
            title=title,
            description=_first_value(item, "dcterms:description") or "",
            creator=_first_value(item, "dcterms:creator", "dcterms:contributor"),
            date_text=date_text,
            year=parse_year(date_text),
            license=license,
            rights=rights or self.descriptor.rights,
            page_url=self._page_url(item, item_id),
            image_url=image_url,
            thumbnail_url=thumbnail,
            iiif_id=iiif_id,
            extra={
                "provider": "Deutsches Museum Digital",
                "media_type": media_type,
            },
        )

    def _page_url(self, item: dict, item_id: Any) -> str | None:
        sites = item.get("o:site")
        if isinstance(sites, list) and sites and isinstance(sites[0], dict):
            slug = sites[0].get("o:slug")
            if slug:
                base = "https://digital.deutsches-museum.de"
                return f"{base}/s/{slug}/item/{item_id}"
        api_id = item.get("@id")
        if isinstance(api_id, str) and api_id:
            return api_id
        return None
