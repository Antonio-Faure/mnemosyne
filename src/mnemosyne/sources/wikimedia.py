"""Wikimedia Commons full-text search (namespace 6 = File)."""

from __future__ import annotations

import re

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str | None) -> str:
    return _TAG_RE.sub("", value or "").strip()


class WikimediaConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": str(min(limit, 50)),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": "512",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        pages = data.get("query", {}).get("pages", [])
        assets: list[Asset] = []
        for page in pages:
            asset = self._page_to_asset(page)
            if asset:
                assets.append(asset)
        return assets

    def _page_to_asset(self, page: dict) -> Asset | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        meta = info.get("extmetadata", {})

        def m(field: str) -> str:
            return _clean(meta.get(field, {}).get("value"))

        title = page.get("title", "").removeprefix("File:")
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
            extra={"ns": page.get("ns"), "credit": m("Credit")},
        )
