"""Gallica (BnF) — agences photographiques de presse (Rol / Meurisse / Mondial).

Source sœur **photo-only** du connecteur `gallica` générique. Même API
officielle (SRU Dublin Core + images exposées via IIIF, aucun scraping HTML),
mais la requête SRU est restreinte au type documentaire « photographie » afin de
ne plus enfouir les collections photographiques des agences de presse sous les
livres et les journaux.

Cible éditoriale : photographies de presse 1929-1934 de la Grande Dépression
(usine Citroën du quai de Javel, Rosalie au Salon 1932, Traction Avant 1934),
conservées par la BnF sur Gallica (collections Agence Rol / Meurisse / Mondial,
arks `btv1b…`).

Accès : l'hôte `gallica.bnf.fr` renvoie HTTP 403 (WAF Cloudflare) depuis l'IP
d'exécution de l'agent — même blocage infrastructurel que la source `gallica`
(voir son descripteur et docs/SOURCES.md). Le connecteur frappe bien l'API
officielle ; il est sans effet côté contournement (règle 403 respectée).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_ARK_RE = re.compile(r"(ark:/12148/[A-Za-z0-9._-]+)")

#: Agences de presse dont les photographies sont visées par cette source sœur.
_AGENCIES = ("Agence Rol", "Agence Meurisse", "Agence Mondial")

#: Valeur du facette `dc.type` de Gallica qui isole les photographies.
#: Surchargeable via `descriptor.extra["doc_type"]`.
_PHOTO_TYPE = "photographie"

#: Champs Dublin Core où l'on cherche une mention d'agence de presse.
_AGENCY_FIELDS = (
    "title",
    "creator",
    "description",
    "subject",
    "source",
    "relation",
    "publisher",
)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(elem: ET.Element, name: str) -> list[str]:
    out = []
    for child in elem.iter():
        if _localname(child.tag) == name and child.text:
            out.append(child.text.strip())
    return out


class GallicaAgencesPhotosConnector(Connector):
    """SRU search restricted to photographs from the press-agency collections."""

    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        doc_type = str(self.descriptor.extra.get("doc_type") or _PHOTO_TYPE)
        # Restriction *au niveau requête* : sinon les livres/journaux dominent le
        # classement et enfouissent les photographies (cf. connecteur `gallica`).
        cql = f'(gallica all "{query}") and (dc.type all "{doc_type}")'
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

        agency = self._detect_agency(record)

        base = f"https://gallica.bnf.fr/iiif/{ark}/f1"
        extra: dict[str, object] = {"source": "gallica-sru"}
        if agency:
            extra["agence"] = agency
        return Asset.build(
            self.id,
            source_asset_id,
            title=titles[0] if titles else "",
            description=descriptions[0] if descriptions else "",
            creator=creators[0] if creators else (agency or None),
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
            tags=[f"agence:{agency}"] if agency else [],
            extra=extra,
        )

    @staticmethod
    def _detect_agency(record: ET.Element) -> str | None:
        """Return the press agency named in the record, if any (case-insensitive)."""
        haystack = " ".join(
            text for name in _AGENCY_FIELDS for text in _texts(record, name)
        ).lower()
        for agency in _AGENCIES:
            if agency.lower() in haystack:
                return agency
        return None
