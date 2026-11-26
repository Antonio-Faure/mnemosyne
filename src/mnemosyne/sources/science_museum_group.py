"""Science Museum Group Collection (UK) — object search + IIIF manifests.

The Science Museum Group publishes its collection — including the Daily Herald
photographic archive — on two open, programmatic endpoints, both used here
instead of scraping:

* ``GET /search?q=...`` — a JSON:API document
  (``{"data": [{"type": "objects", "id": "co6908", ...}, ...]}``) returned
  **only** when the request carries ``Accept: application/json`` (the default
  ``HttpClient.get_json`` sends it; a browser receives HTML instead).
* ``GET /iiif/objects/{id}`` — a IIIF Presentation v2 manifest (pure JSON) with
  the full-resolution image, thumbnail, canvas dimensions, ``attribution`` and
  an identifier for the object.

The search yields ids; each id is then enriched from its manifest so the asset
carries a real, high-resolution image. Raw provider shapes never leave this
boundary.
"""

from __future__ import annotations

from typing import Any

import httpx

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.science_museum_group")

_DATE_LABELS = ("date", "production date", "date made", "made", "period")
_MAKER_LABELS = ("maker", "makers", "creator", "photographer", "artist", "author")
_ID_LABELS = ("identifier", "object number", "inventory number", "accession")
_DATE_ATTRS = ("date", "date_made", "production_date", "made", "year")
_CREATOR_ATTRS = ("maker", "makers", "creator", "author")


def _text(value: Any) -> str | None:
    """Coerce a IIIF/JSON:API value (str, language-map dict, list) to text."""
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        # IIIF objects use {"@id": ...} and {"@language": "en", "@value": "..."}
        for key in ("@value", "value", "en", "label", "@id"):
            text = _text(value.get(key))
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _meta(metadata: Any, labels: tuple[str, ...]) -> str | None:
    """Value of the first manifest ``metadata`` entry whose label matches."""
    if not isinstance(metadata, list):
        return None
    wanted = {label.lower() for label in labels}
    for entry in metadata:
        if not isinstance(entry, dict):
            continue
        label = _text(entry.get("label"))
        if label and label.lower() in wanted:
            return _text(entry.get("value"))
    return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _canvas_image(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return ``(canvas, resource)`` for the first usable image of a manifest."""
    sequences = manifest.get("sequences")
    if not isinstance(sequences, list):
        return None
    for sequence in sequences:
        if not isinstance(sequence, dict):
            continue
        canvases = sequence.get("canvases")
        if not isinstance(canvases, list):
            continue
        for canvas in canvases:
            if not isinstance(canvas, dict):
                continue
            images = canvas.get("images")
            if not isinstance(images, list):
                continue
            for image in images:
                if not isinstance(image, dict):
                    continue
                resource = image.get("resource")
                if isinstance(resource, dict) and _text(resource.get("@id")):
                    return canvas, resource
    return None


def _service_id(resource: dict[str, Any]) -> str | None:
    service = resource.get("service")
    if isinstance(service, dict):
        return _text(service.get("@id"))
    if isinstance(service, list):
        for item in service:
            if isinstance(item, dict):
                text = _text(item.get("@id"))
                if text:
                    return text
    return None


class ScienceMuseumGroupConnector(Connector):
    """Search the SMG collection and enrich each hit from its IIIF manifest."""

    def _search_url(self) -> str:
        path = self.descriptor.extra.get("search_path", "/search")
        return self.descriptor.base_url.rstrip("/") + str(path)

    def _manifest_url(self, object_id: str) -> str:
        path = str(self.descriptor.extra.get("manifest_path", "/iiif/objects/{id}"))
        return self.descriptor.base_url.rstrip("/") + path.format(id=object_id)

    def _page_url(self, object_id: str) -> str:
        path = str(self.descriptor.extra.get("object_page", "/objects/{id}"))
        return self.descriptor.base_url.rstrip("/") + path.format(id=object_id)

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0:
            return []
        data = await self.http.get_json(self._search_url(), params={"q": query})
        candidates = self._candidate_ids(data)

        assets: list[Asset] = []
        remaining = limit * 2  # allow for hits without a usable image
        for object_id, attrs in candidates:
            if len(assets) >= limit or remaining <= 0:
                break
            remaining -= 1
            try:
                manifest = await self.http.get_json(self._manifest_url(object_id))
            except (httpx.HTTPError, ValueError):
                # a single broken/missing manifest must not abort the search
                log.warning("smg: manifest unavailable for %s", object_id)
                continue
            if not isinstance(manifest, dict):
                continue
            asset = self._to_asset(object_id, manifest, attrs)
            if asset is not None:
                assets.append(asset)
        return assets[:limit]

    def _candidate_ids(self, data: Any) -> list[tuple[str, dict[str, Any]]]:
        """Extract ``(id, attributes)`` pairs for object records from a search."""
        records = data.get("data") if isinstance(data, dict) else data
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list):
            return []
        out: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            rtype = record.get("type")
            if rtype is not None and rtype != "objects":
                continue
            object_id = _text(record.get("id"))
            if not object_id or object_id in seen:
                continue
            seen.add(object_id)
            attrs = record.get("attributes")
            out.append((object_id, attrs if isinstance(attrs, dict) else {}))
        return out

    def _to_asset(
        self,
        object_id: str,
        manifest: dict[str, Any],
        attrs: dict[str, Any],
    ) -> Asset | None:
        found = _canvas_image(manifest)
        if found is None:
            return None
        canvas, resource = found
        image_url = _text(resource.get("@id"))
        if not image_url:
            return None

        service = _service_id(resource)
        metadata = manifest.get("metadata")

        thumbnail = _text(manifest.get("thumbnail"))
        if not thumbnail and service:
            thumbnail = f"{service}/full/400,/0/default.jpg"

        title = (
            _text(manifest.get("label"))
            or _text(attrs.get("summary_title"))
            or _text(attrs.get("title"))
            or object_id
        )
        description = (
            _text(manifest.get("description"))
            or _text(attrs.get("description"))
            or ""
        )
        date_text = _meta(metadata, _DATE_LABELS) or self._attr(attrs, _DATE_ATTRS)
        creator = _meta(metadata, _MAKER_LABELS) or self._attr(attrs, _CREATOR_ATTRS)
        attribution = _text(manifest.get("attribution"))

        return Asset.build(
            self.id,
            object_id,
            title=title,
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=self.descriptor.license,
            rights=attribution or self.descriptor.rights,
            page_url=self._page_url(object_id),
            image_url=image_url,
            thumbnail_url=thumbnail,
            iiif_id=service,
            width=_int(canvas.get("width")) or _int(resource.get("width")),
            height=_int(canvas.get("height")) or _int(resource.get("height")),
            extra={
                "accession": _meta(metadata, _ID_LABELS),
                "attribution": attribution,
            },
        )

    @staticmethod
    def _attr(attrs: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            text = _text(attrs.get(key))
            if text:
                return text
        return None
