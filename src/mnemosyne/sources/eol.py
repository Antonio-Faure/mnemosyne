"""Encyclopedia of Life (EOL) — REST API (``/search`` then ``/pages``).

EOL is a public, keyless REST API. A search (``/search/1.0.json``) returns
lightweight results (``id``, ``title``, ``content``); the media are only exposed
on the page detail (``/pages/1.0/<id>.json`` → ``taxonConcept.dataObjects[]``).
Each media's licence is granted *per dataObject*; we keep only ``image/*``
dataObjects whose licence is CC0 1.0 or CC BY 3.0/4.0 (http or https, with or
without ``www.``) and whose ``mediaURL`` is a non-empty http(s) URL — everything
else (``None``, CC BY-NC, CC BY-SA, CC BY-ND… ) is dropped.

A single species page may expose several qualifying media, so **one media = one
Asset**. Provider shapes are normalized into the canonical :class:`Asset` at
this boundary; the raw provider form never leaks past it. The detail page is
only fetched while the ``limit`` is not yet reached, and at most ``max_pages``
search pages are walked. Images are never downloaded here — only URLs are
recorded (the media ``mediaURL`` is used as both the image and the thumbnail,
since no size variant is known).

Transient Cloudflare/CDN hiccups (HTTP 5xx such as 520, or 429) are tolerated:
the affected result set is dropped instead of degrading the whole source. A real
access/rights error (401/403/404…) is *not* masked — it propagates to the engine.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset

log = get_logger("sources.eol")

#: EOL search page size (fixed by the API); used to bound pagination.
_SEARCH_PAGE_SIZE = 50

#: default cap on the number of search pages walked
_DEFAULT_MAX_PAGES = 3

#: maximum number of media requested per species page detail
_MAX_IMAGES_PER_PAGE = 50

#: canonical licence name per recognized CC licence variant
_LICENSE_CC0 = "CC0-1.0"
_LICENSE_BY = {3: "CC-BY-3.0", 4: "CC-BY-4.0"}

#: Transient CDN/server statuses: the HttpClient already retries 429/500/502/
#: 503/504 with backoff; the rest of Cloudflare's 5xx family (520–527) is caught
#: here and treated as a soft failure rather than a source error.
_TRANSIENT_STATUS = frozenset(
    {429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527}
)


def _normalize_license(value: str | None) -> str | None:
    """Map a media-level licence URL to ``CC0-1.0`` / ``CC-BY-3.0`` / ``CC-BY-4.0``.

    Accepts ``http`` or ``https``, with or without ``www.``, and tolerates a
    trailing ``/legalcode`` or query string. Only CC0 1.0 and CC BY 3.0/4.0 are
    recognised; everything else — including a missing licence, CC BY-NC,
    CC BY-SA, CC BY-ND or a public-domain mark — is rejected (``None``).
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
        return _LICENSE_CC0
    # the trailing slash after ``by`` keeps out ``by-sa``, ``by-nc`` and ``by-nd``
    prefix = "creativecommons.org/licenses/by/"
    if text.startswith(prefix):
        version = text[len(prefix) :]
        if version.startswith("4.0"):
            return _LICENSE_BY[4]
        if version.startswith("3.0"):
            return _LICENSE_BY[3]
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


def _truncate(text: Any, length: int = 600) -> str:
    """Return ``text`` stripped and truncated to ``length`` characters."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    return text[:length]


class EolConnector(Connector):
    async def _get_json(self, url: str, *, params: dict[str, Any]) -> Any | None:
        """GET JSON, tolerating transient CDN/server hiccups (return ``None``).

        The shared :class:`HttpClient` already retries its ``RETRY_STATUS``
        (429/500/502/503/504) with backoff. Cloudflare's remaining 5xx family
        (520–527) is transient too but outside that set, so it is caught here as
        a *soft* failure: the caller drops the affected result set instead of
        degrading the whole source. A real access/rights error (401/403/404…) is
        **not** masked — it propagates to the engine.
        """
        try:
            return await self.http.get_json(url, params=params)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in _TRANSIENT_STATUS:
                log.warning(
                    "eol: transient HTTP %s on %s; dropping result set", status, url
                )
                return None
            raise

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0:
            return []

        max_pages = int(filters.get("max_pages", _DEFAULT_MAX_PAGES))
        images_per_page = min(max(limit, 5), _MAX_IMAGES_PER_PAGE)

        assets: list[Asset] = []
        seen: set[str] = set()

        page = 1
        while page <= max_pages:
            data = await self._get_json(
                f"{self.descriptor.base_url}/search/1.0.json",
                params={"q": query, "page": page},
            )
            if data is None:
                break
            results = data.get("results") or []
            if not results:
                break

            total = data.get("totalResults")
            per_page = data.get("itemsPerPage")
            if not isinstance(per_page, int) or per_page <= 0:
                per_page = len(results)

            for result in results:
                if len(assets) >= limit:
                    break
                page_id = result.get("id")
                if page_id is None:
                    continue
                page_data = await self._get_json(
                    f"{self.descriptor.base_url}/pages/1.0/{page_id}.json",
                    params={
                        "images_per_page": images_per_page,
                        "common_names": "false",
                        "details": "true",
                    },
                )
                if page_data is None:
                    continue
                for asset in self._page_to_assets(page_id, result, page_data):
                    if asset.id in seen:
                        continue
                    seen.add(asset.id)
                    assets.append(asset)
                    if len(assets) >= limit:
                        break

            if len(assets) >= limit:
                break
            if isinstance(total, int) and page * per_page >= total:
                break
            page += 1

        return assets[:limit]

    def _page_to_assets(
        self,
        page_id: Any,
        result: dict[str, Any],
        page_data: dict[str, Any],
    ) -> list[Asset]:
        """Normalize one species page into assets, one per qualifying media."""
        taxon = page_data.get("taxonConcept") or {}
        assets: list[Asset] = []
        for index, media in enumerate(taxon.get("dataObjects") or []):
            if not isinstance(media, dict):
                continue
            mime = media.get("mimeType")
            if not isinstance(mime, str) or not mime.startswith("image/"):
                continue
            media_url = media.get("mediaURL")
            if not _is_http_url(media_url):
                continue
            license_name = _normalize_license(media.get("license"))
            if license_name is None:
                continue
            assets.append(
                self._media_to_asset(page_id, result, taxon, media, license_name, index)
            )
        return assets

    def _media_to_asset(
        self,
        page_id: Any,
        result: dict[str, Any],
        taxon: dict[str, Any],
        media: dict[str, Any],
        license_name: str,
        index: int,
    ) -> Asset:
        scientific_name = taxon.get("scientificName")
        title = scientific_name or result.get("title") or f"EOL page {page_id}"
        rights_holder = media.get("rightsHolder")
        description = (
            media.get("description") or _truncate(result.get("content")) or ""
        )
        media_url = media["mediaURL"]

        return Asset.build(
            self.id,
            f"{page_id}-{index}",
            title=title,
            description=description,
            creator=rights_holder,
            date_text=None,
            year=None,
            license=license_name,
            rights=rights_holder or media.get("attribution") or "",
            page_url=f"https://eol.org/pages/{page_id}",
            image_url=media_url,
            thumbnail_url=media_url,
            extra={
                "eol_page_id": page_id,
                "scientific_name": scientific_name,
                "media_license": media.get("license"),
                "rights_holder": rights_holder,
            },
        )
