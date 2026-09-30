"""Gallica (BnF) via the SRU search API, images exposed through IIIF."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_ARK_RE = re.compile(r"(ark:/12148/[A-Za-z0-9._-]+)")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(elem: ET.Element, name: str) -> list[str]:
    out = []
    for child in elem.iter():
        if _localname(child.tag) == name and child.text:
            out.append(child.text.strip())
    return out


class GallicaConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        params = {
            "operation": "searchRetrieve",
            "version": "1.2",
            "query": f'gallica all "{query}"',
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

        base = f"https://gallica.bnf.fr/iiif/{ark}/f1"
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
            page_url=page_url if page_url.startswith("http") else f"https://gallica.bnf.fr/{page_url}",
            image_url=f"{base}/full/full/0/native.jpg",
            thumbnail_url=f"{base}/full/384,/0/native.jpg",
            iiif_id=ark,
            extra={"source": "gallica-sru"},
        )
