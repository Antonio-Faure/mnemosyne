"""Paris en Images — photographies historiques de la Ville de Paris (Paris Musées).

Accès 100 % programmatique, sans scraping (règle dure du projet, cf.
``docs/SOURCES.md`` « Politique d'accès aux images » et
``docs/SOURCE-PARIS-EN-IMAGES.md``).

« Paris en Images » désigne les collections photographiques historiques de la
Ville de Paris, aujourd'hui publiées par **Paris Musées**. L'ancien domaine
``parisenimages.fr`` redirige vers ``paris.fr`` ; les œuvres vivent sur
``parismuseescollections.paris.fr`` et leur API IIIF sur
``apicollections.parismusees.paris.fr``.

La plateforme **n'expose aucune API de recherche publique** (le GraphQL
``/graphql`` exige un jeton par compte) et aucune Collection IIIF énumérable. La
découverte passe donc par une liste ``seeds`` curatée (un identifiant de visuel
IIIF par œuvre pertinente). Pour chaque seed on récupère le **manifeste IIIF
Presentation v2** par œuvre ::

    /iiif/<visuel_id>/manifest

et on en tire l'image pleine résolution
(``sequences[0].canvases[0].images[0].resource.@id``), les métadonnées et les
droits. **Droits par notice** : une œuvre ouverte (CC0 / domaine public,
signalée par le seed vérifié ou par le champ ``license`` du manifeste) est
exposée en pleine résolution avec crédit ; sinon on ne renvoie que la vignette
et le lien vers la notice, jamais l'image pleine résolution d'une œuvre
restreinte. Aucune image n'est copiée : on renvoie l'URL publique du manifeste.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.paris_en_images")

_DEFAULT_MANIFEST_TEMPLATE = (
    "https://apicollections.parismusees.paris.fr/iiif/{visuel_id}/manifest"
)
#: marqueurs d'une licence ouverte (domaine public / CC0) dans le manifeste
_OPEN_MARKERS = (
    "publicdomain/zero",
    "publicdomain/mark",
    "creativecommons.org/publicdomain",
    "cc0",
    "domaine public",
    "public domain",
    "pdm",
)
_OPEN_HINTS = {"open", "cc0", "public", "publicdomain", "domain", "pd"}
_RESTRICTED_HINTS = {"restricted", "in-copyright", "incopyright", "copyright"}

#: borne le travail par recherche (un GET manifeste par seed)
_MAX_SEEDS_PER_SEARCH = 30
_MIN_TOKEN_LEN = 3

_VISUEL_RE = re.compile(r"(\d{5,})")
#: enlève les balises d'un fragment de métadonnée (ex. dates en <span>)
_TAG_RE = re.compile(r"<[^>]*>")


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    normalised = _strip_accents(text.lower())
    return {t for t in re.split(r"[^a-z0-9]+", normalised) if len(t) >= _MIN_TOKEN_LEN}


def _plain(value: Any) -> str:
    """Aplatit une valeur de métadonnée (str / liste) en texte nu, sans balises."""
    if isinstance(value, list):
        return " ".join(_plain(v) for v in value if v is not None)
    if value is None:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def _parse_seed(seed: str) -> tuple[str, str | None, str | None] | None:
    """``(visuel_id, droits, url_notice)`` depuis ``<id>|<droits>|<notice>``.

    Accepte un identifiant nu, un identifiant suffixé, ou un manifeste/notice
    dont l'URL contient l'identifiant de visuel.
    """
    raw = (seed or "").strip()
    if not raw:
        return None
    parts = raw.split("|")
    head = parts[0].strip()
    hint = parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else None
    notice = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    match = _VISUEL_RE.search(head)
    if not match:
        return None
    return match.group(1), hint, notice


class ParisEnImagesConnector(Connector):
    """Per-object IIIF v2 manifest connector over a curated seed list (no HTML)."""

    def _manifest_template(self) -> str:
        template = (self.descriptor.extra or {}).get("manifest_template")
        return str(template or _DEFAULT_MANIFEST_TEMPLATE)

    def _manifest_url(self, visuel_id: str) -> str:
        return self._manifest_template().format(visuel_id=visuel_id)

    async def _fetch_manifest(self, visuel_id: str) -> dict | None:
        url = self._manifest_url(visuel_id)
        try:
            data = await self.http.get_json(url)
        except Exception as exc:  # noqa: BLE001 - a dead seed must not break search
            log.debug("paris_en_images %s failed: %s", url, exc)
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _metadata(manifest: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        for entry in manifest.get("metadata") or []:
            if not isinstance(entry, dict):
                continue
            label = _plain(entry.get("label")).lower()
            value = _plain(entry.get("value"))
            if label and value and label not in out:
                out[label] = value
        return out

    @staticmethod
    def _lookup(meta: dict[str, str], *needles: str) -> str | None:
        for label, value in meta.items():
            if any(needle in label for needle in needles):
                return value or None
        return None

    @staticmethod
    def _full_image(manifest: dict) -> tuple[str | None, str | None, int | None, int | None]:
        service_id: str | None = None
        try:
            canvas = manifest["sequences"][0]["canvases"][0]
            resource = canvas["images"][0]["resource"]
        except (KeyError, IndexError, TypeError):
            return None, None, None, None
        if not isinstance(resource, dict):
            return None, None, None, None
        service = resource.get("service")
        if isinstance(service, list) and service and isinstance(service[0], dict):
            service = service[0]
        if isinstance(service, dict):
            service_id = service.get("@id")
        width = resource.get("width")
        height = resource.get("height")
        return (
            resource.get("@id"),
            service_id,
            width if isinstance(width, int) else None,
            height if isinstance(height, int) else None,
        )

    @staticmethod
    def _thumbnail(manifest: dict, service_id: str | None, full_url: str | None) -> str | None:
        thumb = manifest.get("thumbnail")
        if isinstance(thumb, dict) and thumb.get("@id"):
            return thumb["@id"]
        if isinstance(thumb, list) and thumb and isinstance(thumb[0], dict):
            return thumb[0].get("@id")
        if service_id:
            return f"{service_id.rstrip('/')}/full/!400,400/0/default.jpg"
        return full_url

    @staticmethod
    def _page_url(manifest: dict, notice: str | None) -> str | None:
        if notice:
            return notice
        for key in ("related", "homepage"):
            value = manifest.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and value.get("@id"):
                return value["@id"]
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value[0].get("@id")
        return None

    def _is_open(self, hint: str | None, manifest: dict, meta: dict[str, str]) -> bool:
        if hint in _RESTRICTED_HINTS:
            return False
        if hint in _OPEN_HINTS:
            return True
        candidates = [
            manifest.get("license"),
            manifest.get("rights"),
            self._lookup(
                meta, "droits", "licence", "license", "conditions", "crédit", "credit"
            ),
        ]
        for candidate in candidates:
            text = _plain(candidate).lower()
            if text and any(marker in text for marker in _OPEN_MARKERS):
                return True
        return False

    def _asset(
        self, manifest: dict, visuel_id: str, hint: str | None, notice: str | None
    ) -> Asset | None:
        full_url, service_id, width, height = self._full_image(manifest)
        if not full_url and not service_id:
            return None
        meta = self._metadata(manifest)
        title = _plain(manifest.get("label")) or "Sans titre"
        creator = self._lookup(meta, "auteur", "artiste", "créateur", "createur")
        date_text = self._lookup(
            meta, "date de production", "datation", "période", "periode", "date"
        )
        description = (
            self._lookup(meta, "description iconographique", "description") or ""
        )
        page_url = self._page_url(manifest, notice)
        thumbnail_url = self._thumbnail(manifest, service_id, full_url)
        tags = [t.strip() for t in re.split(r"[,;]", _plain(
            self._lookup(meta, "type d'objet", "dénomination", "domaine") or ""
        )) if t.strip()]

        attribution = _plain(manifest.get("attribution")) or str(
            self.descriptor.institution or "Paris Musées"
        )
        is_open = self._is_open(hint, manifest, meta)
        if is_open:
            image_url = full_url or (
                f"{service_id.rstrip('/')}/full/max/0/default.jpg" if service_id else None
            )
            license_text = "CC0 / domaine public (Paris Musées)"
            rights_text = f"CC0 / domaine public — crédit « Paris Musées » ({attribution})"
        else:
            # droits restreints : vignette + lien seulement, jamais l'image pleine
            image_url = None
            license_text = "varies"
            rights_text = (
                "Droits par notice (« tous droits réservés ») — voir la notice ; "
                "vignette + lien uniquement"
            )

        return Asset.build(
            self.id,
            visuel_id,
            title=title,
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text or ""),
            license=license_text,
            rights=rights_text,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            iiif_id=service_id,
            width=width,
            height=height,
            tags=tags,
            extra={
                "visuel_id": visuel_id,
                "manifest_url": self._manifest_url(visuel_id),
                "notice_url": page_url,
                "is_open": is_open,
                "attribution": attribution,
                "credit": "Paris Musées / Ville de Paris",
            },
        )

    @staticmethod
    def _relevance(asset: Asset, query: str | None) -> int:
        wanted = _tokens(query)
        if not wanted:
            return 0
        haystack = _tokens(
            " ".join(
                [
                    asset.title or "",
                    asset.description or "",
                    asset.creator or "",
                    " ".join(asset.tags or []),
                    asset.date_text or "",
                ]
            )
        )
        return len(wanted & haystack)

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        seeds: list[tuple[str, str | None, str | None]] = []
        for raw in self.descriptor.seeds:
            parsed = _parse_seed(raw)
            if parsed is not None:
                seeds.append(parsed)
        if not seeds:
            return []

        assets: list[Asset] = []
        for visuel_id, hint, notice in seeds[:_MAX_SEEDS_PER_SEARCH]:
            manifest = await self._fetch_manifest(visuel_id)
            if manifest is None:
                continue
            asset = self._asset(manifest, visuel_id, hint, notice)
            if asset is not None:
                assets.append(asset)

        # Curated seeds are a fallback, not a blanket result set: when the query
        # carries usable tokens, drop seeds with no lexical relevance. Otherwise
        # every catalog search would inherit these photos.
        if _tokens(query):
            assets = [asset for asset in assets if self._relevance(asset, query) > 0]
        assets.sort(key=lambda a: self._relevance(a, query), reverse=True)
        return assets[: max(limit, 0)]
