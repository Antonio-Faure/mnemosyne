"""ESSO France oil imagery on the Internet Archive — discovery + IIIF.

The Institut français du pétrole (IFPEN) itself exposes **no** public photo
archive (see ``config/sources/ifpen_petrole.yaml``), so the French petroleum
imagery the adversarial resolver needs is sourced from the openly-addressable
**ESSO France** corpus on the Internet Archive: 31 issues of ``ESSO REVUE``
(1950-1952) plus ``Histoire de Parentis`` (1955) and ``Le pétrole des Landes``
(1957) — vintage scans of French oil exploration and exploitation
(Parentis-en-Born, the Landes, Lacq, drilling rigs/derricks, flares). This is
ESSO corporate material, **not** IFPEN; the labelling reflects that honestly.

Access is fully programmatic (no HTML scraping): items are discovered through
the Internet Archive advanced-search JSON API, and each item's page image is
read from its IIIF Presentation v3 manifest (served by the IIIF Image API v3).
The items carry no ``rights``/``licenseurl`` — rights are unknown, so the
descriptor is link/reference only and nothing is re-hosted.

Reuse: :class:`IIIFConnector` for the manifest -> :class:`Asset` normalization,
and override only discovery plus the bounded image sizes (the generic connector
would request ``/full/max``, which is slow and heavy on the Internet Archive).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from mnemosyne.models import Asset
from mnemosyne.sources.iiif import IIIFConnector
from mnemosyne.util import parse_year

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

_DETAILS = "https://archive.org/details/{identifier}"
_DEFAULT_MANIFEST = "https://iiif.archive.org/iiif/{identifier}/manifest.json"
_FALLBACK_IMAGE = "https://archive.org/services/img/{identifier}"


def _fold(text: Any) -> str:
    """Lower-case and strip diacritics so queries match regardless of accents."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def _first(value: Any) -> str:
    """Internet Archive fields are sometimes lists — take the first scalar."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value) if value else ""


class IaEssoPetroleConnector(IIIFConnector):
    """Discovers the ESSO France corpus on the Internet Archive, then IIIF."""

    async def search(
        self, query: str, limit: int = 20, **filters: Any
    ) -> list[Asset]:
        if limit <= 0:
            return []
        docs = await self._discover(query)
        assets: list[Asset] = []
        for doc in docs:
            if len(assets) >= limit:
                break
            asset = await self._doc_asset(doc)
            if asset is not None:
                assets.append(asset)
        return assets

    async def _discover(self, query: str) -> list[dict[str, Any]]:
        extra = self.descriptor.extra or {}
        params = {
            "q": str(extra.get("search_query") or ""),
            "fl[]": ["identifier", "title", "description", "date"],
            "rows": str(int(extra.get("rows", 80))),
            "page": "1",
            "output": "json",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        response = data.get("response") if isinstance(data, dict) else None
        docs = (response or {}).get("docs") or []
        docs = [d for d in docs if isinstance(d, dict) and d.get("identifier")]
        tokens = self._tokens(query)
        if tokens:
            # stable sort: most relevant items first, corpus order kept on ties
            docs.sort(key=lambda d: -self._score(d, tokens))
        return docs

    async def _doc_asset(self, doc: dict[str, Any]) -> Asset | None:
        identifier = str(doc["identifier"])
        details_url = _DETAILS.format(identifier=identifier)
        manifest_url = self._manifest_url(identifier)
        title = _first(doc.get("title")) or identifier
        description = _first(doc.get("description"))
        date_text = _first(doc.get("date")) or None
        year = parse_year(date_text)

        parsed = await self._manifest_to_asset(manifest_url)
        if parsed is not None:
            service = parsed.iiif_id
            if service:
                image_url = f"{service}/full/!400,400/0/default.jpg"
                thumbnail_url = f"{service}/full/!200,200/0/default.jpg"
            else:
                image_url = parsed.image_url
                thumbnail_url = parsed.thumbnail_url or parsed.image_url
            return Asset.build(
                self.id,
                identifier,
                title=title,
                description=description or parsed.description,
                creator=parsed.creator,
                date_text=date_text or parsed.date_text,
                year=year or parsed.year,
                license=parsed.license,
                rights=parsed.rights,
                page_url=details_url,
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                iiif_id=service,
                extra={
                    "ia_identifier": identifier,
                    "details_url": details_url,
                    "iiif_manifest": manifest_url,
                },
            )
        # Manifest unreachable: still surface the item with the IA thumbnail.
        return Asset.build(
            self.id,
            identifier,
            title=title,
            description=description,
            date_text=date_text,
            year=year,
            license=self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=details_url,
            image_url=_FALLBACK_IMAGE.format(identifier=identifier),
            thumbnail_url=_FALLBACK_IMAGE.format(identifier=identifier),
            extra={"ia_identifier": identifier, "details_url": details_url},
        )

    def _manifest_url(self, identifier: str) -> str:
        template = str(
            (self.descriptor.extra or {}).get("manifest_template") or _DEFAULT_MANIFEST
        )
        return template.format(identifier=identifier)

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return [t for t in _TOKEN_RE.findall(_fold(query)) if len(t) > 2]

    @staticmethod
    def _score(doc: dict[str, Any], tokens: list[str]) -> int:
        haystack = _fold(
            " ".join(_first(doc.get(k)) for k in ("title", "description"))
        )
        return sum(1 for token in tokens if token in haystack)
