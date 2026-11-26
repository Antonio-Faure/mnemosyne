"""La Contemporaine (ex-BDIC, Nanterre) — bibliothèque numérique L'Argonnaute.

Accès 100 % programmatique, sans scraping et sans contournement d'anti-bot
(règle dure du projet, cf. ``docs/SOURCE-LA-CONTEMPORAINE.md``).

La plateforme L'Argonnaute (https://argonnaute.parisnanterre.fr) n'expose :

* **aucun IIIF** (``app.toolbar.isIIIFEnabled == false``, ``location.iiif ==
  null``) ;
* **aucune API de recherche** (pas d'index JSON/Solr public : la recherche par
  mot-clé n'existe qu'en page rendue côté serveur) ;
* une **API JSON PAR DOCUMENT** ::

      /visualizer/api?arkName=<ARK>&uuid=<UUID>

  qui renvoie ``media[0].record{title, referenceCode, description, period,
  locationKeywords}`` + ``media[0].location{original, thumb, iiif: null}`` ;
* des **images servies en direct** (hotlink, aucune copie, aucune réhébergement)::

      /images/<UUID>.jpg            (pleine résolution)
      /images/<UUID>_thumbnail.jpg  (vignette)

Comme la recherche ne peut pas se faire par programme, la découverte passe par
une liste ``seeds`` curatée (une URL notice/média par photographie pertinente
pour l'histoire sociale et ouvrière). Chaque seed est résolue via l'API JSON par
document ; l'image n'est **jamais téléchargée** (on renvoie son URL publique).
``robots.txt`` autorise ces chemins (seuls ``/private/``, ``/oai-pmh``,
``/user/`` sont interdits) et l'User-Agent descriptif du projet n'est pas dans la
liste des robots bloqués. ``GET /visualizer/api`` sans ``uuid`` renvoie ``400`` :
l'API est strictement par document.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.la_contemporaine_argonnaute")

_SEED_RE = re.compile(r"ark:/(?P<naan>\d+)/(?P<ark>[^/]+)/(?P<uuid>[0-9a-fA-F-]+)")
_DEFAULT_API_PATH = "/visualizer/api"
#: bound the per-search work (one HTTP call per seed) so a large seed list can
#: never blow through the engine's per-source timeout
_MAX_SEEDS_PER_SEARCH = 20
_MIN_TOKEN_LEN = 3


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    normalised = _strip_accents(text.lower())
    return {t for t in re.split(r"[^a-z0-9]+", normalised) if len(t) >= _MIN_TOKEN_LEN}


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _parse_seed(seed: str) -> tuple[str, str] | None:
    """Extract ``(arkName, uuid)`` from a seed (notice/média URL or ``ark:uuid``)."""
    seed = (seed or "").strip()
    if not seed:
        return None
    match = _SEED_RE.search(seed)
    if match:
        return match.group("ark"), match.group("uuid")
    # tolerate a bare "arkName:uuid" pair without any slashes
    if ":" in seed and "/" not in seed:
        ark, _, uuid = seed.partition(":")
        if ark.strip() and uuid.strip():
            return ark.strip(), uuid.strip()
    return None


class LaContemporaineArgonnauteConnector(Connector):
    """Per-document JSON API connector over a curated seed list (no HTML)."""

    def _api_path(self) -> str:
        return str((self.descriptor.extra or {}).get("api_path") or _DEFAULT_API_PATH)

    def _attribution(self) -> str:
        extra = self.descriptor.extra or {}
        return str(
            extra.get("attribution")
            or self.descriptor.institution
            or self.descriptor.name
        )

    def _api_url(self, ark: str, uuid: str) -> str:
        return (
            f"{self.descriptor.base_url.rstrip('/')}{self._api_path()}"
            f"?arkName={quote(ark, safe='')}&uuid={quote(uuid, safe='')}"
        )

    async def _fetch(self, ark: str, uuid: str) -> dict | None:
        url = self._api_url(ark, uuid)
        try:
            data = await self.http.get_json(url)
        except Exception as exc:  # noqa: BLE001 - a dead seed must not break search
            log.debug("la_contemporaine %s failed: %s", url, exc)
            return None
        return data if isinstance(data, dict) else None

    def _asset_from_doc(self, data: dict) -> Asset | None:
        media = data.get("media")
        if not isinstance(media, list) or not media:
            return None
        item = media[0]
        if not isinstance(item, dict):
            return None
        if item.get("type") not in (None, "image"):
            return None
        uuid = item.get("uuid")
        record = item.get("record") or {}
        if not isinstance(record, dict):
            record = {}
        location = item.get("location") or {}
        if not isinstance(location, dict):
            location = {}
        image_url = location.get("original")
        if not uuid or not image_url:
            return None

        title = _first(record.get("title")) or "Sans titre"
        reference = record.get("referenceCode") or []
        if isinstance(reference, str):
            reference = [reference]
        reference_code = " ; ".join(str(r) for r in reference if r) or None
        description = record.get("description") or ""
        keywords = record.get("locationKeywords") or []
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        period = record.get("period") or {}
        if not isinstance(period, dict):
            period = {}
        boundaries = period.get("boundaries") or []
        if not isinstance(boundaries, list):
            boundaries = []
        date_from = boundaries[0] if len(boundaries) > 0 else None
        date_to = boundaries[1] if len(boundaries) > 1 else None
        if date_from and date_to and date_from != date_to:
            date_text = f"{date_from}/{date_to}"
        else:
            date_text = date_from or date_to
        year = parse_year(date_from) or parse_year(date_to)

        record_url = record.get("url")
        viewer_url = item.get("url")

        return Asset.build(
            self.id,
            str(uuid),
            title=str(title),
            description=str(description),
            date_text=date_text,
            year=year,
            license=self.descriptor.license,
            rights=self._attribution(),
            page_url=record_url or viewer_url,
            image_url=image_url,
            thumbnail_url=location.get("thumb"),
            tags=[str(k) for k in keywords],
            extra={
                "ark": (record.get("arkId") or {}).get("arkName"),
                "reference_code": reference_code,
                "record_url": record_url,
                "viewer_url": viewer_url,
                "date_from": date_from,
                "date_to": date_to,
                "keywords": [str(k) for k in keywords],
                "attribution": self._attribution(),
                "license_text_source": "app.licenses.visualizer (L'Argonnaute)",
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
                    " ".join(asset.tags or []),
                    str((asset.extra or {}).get("reference_code") or ""),
                    asset.date_text or "",
                ]
            )
        )
        return len(wanted & haystack)

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        pairs: list[tuple[str, str]] = []
        for raw in self.descriptor.seeds:
            parsed = _parse_seed(raw)
            if parsed is not None:
                pairs.append(parsed)
        if not pairs:
            return []

        assets: list[Asset] = []
        for ark, uuid in pairs[:_MAX_SEEDS_PER_SEARCH]:
            data = await self._fetch(ark, uuid)
            if data is None:
                continue
            asset = self._asset_from_doc(data)
            if asset is not None:
                assets.append(asset)

        # Relevant photos first; a stable sort keeps the curated seed order
        # for ties (and when the query carries no usable token).
        assets.sort(key=lambda a: self._relevance(a, query), reverse=True)
        return assets[: max(limit, 0)]
