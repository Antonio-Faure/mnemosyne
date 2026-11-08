"""GBIF occurrences with media — REST API v1 (``/occurrence/search``).

GBIF (Global Biodiversity Information Facility) is a public, keyless REST API.
Occurrences carry a ``media[]`` array whose licence is granted *per media*; the
API ``license`` filter targets the *occurrence* licence, never the media, so we
always re-check ``media[].license`` on our side and keep only CC0 1.0 and
CC BY 4.0 media (http or https, with or without ``www.``; everything else —
``None``, CC BY-NC, CC BY-SA… — is dropped).

A single occurrence may expose several qualifying media, so **one media = one
Asset**. Provider shapes are normalized into the canonical :class:`Asset` at
this boundary; the raw provider form never leaks past it. Images are never
downloaded here — only URLs are recorded (the media ``identifier`` is used as
both the main image and the thumbnail, since no size variant is known).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: maximum ``limit`` accepted by the GBIF occurrence search API
_MAX_LIMIT = 300

#: canonical licence name per recognized CC licence family
_LICENSE_NAMES = {"cc0": "CC0-1.0", "cc-by": "CC-BY-4.0"}


def _normalize_license(value: str | None) -> str | None:
    """Map a media-level licence URL to ``CC0-1.0`` / ``CC-BY-4.0``, else ``None``.

    Accepts ``http`` or ``https``, with or without ``www.``, and tolerates
    trailing ``/legalcode`` or query strings. Anything else — including a
    missing licence, CC BY-NC, CC BY-SA or a public-domain mark — is rejected.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lower()
    for scheme in ("https://", "http://"):
        if text.startswith(scheme):
            text = text[len(scheme) :]
            break
    if text.startswith("www."):
        text = text[len("www.") :]
    if text.startswith("creativecommons.org/publicdomain/zero/1.0"):
        return _LICENSE_NAMES["cc0"]
    if text.startswith("creativecommons.org/licenses/by/4.0"):
        return _LICENSE_NAMES["cc-by"]
    return None


def _is_http_url(value: str | None) -> bool:
    """Return True when ``value`` is an absolute http(s) URL."""
    if not value or not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


class GbifConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        api_limit = min(max(limit * 2, 10), _MAX_LIMIT)
        max_pages = int(filters.get("max_pages", 3))
        step = max(limit, 1)  # offset advances by the requested limit
        offset = int(filters.get("offset", 0))

        assets: list[Asset] = []
        count: int | None = None
        pages = 0
        while pages < max_pages:
            params = {
                "q": query,
                "mediaType": "StillImage",
                "limit": api_limit,
                "offset": offset,
            }
            data = await self.http.get_json(
                f"{self.descriptor.base_url}/occurrence/search", params=params
            )
            results = data.get("results") or []
            if isinstance(data.get("count"), int):
                count = data["count"]
            if not results:
                break

            for occurrence in results:
                assets.extend(self._occurrence_to_assets(occurrence))
                if len(assets) >= limit:
                    break

            pages += 1
            if len(assets) >= limit:
                break
            if data.get("endOfRecords"):
                break
            offset += step
            if isinstance(count, int) and offset >= count:
                break

        return assets[:limit]

    def _occurrence_to_assets(self, occurrence: dict[str, Any]) -> list[Asset]:
        """Normalize one occurrence into assets, one per qualifying media."""
        assets: list[Asset] = []
        for index, media in enumerate(occurrence.get("media") or []):
            if not isinstance(media, dict):
                continue
            license_name = _normalize_license(media.get("license"))
            identifier = media.get("identifier")
            if license_name is None or not _is_http_url(identifier):
                continue
            assets.append(self._media_to_asset(occurrence, media, license_name, index))
        return assets

    def _media_to_asset(
        self,
        occurrence: dict[str, Any],
        media: dict[str, Any],
        license_name: str,
        index: int,
    ) -> Asset:
        key = occurrence.get("key")
        identifier = media["identifier"]

        title = (
            occurrence.get("scientificName")
            or occurrence.get("species")
            or f"GBIF occurrence {key}"
        )
        creator = occurrence.get("recordedBy") or media.get("creator")

        year_raw = occurrence.get("year")
        event_date = occurrence.get("eventDate")
        if event_date:
            date_text = event_date
        elif year_raw not in (None, ""):
            date_text = str(year_raw)
        else:
            date_text = None

        year = parse_year(event_date)
        if year is None:
            if isinstance(year_raw, int):
                year = year_raw
            elif year_raw is not None:
                year = parse_year(str(year_raw))

        return Asset.build(
            self.id,
            f"{key}-{index}",
            title=title,
            description=media.get("description") or occurrence.get("country") or "",
            creator=creator,
            date_text=date_text,
            year=year,
            license=license_name,
            rights=media.get("rightsHolder") or creator or "",
            page_url=f"https://www.gbif.org/occurrence/{key}",
            image_url=identifier,
            thumbnail_url=identifier,
            extra={
                "occurrence_key": key,
                "taxon_key": occurrence.get("taxonKey"),
                "species": occurrence.get("species"),
                "country": occurrence.get("country"),
                "media_license": media.get("license"),
                "media_creator": media.get("creator"),
                "rights_holder": media.get("rightsHolder"),
            },
        )
