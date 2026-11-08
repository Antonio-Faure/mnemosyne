"""Wikimedia Commons photographs (namespace 6 / File) via the imageinfo API.

This is the photo-specific sibling of :mod:`mnemosyne.sources.wikimedia`. A
plain full-text search on Commons ranks OCR-heavy book scans (PDF / DjVu files
uploaded from Internet Archive) above genuine photographs, so historical queries
came back as digitised text rather than pictures. Here the search is constrained
to ``filetype:bitmap`` and every hit is additionally checked for a raster MIME
type, so the connector only ever emits real photographs.
"""

from __future__ import annotations

import os
import re

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_TAG_RE = re.compile(r"<[^>]+>")

#: Non-raster formats that still live in the ``image/`` MediaWiki MIME space.
#: Vector drawings (SVG) and scanned documents (DjVu) are not photographs.
_NON_RASTER_MIMES = frozenset(
    {
        "image/svg+xml",
        "image/vnd.djvu",
        "image/x-djvu",
    }
)


def _clean(value: str | None) -> str:
    return _TAG_RE.sub("", value or "").strip()


def _is_photo(mime: str | None) -> bool:
    """True when ``mime`` denotes a raster image (a photograph, not a document).

    ``filetype:bitmap`` already narrows the server-side search; this guard keeps
    the connector honest if the API ever returns something else. An absent MIME
    is trusted (the search keyword already constrained the result set).
    """
    mime = (mime or "").strip().lower()
    if not mime:
        return True
    return mime.startswith("image/") and mime not in _NON_RASTER_MIMES


class WikimediaCommonsPhotosConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": str(min(limit, 50)),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": "512",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        pages = (data.get("query") or {}).get("pages") or []
        assets: list[Asset] = []
        for page in pages:
            asset = self._page_to_asset(page)
            if asset:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _page_to_asset(self, page: dict) -> Asset | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        if not _is_photo(info.get("mime")):
            return None
        meta = info.get("extmetadata", {})

        def m(field: str) -> str:
            return _clean(meta.get(field, {}).get("value"))

        # ``title`` is the MediaWiki "File:Name.ext" page title: drop the
        # namespace prefix and the file extension so the asset reads as a
        # caption (e.g. "File:German troops Brussels 1914.jpg" -> "German troops
        # Brussels 1914").
        title, _ext = os.path.splitext(page.get("title", "").removeprefix("File:"))
        date_text = m("DateTimeOriginal") or None
        license_name = m("LicenseShortName") or self.descriptor.license
        artist = m("Artist") or None
        description = m("ImageDescription")

        return Asset.build(
            self.id,
            str(page.get("pageid") or title),
            title=title,
            description=description,
            creator=artist,
            date_text=date_text,
            year=parse_year(date_text),
            license=license_name,
            rights=self.descriptor.rights,
            page_url=info.get("descriptionurl"),
            image_url=info.get("url"),
            thumbnail_url=info.get("thumburl"),
            width=info.get("width"),
            height=info.get("height"),
            extra={
                "ns": page.get("ns"),
                "mime": info.get("mime"),
                "credit": m("Credit"),
            },
        )
