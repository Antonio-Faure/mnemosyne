"""Wikidata: entity resolution + canonical image (P18), via wbsearchentities + SPARQL."""

from __future__ import annotations

from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_SEARCH_API = "https://www.wikidata.org/w/api.php"
_SPARQL = "https://query.wikidata.org/sparql"


class WikidataConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        qids = await self._find_entities(query, limit)
        if not qids:
            return []
        rows = await self._fetch_images(qids)
        return [a for row in rows if (a := self._row_to_asset(row))]

    async def _find_entities(self, query: str, limit: int) -> list[str]:
        data = await self.http.get_json(
            _SEARCH_API,
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "fr",
                "uselang": "fr",
                "type": "item",
                "limit": str(min(limit, 20)),
                "format": "json",
            },
        )
        return [hit["id"] for hit in data.get("search", []) if hit.get("id")]

    async def _fetch_images(self, qids: list[str]) -> list[dict]:
        values = " ".join(f"wd:{q}" for q in qids)
        sparql = f"""
        SELECT ?item ?itemLabel ?image WHERE {{
          VALUES ?item {{ {values} }}
          OPTIONAL {{ ?item wdt:P18 ?image. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
        }}
        """
        data = await self.http.get_json(
            _SPARQL,
            params={"query": sparql, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        return [b for b in data.get("results", {}).get("bindings", []) if b.get("image")]

    def _row_to_asset(self, row: dict) -> Asset | None:
        item_url = row["item"]["value"]
        qid = item_url.rsplit("/", 1)[-1]
        image = row["image"]["value"].replace("http://", "https://")
        filename = image.rsplit("/", 1)[-1]
        label = row.get("itemLabel", {}).get("value", qid)
        thumb = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=512"
        return Asset.build(
            self.id,
            qid,
            title=label,
            description=f"Canonical image (P18) for {label}",
            date_text=None,
            year=parse_year(label),
            license="CC0 (data) / per-image Commons license",
            rights=self.descriptor.rights,
            page_url=item_url,
            image_url=image,
            thumbnail_url=thumb,
            extra={"qid": qid, "image_file": filename},
        )
