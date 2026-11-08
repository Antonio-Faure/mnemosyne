"""The Portal to Texas History (UNT Libraries) — https://texashistory.unt.edu/.

The Portal aggregates digitised Texas archival material: newspapers, books,
maps and — the reason this source was requested — the photographic holdings of
oil-industry partners such as the **Permian Basin Petroleum Museum** (Odessa).
Its keyword search UI is fronted by an **Altcha** proof-of-work anti-bot (a
"DAM" challenge served even for ``format=json``); the project policy forbids
circumventing bot protection / HTML-scraping when a programmatic path exists,
and the keyless OAI-PMH endpoint, although open, offers **no keyword search**.
This connector therefore relies on a curated ``seeds`` list of ARKs resolved
through the programmatic IIIF path, exactly like the ANMT connector.

Programmatic path (verified live):

* OAI-PMH at ``/oai/`` (keyless, ungated) — used for discovery/metadata;
* one IIIF Presentation **v2** manifest per ARK:
  ``https://texashistory.unt.edu/ark:/67531/{ark}/manifest/``;
* descriptive metadata is a list of ``{label, value}`` with dotted labels
  (``title``, ``creator``, ``date.creation``, ``description.content``,
  ``subject.UNTL-BS``, ``subject.LCSH``, ``subject.KWD``, ``rights``,
  ``rights.access``, ``rights.license``, ``resourceType``, ``collection``,
  ``institution``);
* the image ``resource`` under ``sequences[].canvases[].images[]`` carries the
  full image ``@id`` and a IIIF Image API **v2 level2** ``service`` whose
  ``@id`` is ``https://texashistory.unt.edu/iiif/ark:/67531/{ark}/m1/1`` (level2
  advertises ``sizeByConfinedWh``), so ``<service>/full/{size}/0/default.jpg``
  is valid for any size strategy;
* a per-item ``thumbnail`` (``.../thumbnail/``) is provided on the manifest.

The connector emits **one** :class:`Asset` per item (the first displayable
canvas), which suits the single-image photographs that dominate oil-industry
holdings; multi-page documents (books, newspapers) therefore contribute their
primary image only.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.sources.iiif_common import label as _label
from mnemosyne.util import parse_year

log = get_logger("sources.texas_history")

_DEFAULT_NAAN = "67531"
_DEFAULT_IMAGE_SIZE = "!1200,1200"
_DEFAULT_THUMB_SIZE = "!400,400"

#: Portal ``rights.license`` / ``rights`` codes → human-readable licence.
_LICENSE_MAP: dict[str, str] = {
    "pd": "Public Domain",
    "public domain": "Public Domain",
    "by": "CC BY (Attribution)",
    "by-sa": "CC BY-SA (Attribution ShareAlike)",
    "by-nd": "CC BY-ND (Attribution NoDerivatives)",
    "by-nc": "CC BY-NC (Attribution Non-commercial)",
    "by-nc-sa": "CC BY-NC-SA (Attribution Non-commercial ShareAlike)",
    "by-nc-nd": "CC BY-NC-ND (Attribution Non-commercial NoDerivatives)",
}


def _metadata_values(manifest: dict, *names: str, prefix: bool = False) -> list[str]:
    """All metadata values whose label matches one of ``names``.

    With ``prefix=True`` a dotted label matches when it *starts with* a wanted
    name (so ``subject`` collects ``subject.UNTL-BS`` / ``subject.LCSH`` /
    ``subject.KWD``).
    """
    wanted = [name.lower() for name in names]
    out: list[str] = []
    for entry in manifest.get("metadata", []) or []:
        if not isinstance(entry, dict):
            continue
        current = _label(entry.get("label")).lower()
        if not current:
            continue
        if any(current == name or (prefix and current.startswith(name)) for name in wanted):
            value = _label(entry.get("value"))
            if value:
                out.append(value)
    return out


def _first_metadata(manifest: dict, *names: str, prefix: bool = False) -> str | None:
    values = _metadata_values(manifest, *names, prefix=prefix)
    return values[0] if values else None


def _license_label(code: str | None) -> str | None:
    if not code:
        return None
    cleaned = code.strip()
    return _LICENSE_MAP.get(cleaned.lower(), cleaned or None)


def _canvases(manifest: dict) -> list[dict]:
    """Return the manifest's canvases (IIIF v2 ``sequences`` or v3 ``items``)."""
    for seq in manifest.get("sequences", []) or []:
        if isinstance(seq, dict) and isinstance(seq.get("canvases"), list):
            return [c for c in seq["canvases"] if isinstance(c, dict)]
    items = manifest.get("items")
    if isinstance(items, list):
        return [c for c in items if isinstance(c, dict)]
    return []


def _canvas_image(canvas: dict) -> tuple[str | None, str | None]:
    """Return ``(service_id, resource_id)`` for a canvas' first image.

    ``service_id`` is the IIIF Image API base; when no service is advertised it
    is derived from the resource URL (everything before ``/full/``).
    """
    for image in canvas.get("images", []) or []:
        if not isinstance(image, dict):
            continue
        resource = image.get("resource")
        if not isinstance(resource, dict):
            continue
        service = resource.get("service")
        if isinstance(service, list) and service:
            service = service[0]
        service_id: str | None = None
        if isinstance(service, dict):
            sid = service.get("@id") or service.get("id")
            if sid:
                service_id = str(sid)
        resource_id = resource.get("@id") or resource.get("id")
        resource_id = str(resource_id) if resource_id else None
        if service_id:
            return service_id, resource_id
        if resource_id:
            return resource_id.split("/full/")[0], resource_id
    return None, None


def _image_url(service: str, size: str) -> str:
    return f"{service}/full/{size}/0/default.jpg"


class TexasHistoryConnector(Connector):
    """The Portal to Texas History (UNT Libraries) connector — IIIF seeds only."""

    # -- URL templates (driven by ``extra``) ------------------------------

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

    def _attribution(self, manifest: dict) -> str:
        extra = self.descriptor.extra or {}
        return str(
            extra.get("attribution")
            or manifest.get("attribution")
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
        canvases = _canvases(manifest)
        service: str | None = None
        resource_id: str | None = None
        width: int | None = None
        height: int | None = None
        for canvas in canvases:
            service, resource_id = _canvas_image(canvas)
            if service or resource_id:
                width = canvas.get("width")
                height = canvas.get("height")
                break
        if not (service or resource_id):
            return None

        extra = self.descriptor.extra or {}
        image_size = str(extra.get("image_size") or _DEFAULT_IMAGE_SIZE)
        thumb_size = str(extra.get("thumbnail_size") or _DEFAULT_THUMB_SIZE)

        # Access control + licence (dotted UNTL metadata).
        access = (_first_metadata(manifest, "rights.access") or "").lower()
        if access == "restricted":
            return None
        rights_code = _first_metadata(manifest, "rights.license") or _first_metadata(
            manifest, "rights"
        )
        license_label = _license_label(rights_code) or self.descriptor.license

        # Descriptive fields.
        title = (
            _label(manifest.get("label"))
            or _first_metadata(manifest, "title", prefix=True)
            or "Sans titre"
        )
        creator = _first_metadata(manifest, "creator") or _first_metadata(manifest, "publisher")
        date_text = (
            _first_metadata(manifest, "date.creation")
            or _first_metadata(manifest, "date")
            or _first_metadata(manifest, "coverage.date")
        )
        description = _label(manifest.get("description")) or _first_metadata(
            manifest, "description.content"
        )
        subjects = _metadata_values(manifest, "subject", prefix=True)
        collection = _first_metadata(manifest, "collection")
        institution = _first_metadata(manifest, "institution")
        resource_type = _first_metadata(manifest, "resourceType")

        # Image / thumbnail URLs.
        if service:
            image_url = _image_url(service, image_size)
            thumb_url = _image_url(service, thumb_size)
        else:  # pragma: no cover - service is normally advertised
            image_url = resource_id
            thumb_url = None
        thumb = manifest.get("thumbnail")
        if isinstance(thumb, dict) and thumb.get("@id"):
            thumb_url = str(thumb["@id"])
        elif isinstance(thumb, str):
            thumb_url = thumb

        related = manifest.get("related")
        related_id = related.get("@id") if isinstance(related, dict) else None
        page_url = related_id or self._notice_url(ark)
        attribution = self._attribution(manifest)

        return Asset.build(
            self.id,
            ark,
            title=title,
            description=description or "",
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=license_label,
            rights=attribution,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=thumb_url,
            iiif_id=service or resource_id,
            width=width,
            height=height,
            tags=subjects,
            extra={
                "ark": ark,
                "manifest": self._manifest_url(ark),
                "collection": collection,
                "institution": institution,
                "resource_type": resource_type,
                "rights_code": rights_code,
                "access": access or None,
                "attribution": attribution,
            },
        )

    # -- Connector API -----------------------------------------------------

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        # No HTML/keyword search (Altcha-gated, off-policy to bypass): the
        # curated seeds are resolved through the programmatic IIIF manifests.
        assets: list[Asset] = []
        seen: set[str] = set()
        for ark in list(self.descriptor.seeds):
            if ark in seen:
                continue
            seen.add(ark)
            manifest = await self._fetch_manifest(ark)
            if manifest is None:
                continue
            record = self._record_from_manifest(manifest, ark)
            if record is not None:
                assets.append(record)
            if len(assets) >= limit:
                break
        return assets[:limit]
