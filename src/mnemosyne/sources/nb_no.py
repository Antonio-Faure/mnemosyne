"""National Library of Norway (Nasjonalbiblioteket) catalog API → IIIF images.

Search the public NB catalog (``/catalog/v1/items``) and keep only notices that
are both public-domain and digital, resolving each one's IIIF manifest to the
first canvas image. No HTML scraping, no image download, no key.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: Fixed English rights line put on every public-domain asset.
_RIGHTS = "Public domain — National Library of Norway"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_value(value: Any) -> Any:
    """Return the first element of a list, else the value unchanged."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


class NbNoConnector(Connector):
    """Search the NB catalog and keep only open (public-domain + digital) notices."""

    default_max_pages: int = 3

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0:
            return []
        size = min(max(limit * 5, 20), 100)
        max_pages = _as_int(filters.get("max_pages")) or self.default_max_pages
        endpoint = f"{self.descriptor.base_url.rstrip('/')}/items"

        assets: list[Asset] = []
        for page in range(max_pages):
            params = {"q": query, "size": str(size), "page": str(page)}
            data = await self.http.get_json(endpoint, params=params) or {}
            items = (data.get("_embedded") or {}).get("items") or []
            if not items:
                break
            for item in items:
                if len(assets) >= limit:
                    return assets
                if not self._is_open(item):
                    continue
                manifest_url = self._manifest_url(item)
                if not manifest_url:
                    continue
                manifest = await self.http.get_json(manifest_url) or {}
                asset = self._build_asset(item, manifest)
                if asset is not None:
                    assets.append(asset)
            if len(assets) >= limit:
                break
            total_pages = _as_int((data.get("page") or {}).get("totalPages"))
            if total_pages is not None and page + 1 >= total_pages:
                break
        return assets

    @staticmethod
    def _is_open(item: dict[str, Any]) -> bool:
        """True only for notices that are both public-domain and digital."""
        info = item.get("accessInfo") or {}
        if info.get("isPublicDomain") is not True or info.get("isDigital") is not True:
            return False
        viewability = info.get("viewability")
        return not (isinstance(viewability, str) and viewability.upper() == "NONE")

    @staticmethod
    def _manifest_url(item: dict[str, Any]) -> str | None:
        links = item.get("_links") or {}
        href = (links.get("presentation") or {}).get("href")
        return href if isinstance(href, str) and href else None

    def _build_asset(
        self, item: dict[str, Any], manifest: dict[str, Any]
    ) -> Asset | None:
        nb_id = item.get("id")
        if not nb_id:
            return None
        canvas = self._first_canvas(manifest)
        if canvas is None:
            return None
        images = canvas.get("images") or []
        if not images:
            return None
        image_url = (images[0].get("resource") or {}).get("@id")
        if not image_url:
            return None
        thumbnail_url = self._thumbnail_url(manifest) or image_url

        meta = item.get("metadata") or {}
        access = item.get("accessInfo") or {}
        origin = meta.get("originInfo") or {}

        publisher = _first_value(origin.get("publisher"))
        media_types = meta.get("mediaTypes") or []
        if isinstance(media_types, str):
            media_types = [media_types]
        mediatype = media_types[0] if media_types else None

        date_text = _first_value(origin.get("issued")) or meta.get("dateCreated")

        creators = meta.get("creators")
        if isinstance(creators, list):
            creator = ", ".join(str(c) for c in creators[:3] if c) or None
        elif isinstance(creators, str):
            creator = creators or None
        else:
            creator = None

        description = publisher or (
            ", ".join(str(m) for m in media_types if m) if media_types else ""
        )

        nb_license = access.get("license")
        license_id = self.descriptor.license or "PDM-1.0"
        if isinstance(nb_license, str) and nb_license.lower() == "cc0":
            license_id = "CC0-1.0"

        return Asset.build(
            self.id,
            nb_id,
            title=meta.get("title") or f"National Library of Norway {nb_id}",
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=license_id,
            rights=_RIGHTS,
            page_url=f"https://www.nb.no/items/{nb_id}",
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            width=_as_int(canvas.get("width")),
            height=_as_int(canvas.get("height")),
            extra={
                "nb_id": nb_id,
                "mediatype": mediatype,
                "language": self._language(meta),
                "publisher": publisher,
                "subjects": self._subjects(meta),
                "nb_license": nb_license,
                "viewability": access.get("viewability"),
            },
        )

    @staticmethod
    def _first_canvas(manifest: dict[str, Any]) -> dict[str, Any] | None:
        sequences = manifest.get("sequences") or []
        if not sequences:
            return None
        canvases = sequences[0].get("canvases") or []
        return canvases[0] if canvases else None

    @staticmethod
    def _thumbnail_url(manifest: dict[str, Any]) -> str | None:
        thumbnail = manifest.get("thumbnail")
        if isinstance(thumbnail, str):
            return thumbnail or None
        if isinstance(thumbnail, dict):
            return thumbnail.get("@id") or thumbnail.get("id")
        return None

    @staticmethod
    def _language(meta: dict[str, Any]) -> str | None:
        languages = meta.get("languages") or []
        if not languages:
            return None
        first = languages[0]
        if isinstance(first, dict):
            return first.get("code") or first.get("@value")
        if isinstance(first, str):
            return first
        return None

    @staticmethod
    def _subjects(meta: dict[str, Any]) -> list[str] | None:
        subjects = meta.get("subject")
        terms: list[str] = []
        if isinstance(subjects, dict):
            for value in subjects.values():
                if isinstance(value, list):
                    terms.extend(str(v) for v in value if v)
                elif value:
                    terms.append(str(value))
        elif isinstance(subjects, list):
            terms.extend(str(v) for v in subjects if v)
        return terms or None
