"""The Portal to Texas History (University of North Texas Libraries).

The Portal (https://texashistory.unt.edu) is UNT's statewide digital library,
strong in Texas oil-industry photography (Spindletop, the East Texas and Permian
Basin booms, press photographs, well fires). It keys every item to an ARK
(NAAN ``67531``) and exposes two programmatic paths:

* a IIIF Presentation **v2** manifest per item —
  ``https://texashistory.unt.edu/ark:/67531/{ark}/manifest/`` — with a IIIF
  Image API service on each canvas;
* an OAI-PMH endpoint, but **without keyword search**.

The public keyword search (``/search/?q=…``) is fronted by an ``Altcha``
proof-of-work anti-bot. The project policy forbids circumventing or
HTML-scraping such a gate without written consent, so this connector relies
exclusively on a curated ``seeds`` list of ARKs resolved through the
programmatic IIIF path — exactly like the ANMT connector.

The Portal is a still-image library: one ARK is one photograph/print, so each
seed yields a **single** record built from the item's first displayable canvas.
Item metadata lives in the IIIF v2 ``metadata`` array with dotted labels
(``title``, ``date``/``date.creation``, ``resourceType``, ``rights`` /
``rights.access`` / ``rights.license``); a ``related.@id`` points at the public
item page and ``thumbnail.@id`` at the provider thumbnail.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.sources.iiif_common import label as _label_text
from mnemosyne.util import parse_year

log = get_logger("sources.texas_history")

_DEFAULT_NAAN = "67531"
_DEFAULT_IMAGE_SIZE = "!1200,1200"
_DEFAULT_THUMB_SIZE = "!400,400"


def _canvases(manifest: dict) -> list[dict]:
    """Return the manifest's canvases (IIIF v2 ``sequences`` or v3 ``items``)."""
    for seq in manifest.get("sequences", []) or []:
        if isinstance(seq, dict) and isinstance(seq.get("canvases"), list):
            return [c for c in seq["canvases"] if isinstance(c, dict)]
    items = manifest.get("items")
    if isinstance(items, list):
        return [c for c in items if isinstance(c, dict)]
    return []


def _canvas_image(canvas: dict) -> str | None:
    """IIIF Image API service id for a canvas (``resource.service.@id``)."""
    for image in canvas.get("images", []) or []:
        if not isinstance(image, dict):
            continue
        resource = image.get("resource")
        if not isinstance(resource, dict):
            continue
        service = resource.get("service")
        if isinstance(service, list) and service:
            service = service[0]
        if isinstance(service, dict):
            sid = service.get("@id") or service.get("id")
            if sid:
                return str(sid)
        image_id = resource.get("@id") or resource.get("id")
        if image_id:
            # no service advertised: derive the base from the image URL
            return str(image_id).split("/full/")[0]
    return None


def _metadata_values(manifest: dict, *names: str) -> list[str]:
    """All non-empty metadata values whose label matches one of `names`."""
    wanted = {name.lower() for name in names}
    out: list[str] = []
    for entry in manifest.get("metadata", []) or []:
        if not isinstance(entry, dict):
            continue
        if _label_text(entry.get("label")).lower() not in wanted:
            continue
        text = _label_text(entry.get("value"))
        if text:
            out.append(text)
    return out


def _first_metadata(manifest: dict, *names: str) -> str | None:
    """First non-empty metadata value whose label matches one of `names`."""
    values = _metadata_values(manifest, *names)
    return values[0] if values else None


def _is_restricted(manifest: dict) -> bool:
    """An item is not displayable when ``rights.access`` says ``restricted``."""
    for value in _metadata_values(
        manifest, "rights.access", "rights.access.status", "access"
    ):
        if "restrict" in value.lower():
            return True
    return False


def _license_label(manifest: dict, default: str | None) -> str | None:
    """Prefer an explicit ``rights.license`` value, else the descriptor licence."""
    explicit = _first_metadata(manifest, "rights.license", "license", "rights.uri")
    return explicit or default


def _related_url(manifest: dict) -> str | None:
    related = manifest.get("related")
    if isinstance(related, list) and related:
        related = related[0]
    if isinstance(related, dict):
        return related.get("@id") or related.get("id")
    if isinstance(related, str):
        return related
    return None


def _thumbnail_url(manifest: dict) -> str | None:
    thumb = manifest.get("thumbnail")
    if isinstance(thumb, list) and thumb:
        thumb = thumb[0]
    if isinstance(thumb, dict):
        return thumb.get("@id") or thumb.get("id")
    if isinstance(thumb, str):
        return thumb
    return None


def _image_url(service: str, size: str) -> str:
    return f"{service}/full/{size}/0/default.jpg"


class TexasHistoryConnector(Connector):
    """Seeds-only IIIF connector for The Portal to Texas History (UNT)."""

    # -- URL templates (driven by ``extra``) -------------------------------

    def _naan(self) -> str:
        return str((self.descriptor.extra or {}).get("ark_naan") or _DEFAULT_NAAN)

    def _manifest_url(self, ark: str) -> str:
        template = (self.descriptor.extra or {}).get("manifest_pattern")
        if template:
            return str(template).format(ark=ark)
        return f"{self.descriptor.base_url.rstrip('/')}/ark:/{self._naan()}/{ark}/manifest/"

    def _notice_url(self, ark: str) -> str:
        template = (self.descriptor.extra or {}).get("notice_pattern")
        if template:
            return str(template).format(ark=ark)
        return f"{self.descriptor.base_url.rstrip('/')}/ark:/{self._naan()}/{ark}/"

    def _attribution(self) -> str:
        extra = self.descriptor.extra or {}
        return str(
            extra.get("attribution")
            or self.descriptor.institution
            or self.descriptor.name
        )

    # -- fetching ----------------------------------------------------------

    async def _fetch_manifest(self, ark: str) -> dict | None:
        url = self._manifest_url(ark)
        try:
            data = await self.http.get_json(url, headers={"Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001
            log.debug("texas_history manifest %s failed: %s", url, exc)
            return None
        return data if isinstance(data, dict) else None

    # -- normalization -----------------------------------------------------

    def _record_from_manifest(self, manifest: dict, ark: str) -> Asset | None:
        service: str | None = None
        canvas: dict | None = None
        for candidate in _canvases(manifest):
            sid = _canvas_image(candidate)
            if sid:
                service, canvas = sid, candidate
                break
        if service is None or canvas is None:
            return None

        extra = self.descriptor.extra or {}
        image_size = str(extra.get("image_size") or _DEFAULT_IMAGE_SIZE)
        thumb_size = str(extra.get("thumbnail_size") or _DEFAULT_THUMB_SIZE)
        attribution = self._attribution()

        title = (
            _first_metadata(manifest, "title")
            or _label_text(manifest.get("label"))
            or "Sans titre"
        )
        date_text = _first_metadata(
            manifest, "date.creation", "date", "creation date", "date of creation"
        )
        year = parse_year(date_text)
        resource_type = _first_metadata(manifest, "resourceType", "resource.type")
        rights = _first_metadata(manifest, "rights") or attribution
        license_label = _license_label(manifest, self.descriptor.license)

        manifest_url = self._manifest_url(ark)
        notice_url = self._notice_url(ark)
        page_url = _related_url(manifest) or notice_url
        thumbnail = _thumbnail_url(manifest) or _image_url(service, thumb_size)

        return Asset.build(
            self.id,
            ark,
            title=title,
            description=_first_metadata(manifest, "description") or _label_text(
                canvas.get("label")
            ),
            date_text=date_text,
            year=year,
            license=license_label,
            rights=rights,
            page_url=page_url,
            image_url=_image_url(service, image_size),
            thumbnail_url=thumbnail,
            iiif_id=service,
            width=canvas.get("width"),
            height=canvas.get("height"),
            tags=[t for t in (resource_type,) if t],
            extra={
                "ark": ark,
                "manifest": manifest_url,
                "notice": notice_url,
                "attribution": attribution,
                "resource_type": resource_type,
            },
        )

    # -- Connector API -----------------------------------------------------

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        # The keyword search is Altcha-gated (no circumvention / no scraping):
        # the curated seeds are fetched through the programmatic IIIF manifests.
        assets: list[Asset] = []
        seen: set[str] = set()
        for ark in self.descriptor.seeds:
            if ark in seen:
                continue
            seen.add(ark)
            manifest = await self._fetch_manifest(ark)
            if manifest is None or _is_restricted(manifest):
                continue
            asset = self._record_from_manifest(manifest, ark)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets[:limit]
