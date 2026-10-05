"""Archives départementales du Nord — industrial heritage of the Nord (France).

Platform: https://archivesdepartementales.lenord.fr
CMS: Arkothèque / Mnesys; ARK NAAN 33518 (``/ark:/33518/<arkName>``).

Access model — **programmatic first**:

* **No IIIF** (``location.iiif`` is always ``null``) and **no OAI-PMH**
  (``/oai-pmh`` → 404).
* The **content** — media lists, image URLs and the per-collection licence — is
  served by a JSON API, ``GET /visualizer/api``:

  - ``?arkName=<id>&group=<g>`` → ``{"counts": {"media": N, ...}, "media": [...]}``
  - ``?arkName=<id>&start=<s>&end=<e>&group=<g>`` → JSON array of Media
    (``end`` is **inclusive**, must be ≤ ``N-1``; otherwise HTTP 400).
  - ``?arkName=<id>&uuid=<mediaUuid>`` → media list + ``app`` (config + licence).

* Images are static and public: ``/images/<uuid>.jpg`` (original) and
  ``/images/<uuid>_thumbnail.jpg`` (thumbnail).

The **search** surface has no JSON twin: ``GET /search/results`` is rendered
server-side. This connector parses that page only to *discover* notices; every
image / licence access then goes through the programmatic ``/visualizer/api``,
so images themselves are never scraped (the project's "no HTML scraping for
images" rule is respected).

Licence (``app.licenses.visualizer``): **restrictive** — commercial reuse of the
digitised material requires a fee and a written licence (délibération of the
Conseil départemental du Nord, 27/03/2017). The descriptor is ``enabled: false``.

Normalization notes for the connector (media → :class:`Asset`):

* ``asset_id``            = ``media.uuid``
* ``title``               = ``record.title[0]``
* ``page_url``            = the notice page ``record.url``
  (``/ark:/33518/<arkName>``); the per-image viewer deep-link ``media.url``
  (``/ark:/33518/<arkName>/<uuid>``) is kept in ``extra.viewer_url``
* ``image_url``           = ``location.original`` (``/images/<uuid>.jpg``)
* ``thumbnail_url``       = ``location.thumb`` (``/images/<uuid>_thumbnail.jpg``)
* ``date_text`` / ``year``= ``record.period.boundaries[0]``
* ``tags``                = ``record.locationKeywords``
* ``extra.reference_code``= ``record.referenceCode[0]`` (the cote)
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.archives_nord")

#: one search result block, e.g. ``<li class="element-list">``
_ELEMENT_SPLIT = '<li class="element-list"'
#: notice-with-images link: ``/ark:/33518/<arkName>/<mediaUuid>``
_ARK_MEDIA_RE = re.compile(r"/ark:/33518/(?P<ark>[A-Za-z0-9._-]+)/(?P<uuid>[0-9a-fA-F-]{36})")
#: standalone PDF link: ``/media/<uuid>.pdf``
_PDF_RE = re.compile(r"/media/(?P<uuid>[0-9a-fA-F-]{36})\.pdf")
_HREF_RE = re.compile(r'href="(?P<href>[^"]+)"', re.IGNORECASE)
_TITLE_RE = re.compile(r"<h2[^>]*>(?P<title>.*?)</h2>", re.IGNORECASE | re.DOTALL)
_MEDIA_COUNT_RE = re.compile(r"(\d+)\s*(?:m[ée]dias?|images?)", re.IGNORECASE)
_PAGES_RE = re.compile(r"(\d+)\s*pages?", re.IGNORECASE)
_TOTAL_RE = re.compile(r"([\d\u00a0\u202f\s]+)\s*r[ée]sultats?", re.IGNORECASE)
_TAGS_RE = re.compile(r"<[^>]+>")

#: licence attached to every asset until the project's policy authorises reuse
_RESTRICTIVE_LICENSE = "Restrictive — AD Nord, délibération du 27/03/2017"

_DEFAULT_NAAN = 33518


def _strip_tags(text: str) -> str:
    return _TAGS_RE.sub("", text or "").strip()


class ArchivesNordConnector(Connector):
    """Search + media enumeration for the Archives départementales du Nord."""

    # -- endpoints ---------------------------------------------------------

    @property
    def _base(self) -> str:
        return self.descriptor.base_url.rstrip("/")

    @property
    def _search_url(self) -> str:
        return str(self.descriptor.extra.get("search_url") or f"{self._base}/search/results")

    @property
    def _api_url(self) -> str:
        return str(self.descriptor.extra.get("visualizer_api") or f"{self._base}/visualizer/api")

    def notice_url(self, ark_name: str) -> str:
        """The ``/ark:/33518/<arkName>`` notice page for a fonds item."""
        return f"{self._base}/ark:/33518/{ark_name}"

    def image_urls(self, uuid: str) -> dict[str, str]:
        """Static image URLs for a media uuid (this platform has no IIIF)."""
        original = str(
            self.descriptor.extra.get("image_url_template")
            or f"{self._base}/images/{{uuid}}.jpg"
        )
        thumb = str(
            self.descriptor.extra.get("thumbnail_url_template")
            or f"{self._base}/images/{{uuid}}_thumbnail.jpg"
        )
        return {"original": original.format(uuid=uuid), "thumbnail": thumb.format(uuid=uuid)}

    # -- search (server-rendered HTML discovery) ---------------------------

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        page = int(filters.get("page") or 1)
        per_page = int(filters.get("per_page") or limit or 20)
        params = {"q": query, "page": str(page), "resultsPerPage": str(per_page)}
        resp = await self.http.get(
            self._search_url,
            params=params,
            accept="text/html, application/xhtml+xml;q=0.9, */*;q=0.5",
        )
        hits, total = self.parse_search(resp.text)
        log.debug("archives_nord search %r: %d hits (total=%s)", query, len(hits), total)

        assets: list[Asset] = []
        for hit in hits:
            asset = self._hit_to_asset(hit)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def parse_search(self, html: str) -> tuple[list[dict[str, Any]], int | None]:
        """Split a ``/search/results`` page into notice hits and the result total."""
        hits: list[dict[str, Any]] = []
        for chunk in (html or "").split(_ELEMENT_SPLIT)[1:]:
            hit = self._parse_element(chunk)
            if hit is not None:
                hits.append(hit)
        return hits, self._parse_total(html)

    def _parse_element(self, chunk: str) -> dict[str, Any] | None:
        href_match = _HREF_RE.search(chunk)
        if not href_match:
            return None
        href = href_match.group("href")
        title_match = _TITLE_RE.search(chunk)
        title = _strip_tags(title_match.group("title")) if title_match else ""
        plain = _strip_tags(chunk)

        ark_match = _ARK_MEDIA_RE.search(href)
        if ark_match:
            count = _MEDIA_COUNT_RE.search(plain)
            return {
                "kind": "image",
                "href": href,
                "ark_name": ark_match.group("ark"),
                "uuid": ark_match.group("uuid"),
                "title": title,
                "media_count": int(count.group(1)) if count else None,
            }

        pdf_match = _PDF_RE.search(href)
        if pdf_match:
            pages = _PAGES_RE.search(plain)
            return {
                "kind": "pdf",
                "href": href,
                "uuid": pdf_match.group("uuid"),
                "title": title,
                "pages": int(pages.group(1)) if pages else None,
            }
        return None

    @staticmethod
    def _parse_total(html: str) -> int | None:
        match = _TOTAL_RE.search(html or "")
        if not match:
            return None
        digits = re.sub(r"\D", "", match.group(1))
        return int(digits) if digits else None

    def _hit_to_asset(self, hit: dict[str, Any]) -> Asset | None:
        uuid = hit.get("uuid")
        if not uuid:
            return None
        href = hit.get("href") or ""
        media_url = urljoin(f"{self._base}/", href) if href else None

        if hit.get("kind") == "image":
            urls = self.image_urls(uuid)
            ark_name = hit.get("ark_name")
            notice = self.notice_url(ark_name) if ark_name else None
            return Asset.build(
                self.id,
                uuid,
                title=hit.get("title") or "",
                license=_RESTRICTIVE_LICENSE,
                rights=self.descriptor.rights,
                page_url=notice or media_url,
                image_url=urls["original"],
                thumbnail_url=urls["thumbnail"],
                extra={
                    "kind": "image",
                    "ark_name": ark_name,
                    "naan": self.descriptor.extra.get("ark_naan", _DEFAULT_NAAN),
                    "notice_url": notice,
                    "viewer_url": media_url,
                    "media_count": hit.get("media_count"),
                    "discovery": "search",
                },
            )

        # standalone PDF: no raster image, but a search thumbnail exists
        return Asset.build(
            self.id,
            uuid,
            title=hit.get("title") or "",
            license=_RESTRICTIVE_LICENSE,
            rights=self.descriptor.rights,
            page_url=media_url,
            image_url=None,
            thumbnail_url=f"{self._base}/pdf-preview/{uuid}_search_result_thumbnail",
            extra={
                "kind": "pdf",
                "pages": hit.get("pages"),
                "viewer_url": media_url,
                "discovery": "search",
            },
        )

    # -- viewer JSON API ---------------------------------------------------

    async def group_page(self, ark_name: str, group: int = 0) -> dict[str, Any]:
        """Fetch the first page of a group (``counts`` + a page of ``media``)."""
        data = await self.http.get_json(
            self._api_url, params={"arkName": ark_name, "group": group}
        )
        return data if isinstance(data, dict) else {}

    async def record_media(
        self, ark_name: str, start: int, end: int, group: int = 0
    ) -> list[dict[str, Any]]:
        """Fetch a media range (``end`` inclusive, ≤ N-1)."""
        data = await self.http.get_json(
            self._api_url,
            params={"arkName": ark_name, "start": start, "end": end, "group": group},
        )
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict)]
        if isinstance(data, dict):
            return [m for m in (data.get("media") or []) if isinstance(m, dict)]
        return []

    async def all_media(
        self, ark_name: str, group: int = 0, page_size: int = 100
    ) -> list[dict[str, Any]]:
        """Enumerate every media of a notice, paging the viewer API.

        ``end`` is inclusive and clamped to ``counts.media - 1`` so we never
        trigger the API's HTTP 400 ("Invalid request...").
        """
        data = await self.group_page(ark_name, group)
        total = int((data.get("counts") or {}).get("media") or 0)
        media = [m for m in (data.get("media") or []) if isinstance(m, dict)]
        start = len(media)
        while start < total:
            end = min(start + page_size - 1, total - 1)
            batch = await self.record_media(ark_name, start=start, end=end, group=group)
            if not batch:
                break
            media.extend(batch)
            start = end + 1
        return media

    async def media_detail(self, ark_name: str, uuid: str) -> dict[str, Any]:
        """Single-media detail: media list + ``app`` (config + licence)."""
        data = await self.http.get_json(
            self._api_url, params={"arkName": ark_name, "uuid": uuid}
        )
        return data if isinstance(data, dict) else {}

    @staticmethod
    def detail_media(data: dict[str, Any], uuid: str) -> dict[str, Any] | None:
        for media in data.get("media") or []:
            if isinstance(media, dict) and media.get("uuid") == uuid:
                return media
        return None

    @staticmethod
    def visualizer_license(data: dict[str, Any]) -> dict[str, Any] | None:
        """The ``app.licenses.visualizer`` block (restrictive notice)."""
        app = data.get("app") or {}
        licenses = app.get("licenses") or {}
        return licenses.get("visualizer")

    # -- normalization -----------------------------------------------------

    def media_to_asset(self, media: dict[str, Any]) -> Asset | None:
        """Map one viewer ``Media`` onto the canonical :class:`Asset`."""
        uuid = media.get("uuid")
        if not uuid:
            return None
        record = media.get("record") or {}
        ark = record.get("arkId") or {}
        ark_name = ark.get("arkName")
        titles = record.get("title") or []
        codes = record.get("referenceCode") or []
        places = [str(p) for p in (record.get("locationKeywords") or [])]
        boundaries = (record.get("period") or {}).get("boundaries") or []
        location = media.get("location") or {}
        urls = self.image_urls(uuid)
        date_text = boundaries[0] if boundaries else None
        notice = record.get("url") or (self.notice_url(ark_name) if ark_name else None)

        return Asset.build(
            self.id,
            uuid,
            title=(titles[0] if titles else (media.get("title") or "")),
            description=record.get("description") or "",
            date_text=date_text,
            year=parse_year(date_text),
            license=_RESTRICTIVE_LICENSE,
            rights=self.descriptor.rights,
            page_url=notice,
            image_url=location.get("original") or urls["original"],
            thumbnail_url=location.get("thumb") or urls["thumbnail"],
            tags=places,
            extra={
                "ark_name": ark_name,
                "naan": ark.get("naan"),
                "notice_url": notice,
                "viewer_url": media.get("url"),
                "reference_code": codes[0] if codes else None,
                "boundaries": boundaries,
                "location_keywords": places,
                "type": media.get("type"),
                "format": media.get("format"),
            },
        )
