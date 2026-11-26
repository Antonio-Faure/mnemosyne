"""Archives de Paris — fonds photographiques, via the public Arkothèque JSON API.

Verified live (2026-11) against https://archives.paris.fr (Arkothèque « ad75 »):

* search         GET /_recherche-api/search-simple/41?<bracket params>   (JSON)
* record detail  GET /_recherche-api/render-fiche/<moteur>/<ref>/<mode>/detail
* image          GET /_recherche-images/show/<fiche>/image/<image>/<pos>/...
                 = IIIF Image API v2, level 2 (info.json + full/!W,H/0/default.jpg)

The `/_arkotheque/*` and `/tags/*` routes (robots-disallowed, CAPTCHA login) are
NEVER touched, and no front-page HTML is scraped: only the public
`/_recherche-api/` JSON and `/_recherche-images/` IIIF endpoints are used.

Scope honesty: free-text « Citroën » / « usine Citroen » return 0 digitised
photographs (checked live), so this connector does NOT promise the Javel Citroën
works. It is wired at *territory* level (Javel, quai de Grenelle, 15e arrond.)
to supply period context imagery. Rights: per-record credit "Archives de Paris",
no open licence, no re-hosting — only metadata + a IIIF thumbnail pointing back.
"""

from __future__ import annotations

import re
from html import unescape as _html_unescape
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

# Arkothèque's internal ids are opaque and millésime-specific; keep the default
# here but let the descriptor override them so the catalog stays the source of
# truth.
_DEFAULT_MOTEUR = "arko_default_67d426d4c0eab"
_DEFAULT_FIELD = "arko_default_67d42ab10bf33"  # facette « Édifice/site représenté »
_DEFAULT_MODE = "arko_default_67d42cbbe4d8f"  # restitution « Mosaïque »

_IMG_RE = re.compile(r"/_recherche-images/show/(\d+)/image/(\d+)/(\d+)")
_CHAMP_RE = re.compile(r'data-champ="([^"]+)"[^>]*>(.*?)</', re.S)
_DL_RE = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# data-champ label candidates per normalized Asset field. Labels differ between
# Arkothèque instances, so accept a generous set; unmatched fields are simply
# ignored (the raw provider shape never leaks past this connector).
_TITLE_FIELDS = ("titre", "titredocument", "titrepropre", "legende")
_CREATOR_FIELDS = ("auteur", "auteurs", "photographe", "photographes", "operateur", "commanditaire")
_DATE_FIELDS = ("datation", "date", "dateexacte", "dateprecise", "periode", "annee")
_DESC_FIELDS = ("analyse", "description", "leginternet", "sujet", "resume", "descriptif")
_LIEU_FIELDS = (
    "lieu_administratif",
    "lieuadministratif",
    "lieu",
    "adresse",
    "voie",
    "arrondissement",
    "geographie",
    "localisation",
)
_COLLECTION_FIELDS = ("collection", "fonds", "origine", "serie", "sous_serie")
_PHOTOTYPE_FIELDS = ("phototype", "type_ouvrage", "typeouvrage", "type", "genre", "technique")
_COSTE_FIELDS = ("cote", "reference", "intitule")
_RIGHTS_FIELDS = ("copyright", "mention", "mentionobligatoire", "droits", "credit")


def _clean(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = _html_unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _first(mapping: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = mapping.get(name)
        if value:
            return value
    return None


def _parse_champs(html: str) -> dict[str, str]:
    champs: dict[str, str] = {}
    for match in _CHAMP_RE.finditer(html):
        name = match.group(1).strip()
        value = _clean(match.group(2))
        if value and name not in champs:
            champs[name] = value
    return champs


def _parse_definition_list(html: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for match in _DL_RE.finditer(html):
        label = _clean(match.group(1)).lower()
        value = _clean(match.group(2))
        if value and label not in pairs:
            pairs[label] = value
    return pairs


def _lookup_by_label(pairs: dict[str, str], needles: tuple[str, ...]) -> str | None:
    for label, value in pairs.items():
        if any(needle in label for needle in needles):
            return value
    return None


class ArchivesParisConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        query = (query or "").strip()
        if not query or limit <= 0:
            return []
        results = await self._search_records(query, limit, filters)
        assets: list[Asset] = []
        for record in results:
            if len(assets) >= limit:
                break
            asset = await self._build_asset(record)
            if asset is not None:
                assets.append(asset)
        return assets

    # -- search ---------------------------------------------------------------

    def _search_url(self) -> str:
        endpoint = self.descriptor.extra.get("search_endpoint", "/_recherche-api/search-simple/41")
        return self.descriptor.base_url.rstrip("/") + endpoint

    def _search_params(self, query: str, offset: int, size: int) -> list[tuple[str, str]]:
        prefix = self.descriptor.extra.get("moteur", _DEFAULT_MOTEUR)
        field = self.descriptor.extra.get("field_fulltext", _DEFAULT_FIELD)
        mode = self.descriptor.extra.get("mode_restitution", _DEFAULT_MODE)
        base = f"{prefix}--filtreGroupes[groupes][0][{field}]"
        return [
            (f"{prefix}--filtreGroupes[mode]", "simple"),
            (f"{prefix}--filtreGroupes[op]", "AND"),
            (f"{base}[op]", "AND"),
            (f"{base}[q][]", query),
            (f"{base}[extras][mode]", "input"),
            (f"{prefix}--from", str(offset)),
            (f"{prefix}--resultSize", str(size)),
            (f"{prefix}--modeRestit", mode),
            (f"{prefix}--searchMode", "strict"),
        ]

    async def _search_records(
        self, query: str, limit: int, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        offset = int(filters.get("offset", 0) or 0)
        size = 25 if limit <= 25 else 50 if limit <= 50 else 100
        resp = await self.http.get(
            self._search_url(),
            params=self._search_params(query, offset, size),
            accept="application/json",
        )
        try:
            payload = resp.json()
        except Exception:
            return []
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        return [r for r in results[:size] if isinstance(r, dict)]

    # -- record detail -> asset ----------------------------------------------

    async def _build_asset(self, record: dict[str, Any]) -> Asset | None:
        fiche_id = record.get("id")
        ref_unique = record.get("refUnique")
        intitule = (record.get("intitule") or "").strip()
        if fiche_id in (None, "") or not ref_unique:
            return None
        html = await self._fetch_detail(str(ref_unique))
        if not html:
            return None
        image = _IMG_RE.search(html)
        if not image:
            return None
        image_base = (
            f"{self.descriptor.base_url.rstrip('/')}"
            f"/_recherche-images/show/{image.group(1)}/image/{image.group(2)}/{image.group(3)}"
        )
        champs = _parse_champs(html)
        pairs = _parse_definition_list(html)

        title = _first(champs, _TITLE_FIELDS) or intitule
        cote = _first(champs, _COSTE_FIELDS) or intitule
        creator = _first(champs, _CREATOR_FIELDS) or _lookup_by_label(
            pairs, ("auteur", "photographe", "operateur")
        )
        date_text = _first(champs, _DATE_FIELDS) or _lookup_by_label(
            pairs, ("date", "datation", "periode")
        )
        description = _first(champs, _DESC_FIELDS) or ""
        lieu = _first(champs, _LIEU_FIELDS) or _lookup_by_label(pairs, ("lieu", "adresse"))
        collection = _first(champs, _COLLECTION_FIELDS)
        phototype = _first(champs, _PHOTOTYPE_FIELDS)
        rights = (
            _first(champs, _RIGHTS_FIELDS)
            or _lookup_by_label(pairs, ("mention", "credit", "droits"))
            or self.descriptor.rights
        )

        extra: dict[str, Any] = {"cote": cote}
        if lieu:
            extra["lieu"] = lieu
        if collection:
            extra["collection"] = collection
        if phototype:
            extra["phototype"] = phototype

        page_url = (
            f"{self.descriptor.base_url.rstrip('/')}"
            f"/rechercher-dans-les-collections-photographiques?detail={fiche_id}"
        )
        return Asset.build(
            self.id,
            str(fiche_id),
            title=title,
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            rights=rights,
            license=self.descriptor.license,
            page_url=page_url,
            image_url=f"{image_base}/full/!800,800/0/default.jpg",
            thumbnail_url=f"{image_base}/full/!400,400/0/default.jpg",
            iiif_id=image_base,
            extra=extra,
        )

    async def _fetch_detail(self, ref_unique: str) -> str | None:
        moteur = self.descriptor.extra.get("moteur", _DEFAULT_MOTEUR)
        mode = self.descriptor.extra.get("mode_restitution", _DEFAULT_MODE)
        url = (
            f"{self.descriptor.base_url.rstrip('/')}"
            f"/_recherche-api/render-fiche/{moteur}/{ref_unique}/{mode}/detail"
        )
        resp = await self.http.get(url, accept="application/json")
        try:
            payload = resp.json()
        except Exception:
            return None
        if isinstance(payload, dict):
            html = payload.get("html")
            return html if isinstance(html, str) else None
        return None
