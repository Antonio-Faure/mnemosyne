"""Archives nationales du monde du travail (ANMT, Roubaix).

The ANMT online search (https://recherche-anmt.culture.gouv.fr) runs on the
Ligeo-Archives / Boscop platform (Monocle viewer, ARK NAAN 60879). There is no
documented search API, and the HTML search is fronted by an intermittent
"Anubis" proof-of-work anti-bot, so this connector relies primarily on a curated
``seeds`` list of ARKs and only opportunistically discovers more through the
HTML search, degrading back to the seeds when the anti-bot challenges us.

Programmatic path (verified by the browser agent):

* one IIIF Presentation **v2** manifest per ARK lists *all* of its digitised
  canvases (1..250+);
* each canvas carries a IIIF Image API **v3** service id, and the image is
  fetched from ``<service>/full/max/0/default.jpg`` (thumbnail
  ``<service>/full/!200,200/0/default.jpg``);
* canvases flagged ``ligeoRestrictedAccess: true`` ("document numérisé non
  affichable") are skipped; a manifest whose canvases are *all* restricted
  yields no record;
* the reuse terms live in ``manifest.ligeoReUseProfil.content`` (HTML).

The implementation is generic to the Ligeo-Archives/Boscop CMS: base URL, ARK
NAAN and the URL templates are read from the descriptor's ``extra``, so the same
connector can serve other French archives built on this platform.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.anmt")

_DEFAULT_NAAN = "60879"
_DEFAULT_IMAGE_SIZE = "max"
_DEFAULT_THUMB_SIZE = "!200,200"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html or "")).strip()


def _label(value: Any) -> str:
    """IIIF labels: str | lang->str | lang->[str] | {"@value": ...} | list."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return _label(value[0]) if value else ""
    if isinstance(value, dict):
        if "@value" in value:
            return _label(value["@value"])
        for key in ("fr", "en", "none"):
            if key in value:
                text = _label(value[key])
                if text:
                    return text
        for v in value.values():
            text = _label(v)
            if text:
                return text
    return ""


def _metadata(manifest: dict, *names: str) -> str | None:
    wanted = {n.lower() for n in names}
    for entry in manifest.get("metadata", []) or []:
        if not isinstance(entry, dict):
            continue
        if _label(entry.get("label")).lower() in wanted:
            text = _label(entry.get("value"))
            if text:
                return text
    return None


def _canvases(manifest: dict) -> list[dict]:
    """Return the manifest's canvases (IIIF v2 ``sequences`` or v3 ``items``)."""
    for seq in manifest.get("sequences", []) or []:
        if isinstance(seq, dict) and isinstance(seq.get("canvases"), list):
            return [c for c in seq["canvases"] if isinstance(c, dict)]
    items = manifest.get("items")
    if isinstance(items, list):
        return [c for c in items if isinstance(c, dict)]
    return []


def _is_restricted(canvas: dict) -> bool:
    """A canvas is not displayable when flagged ``ligeoRestrictedAccess``."""
    if canvas.get("ligeoRestrictedAccess") is True:
        return True
    for image in canvas.get("images", []) or []:
        if not isinstance(image, dict):
            continue
        if image.get("ligeoRestrictedAccess") is True:
            return True
        resource = image.get("resource")
        if isinstance(resource, dict) and resource.get("ligeoRestrictedAccess") is True:
            return True
    return False


def _service_id(canvas: dict) -> str | None:
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


def _reuse_content(manifest: dict) -> str:
    profile = manifest.get("ligeoReUseProfil")
    if isinstance(profile, dict):
        content = profile.get("content")
        if isinstance(content, str):
            return content
    if isinstance(profile, str):
        return profile
    return ""


def _license_from_reuse(content: str) -> str | None:
    """Derive a licence label from the ``ligeoReUseProfil`` HTML, if any."""
    text = _strip_html(content).lower()
    if not text:
        return None
    if not any(k in text for k in ("réutilis", "reutilis", "reuse", "libre")):
        return None
    # detect a strictly non-commercial grant
    stripped = text.replace("non commercial", "").replace("non-commercial", "")
    if "commercial" not in stripped:
        return "Réutilisation libre (non commerciale)"
    return "Réutilisation libre (commerciale et non commerciale)"


def _extract_arks(html: str, naan: str) -> list[str]:
    pattern = re.compile(r"/ark:/" + re.escape(naan) + r"/([0-9A-Za-z._\-]+)")
    arks: list[str] = []
    for match in pattern.finditer(html or ""):
        ark = match.group(1)
        if ark not in arks:
            arks.append(ark)
    return arks


def _is_anubis(html: str) -> bool:
    """Detect the "Anubis" proof-of-work anti-bot challenge page."""
    head = (html or "")[:8000].lower()
    return "anubis" in head or "proof of work" in head or "proof-of-work" in head


def _image_url(service: str, size: str) -> str:
    return f"{service}/full/{size}/0/default.jpg"


class AnmtConnector(Connector):
    """Generic Ligeo-Archives/Boscop IIIF connector (ANMT Roubaix)."""

    # -- URL templates (generic, driven by ``extra``) ----------------------

    def _naan(self) -> str:
        return str((self.descriptor.extra or {}).get("ark_naan") or _DEFAULT_NAAN)

    def _manifest_url(self, ark: str) -> str:
        template = (self.descriptor.extra or {}).get("manifest_pattern")
        if template:
            return str(template).format(ark=ark)
        return f"{self.descriptor.base_url.rstrip('/')}/ark:/{self._naan()}/{ark}/manifest"

    def _notice_url(self, ark: str) -> str:
        template = (self.descriptor.extra or {}).get("notice_pattern")
        if template:
            return str(template).format(ark=ark)
        return f"{self.descriptor.base_url.rstrip('/')}/ark:/{self._naan()}/{ark}"

    def _viewer_url(self, ark: str) -> str:
        template = (self.descriptor.extra or {}).get("viewer_pattern")
        if template:
            return str(template).format(ark=ark)
        return f"{self.descriptor.base_url.rstrip('/')}/ark:/{self._naan()}/{ark}/daogrp/0"

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
            log.debug("anmt manifest %s failed: %s", url, exc)
            return None
        return data if isinstance(data, dict) else None

    async def _discover_arks(self, query: str) -> list[str] | None:
        """ARKs from the HTML search, or ``None`` when blocked by the anti-bot."""
        template = (self.descriptor.extra or {}).get("search_url")
        if not template:
            return None
        url = str(template).format(query=quote(query))
        try:
            resp = await self.http.get(url, accept="text/html, */*;q=0.5")
        except Exception as exc:  # noqa: BLE001
            log.debug("anmt search %s failed: %s", url, exc)
            return None
        if _is_anubis(resp.text):
            log.info("anmt search challenged by Anubis; falling back to seeds")
            return None
        return _extract_arks(resp.text, self._naan())

    # -- normalization -----------------------------------------------------

    def _records_from_manifest(self, manifest: dict, ark: str) -> list[Asset]:
        canvases = _canvases(manifest)
        if not canvases:
            return []

        extra = self.descriptor.extra or {}
        image_size = str(extra.get("image_size") or _DEFAULT_IMAGE_SIZE)
        thumb_size = str(extra.get("thumbnail_size") or _DEFAULT_THUMB_SIZE)
        attribution = self._attribution()

        reuse_content = _reuse_content(manifest)
        license_label = _license_from_reuse(reuse_content) or self.descriptor.license
        reuse_text = _strip_html(reuse_content)[:1200]

        fonds_title = _label(manifest.get("label"))
        date_text = _metadata(
            manifest, "date", "datation", "période", "periode", "date de création"
        )
        year = parse_year(date_text)
        manifest_url = self._manifest_url(ark)
        notice_url = self._notice_url(ark)
        viewer_url = self._viewer_url(ark)

        records: list[Asset] = []
        for index, canvas in enumerate(canvases):
            if _is_restricted(canvas):
                continue
            service = _service_id(canvas)
            if not service:
                continue
            page_label = _label(canvas.get("label"))
            records.append(
                Asset.build(
                    self.id,
                    f"{ark}#{index}",
                    title=fonds_title or page_label or "Sans titre",
                    description=page_label,
                    date_text=date_text,
                    year=year,
                    license=license_label,
                    rights=attribution,
                    page_url=viewer_url,
                    image_url=_image_url(service, image_size),
                    thumbnail_url=_image_url(service, thumb_size),
                    iiif_id=service,
                    width=canvas.get("width"),
                    height=canvas.get("height"),
                    extra={
                        "ark": ark,
                        "fonds": fonds_title,
                        "page_label": page_label,
                        "manifest": manifest_url,
                        "notice": notice_url,
                        "attribution": attribution,
                        "reuse_profile": reuse_text,
                    },
                )
            )
        return records

    # -- Connector API -----------------------------------------------------

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if query and query.strip():
            arks = await self._discover_arks(query)
            if arks is None:  # anti-bot or search unavailable -> curated seeds
                arks = list(self.descriptor.seeds)
        else:
            arks = list(self.descriptor.seeds)

        assets: list[Asset] = []
        seen: set[str] = set()
        for ark in arks:
            if ark in seen:
                continue
            seen.add(ark)
            manifest = await self._fetch_manifest(ark)
            if manifest is None:
                continue
            assets.extend(self._records_from_manifest(manifest, ark))
            if len(assets) >= limit:
                break
        return assets[:limit]
