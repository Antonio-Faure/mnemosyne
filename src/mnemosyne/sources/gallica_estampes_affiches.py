"""Gallica (BnF) — Estampes et affiches (publicité industrielle).

Source sœur **estampe/affiche-only** du connecteur `gallica` générique. Même
API officielle (SRU Dublin Core + images exposées via IIIF, aucun scraping
HTML), mais la requête SRU est restreinte aux types documentaires « estampe »
et « affiche » afin de ne plus enfouir la production graphique (affiches
publicitaires, estampes) sous les livres, la presse et les photographies.

Cible éditoriale : affiches publicitaires de l'industrie française de la fin du
XIXe au début du XXe siècle — en premier lieu la publicité du pneu
(Michelin/Bibendum, illustrée par O'Galop, ~1900-1930), ainsi que les affiches
d'usines et de produits industriels conservées par la BnF (Département des
Estampes et de la photographie, arks `btv1b…`).

Accès : l'hôte `gallica.bnf.fr` renvoie HTTP 403 (WAF Cloudflare) depuis l'IP
d'exécution de l'agent — même blocage infrastructurel que les sources `gallica`
et `gallica_agences_photos` (voir leurs descripteurs et docs/SOURCES.md). Le
connecteur frappe bien l'API officielle ; il ne contourne volontairement rien
(règle 403 respectée).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_ARK_RE = re.compile(r"(ark:/12148/[A-Za-z0-9._-]+)")

#: Valeurs du facette `dc.type` de Gallica qui isolent les estampes et les
#: affiches (Département des Estampes et de la photographie). Surchargeable via
#: `descriptor.extra["doc_types"]` (liste ou chaîne).
_DEFAULT_DOC_TYPES = ("estampe", "affiche")

#: Genres exposés dans `extra.genre` / tag `genre:<nom>`, par ordre de
#: préférence (l'affiche, plus spécifique, prime sur l'estampe).
_GENRES = ("affiche", "estampe")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(elem: ET.Element, name: str) -> list[str]:
    out = []
    for child in elem.iter():
        if _localname(child.tag) == name and child.text:
            out.append(child.text.strip())
    return out


class GallicaEstampesAffichesConnector(Connector):
    """SRU search restricted to prints and posters (estampes / affiches)."""

    def _doc_types(self) -> list[str]:
        raw = self.descriptor.extra.get("doc_types")
        if isinstance(raw, str):
            raw = [raw]
        if not raw:
            raw = list(_DEFAULT_DOC_TYPES)
        types = [str(t).strip() for t in raw if str(t).strip()]
        return types or list(_DEFAULT_DOC_TYPES)

    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        doc_types = self._doc_types()
        # Restriction *au niveau requête* : sinon livres/journaux/photographies
        # dominent le classement et enfouissent les affiches (cf. `gallica`).
        type_clause = " or ".join(f'(dc.type all "{t}")' for t in doc_types)
        cql = f'(gallica all "{query}") and ({type_clause})'
        params = {
            "operation": "searchRetrieve",
            "version": "1.2",
            "query": cql,
            "maximumRecords": str(min(limit, 50)),
            "startRecord": "1",
        }
        resp = await self.http.get(
            self.descriptor.base_url,
            params=params,
            accept="application/xml, text/xml;q=0.9, */*;q=0.5",
        )
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return []

        assets: list[Asset] = []
        for record in root.iter():
            if _localname(record.tag) != "record":
                continue
            asset = self._parse_record(record)
            if asset:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _parse_record(self, record: ET.Element) -> Asset | None:
        identifiers = [i for i in _texts(record, "identifier") if _ARK_RE.search(i)]
        if not identifiers:
            return None
        page_url = identifiers[0]
        ark_match = _ARK_RE.search(page_url)
        if not ark_match:
            return None
        ark = ark_match.group(1)
        source_asset_id = ark.split("/")[-1]

        titles = _texts(record, "title")
        dates = _texts(record, "date")
        creators = _texts(record, "creator")
        descriptions = _texts(record, "description")
        rights = _texts(record, "rights")

        genre = self._detect_genre(record)

        base = f"https://gallica.bnf.fr/iiif/{ark}/f1"
        extra: dict[str, object] = {"source": "gallica-sru"}
        if genre:
            extra["genre"] = genre
        return Asset.build(
            self.id,
            source_asset_id,
            title=titles[0] if titles else "",
            description=descriptions[0] if descriptions else "",
            creator=creators[0] if creators else None,
            date_text=dates[0] if dates else None,
            year=parse_year(dates[0] if dates else None),
            rights=rights[0] if rights else self.descriptor.rights,
            license=self.descriptor.license,
            page_url=(
                page_url
                if page_url.startswith("http")
                else f"https://gallica.bnf.fr/{page_url}"
            ),
            image_url=f"{base}/full/full/0/native.jpg",
            thumbnail_url=f"{base}/full/384,/0/native.jpg",
            iiif_id=ark,
            tags=[f"genre:{genre}"] if genre else [],
            extra=extra,
        )

    @staticmethod
    def _detect_genre(record: ET.Element) -> str | None:
        """Return the document genre (affiche/estampe) declared in the record."""
        haystack = " ".join(_texts(record, "type")).lower()
        for genre in _GENRES:
            if genre in haystack:
                return genre
        return None
