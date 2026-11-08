"""Musée français du Pétrole (Merkwiller-Pechelbronn) — WordPress media API.

The museum's WordPress site exposes an open, keyless JSON media endpoint
(``/wp-json/wp/v2/media``) listing the heritage photo library of the
Pechelbronn oil field: wells, chevalements/derricks, drilling rigs, refineries,
gas flares, period postcards and figures. This is a fully *programmatic* access
path (no HTML scraping) so the connector talks JSON only and normalizes the
provider shape into :class:`Asset` at this boundary.

Licensing is the real constraint: both the museum site and the regional WebMuseo
portal are "all rights reserved". The descriptor is therefore declared
``enabled: false`` in ``docs/SOURCES.md`` (restrictive licence ⇒ stays off until
the project policy allows it — see the existing ``vam`` / ``vatican`` cases).
The connector and its tests are ready so that, once written authorization and a
reuse licence (CC BY / CC BY-SA 4.0 or public domain) are granted, re-activation
is a one-line change. While disabled, ``Engine.search`` never queries the source
and the harvest scheduler skips it, so no file is ever re-hosted.

Provider quirks normalised here:

* ``mime_type`` is **not** filtered server-side — images are kept on the client;
* metadata is thin: titles are derived from file names, ``caption``/``alt_text``
  are usually empty, there is no photographer and no original date. The REST
  ``date`` field is only the CMS upload timestamp, so it is stored in
  ``extra["wp_upload_date"]`` and *not* promoted to ``Asset.year`` (that would
  mis-date a historical photograph as modern).
"""

from __future__ import annotations

import html
import re
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: subset of WP REST fields requested (keeps payloads small and stable)
_FIELDS = (
    "id,date,link,title,caption,alt_text,media_type,mime_type,"
    "source_url,media_details,post,image_meta"
)


def _clean(value: Any) -> str:
    """Turn a ``*.rendered`` WP field into plain text (no tag, no entity)."""
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    return _WS_RE.sub(" ", text).strip()


class MuseePetrolePechelbronnConnector(Connector):
    """Normalizes the museum's WordPress media API into canonical assets."""

    def _media_url(self) -> str:
        return self.descriptor.base_url.rstrip("/") + "/media"

    async def search(
        self, query: str, limit: int = 20, **filters: Any
    ) -> list[Asset]:
        # per_page is capped at 100 server-side (per_page=200 -> HTTP 400).
        per_page = max(1, min(int(limit) if limit else 20, 100))
        params = {
            "search": query,
            "per_page": str(per_page),
            "page": "1",
            "orderby": "date",
            "order": "desc",
            "_fields": _FIELDS,
        }
        data = await self.http.get_json(self._media_url(), params=params)
        if not isinstance(data, list):
            return []

        assets: list[Asset] = []
        for item in data:
            asset = self._item_to_asset(item)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= per_page:
                break
        return assets

    def _item_to_asset(self, item: Any) -> Asset | None:
        if not isinstance(item, dict):
            return None
        # `mime_type` is NOT filtered server-side: filter images on the client.
        if item.get("media_type") != "image":
            return None
        mime = item.get("mime_type") or ""
        source_url = item.get("source_url")
        if not mime.startswith("image/") or not source_url:
            return None
        media_id = item.get("id")
        if media_id is None:
            return None
        source_asset_id = str(media_id)

        details = item.get("media_details") or {}
        sizes = details.get("sizes") or {}
        thumbnail_url = self._size_url(sizes, "medium") or source_url

        title = _clean((item.get("title") or {}).get("rendered")) or source_asset_id
        caption = _clean((item.get("caption") or {}).get("rendered"))
        alt_text = _clean(item.get("alt_text"))

        return Asset.build(
            self.id,
            source_asset_id,
            title=title,
            description=caption or alt_text,
            creator=None,
            date_text=None,
            year=None,
            license=self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=self._page_url(item, media_id),
            image_url=source_url,
            thumbnail_url=thumbnail_url,
            width=details.get("width"),
            height=details.get("height"),
            extra={
                "wp_media_id": media_id,
                "mime_type": mime,
                "source_url": source_url,
                "post": item.get("post"),
                "wp_upload_date": item.get("date"),
                "alt_text": alt_text,
            },
        )

    @staticmethod
    def _size_url(sizes: dict[str, Any], key: str) -> str | None:
        entry = sizes.get(key)
        if isinstance(entry, dict):
            url = entry.get("source_url")
            if isinstance(url, str) and url:
                return url
        return None

    @staticmethod
    def _page_url(item: dict[str, Any], media_id: Any) -> str | None:
        """Outbound link to the museum (the WP attachment page)."""
        link = item.get("link")
        if isinstance(link, str) and link.startswith("http"):
            return link
        return f"https://www.musee-du-petrole.com/?attachment_id={media_id}"
