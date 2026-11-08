"""Imperial War Museums — First World War official photography (Q series).

IWM holds the largest British First World War photography collection (the
"Q series"). Its own WW1 official photography was donated to Wikimedia Commons
and is public domain there, so it is queried through the keyless MediaWiki API.
The IWM website itself is not scraped: its ``/collections/search`` page is
disallowed by ``robots.txt`` and exposes no usable public JSON API, while its
item images are "© IWM" (licensing required). Each Commons hit is normalised to
the canonical :class:`~mnemosyne.models.Asset`, preserving the Q-series
catalogue reference (e.g. ``Q9848``) in ``extra["catalog_ref"]``.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_TAG_RE = re.compile(r"<[^>]+>")
_Q_REF_RE = re.compile(r"Q\s?\d+")
_Q_REF_TRAIL_RE = re.compile(r"\s*Q\s?\d+\s*$")

#: The Q series (large, direct-membership core collection) plus the adjacent
#: WW1 official-photography collections on Commons (union, deduped on pageid).
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Ministry of Information First World War Official Collection",
    "The Official Visits To the Western Front, 1914-1918",
    "IWM First World War Women's War Work Collection photographs",
    "First World War Aerial Photographs Collection",
    "First World War Official Panoramas Collection",
)

#: Open licences we are willing to redistribute (checked per record).
_OPEN_LICENSE_PREFIXES = ("public domain", "cc0", "cc by", "pd-", "pdm")

#: Non-raster formats that still live in the ``image/`` MediaWiki MIME space.
_NON_RASTER_MIMES = frozenset({"image/svg+xml", "image/vnd.djvu", "image/x-djvu"})

#: Descriptive User-Agent, per Wikimedia's UA policy.
_USER_AGENT = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)

_THUMB_WIDTH = 800


def _clean(value: str | None) -> str:
    """Strip markup tags and collapse whitespace."""
    text = _TAG_RE.sub(" ", value or "")
    return " ".join(text.split())


def _is_photo(mime: str | None) -> bool:
    """True when ``mime`` denotes a raster image (a photograph, not a vector)."""
    mime = (mime or "").strip().lower()
    if not mime:
        return True
    return mime.startswith("image/") and mime not in _NON_RASTER_MIMES


def _is_open_license(name: str | None, copyrighted: str | None) -> bool:
    """Only open licences (Public domain / CC0 / CC BY / PD-*) are kept."""
    if (copyrighted or "").strip().lower() == "true":
        return False
    low = (name or "").strip().lower()
    return any(low.startswith(prefix) for prefix in _OPEN_LICENSE_PREFIXES)


def _catalog_ref(*texts: str | None) -> str | None:
    """First Q-series reference (``Q9848``) found in the given texts."""
    for text in texts:
        match = _Q_REF_RE.search(text or "")
        if match:
            return re.sub(r"\s+", "", match.group(0))
    return None


def _clean_title(raw: str | None) -> str:
    """``File:The Trench Warfare, 1914-1918 Q4659.jpg`` -> readable caption."""
    title = (raw or "").removeprefix("File:")
    title, _ext = os.path.splitext(title)
    title = _Q_REF_TRAIL_RE.sub("", title)
    return title.strip().rstrip(",;:-").strip()


def _strip_query(url: str | None) -> str | None:
    if not url:
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _thumb_url(title: str | None) -> str | None:
    """Stable thumbnail via ``Special:FilePath`` (302 -> valid thumb)."""
    name = (title or "").removeprefix("File:")
    if not name:
        return None
    encoded = quote(name, safe="")
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        f"{encoded}?width={_THUMB_WIDTH}"
    )


class IwmWw1Connector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0:
            return []
        categories = self._categories(filters)
        max_pages = int(self.descriptor.extra.get("max_pages", 5) or 5)
        seen: set[str] = set()
        assets: list[Asset] = []
        for category in categories:
            cont: dict[str, Any] | None = None
            for _ in range(max_pages):
                params = self._params(query, category, limit)
                if cont:
                    params.update({str(k): str(v) for k, v in cont.items()})
                data = await self.http.get_json(
                    self.descriptor.base_url,
                    params=params,
                    headers={"User-Agent": _USER_AGENT},
                )
                pages = (data.get("query") or {}).get("pages") or []
                for page in pages:
                    key = self._key(page)
                    if key is None or key in seen:
                        continue
                    seen.add(key)
                    asset = self._page_to_asset(page)
                    if asset is not None:
                        assets.append(asset)
                        if len(assets) >= limit:
                            return assets[:limit]
                cont = data.get("continue")
                if not cont or not pages:
                    break
        return assets[:limit]

    def _categories(self, filters: dict[str, Any]) -> tuple[str, ...]:
        raw = filters.get("categories")
        if raw is None:
            raw = self.descriptor.extra.get("categories")
        if raw is None:
            return DEFAULT_CATEGORIES
        if isinstance(raw, str):
            return (raw,)
        return tuple(str(cat) for cat in raw)

    @staticmethod
    def _key(page: dict[str, Any]) -> str | None:
        pageid = page.get("pageid")
        if pageid is not None:
            return str(pageid)
        title = page.get("title")
        return title if title else None

    def _params(self, query: str, category: str, limit: int) -> dict[str, str]:
        return {
            "action": "query",
            "generator": "search",
            "gsrsearch": f'{query} incategory:"{category}"',
            "gsrnamespace": "6",
            "gsrlimit": str(min(limit, 50)),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata|user",
            "iiurlwidth": str(_THUMB_WIDTH),
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        }

    def _page_to_asset(self, page: dict[str, Any]) -> Asset | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        if not _is_photo(info.get("mime")):
            return None
        meta = info.get("extmetadata") or {}

        def m(field: str) -> str:
            return _clean((meta.get(field) or {}).get("value"))

        license_name = m("LicenseShortName")
        if not _is_open_license(license_name, m("Copyrighted")):
            return None

        raw_title = page.get("title", "")
        description = m("ImageDescription")
        creator = m("Artist") or None
        date_text = m("DateTimeOriginal").split("date QS")[0].strip() or None

        return Asset.build(
            self.id,
            str(page.get("pageid") or raw_title),
            title=_clean_title(raw_title),
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=license_name,
            rights=self.descriptor.rights,
            page_url=info.get("descriptionurl"),
            image_url=_strip_query(info.get("url")),
            thumbnail_url=_thumb_url(raw_title),
            width=info.get("width"),
            height=info.get("height"),
            extra={
                "catalog_ref": _catalog_ref(raw_title, description),
                "mime": info.get("mime"),
                "user": info.get("user"),
            },
        )
