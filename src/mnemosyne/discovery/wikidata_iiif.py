"""Discover IIIF-capable providers via Wikidata (P6108 = IIIF manifest).

Every Wikidata item with a IIIF manifest points at a host that serves IIIF
images. Grouping manifests by host reveals real providers (national libraries,
museums, universities) without any credential.
"""

from __future__ import annotations

from urllib.parse import urlparse

from mnemosyne.discovery.base import Discoverer
from mnemosyne.discovery.models import DiscoveryRecord
from mnemosyne.http import HttpClient

_SPARQL = """SELECT (COUNT(?item) AS ?n) (SAMPLE(?manifest) AS ?sample) ?host WHERE {{
  ?item wdt:P6108 ?manifest .
  BIND(REPLACE(STR(?manifest), "^https?://([^/]+)/.*$", "$1") AS ?host)
}}
GROUP BY ?host
ORDER BY DESC(?n)
LIMIT {limit}"""


class WikidataIIIFDiscoverer(Discoverer):
    name = "wikidata:iiif_hosts"

    async def discover(self, http: HttpClient, limit: int = 50) -> list[DiscoveryRecord]:
        data = await http.get_json(
            "https://query.wikidata.org/sparql",
            params={"query": _SPARQL.format(limit=max(1, min(limit, 200))), "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        records: list[DiscoveryRecord] = []
        for row in data.get("results", {}).get("bindings", []):
            host = (row.get("host", {}) or {}).get("value", "").strip()
            if not host or "." not in host:
                continue
            count = row.get("n", {}).get("value")
            sample = (row.get("sample", {}) or {}).get("value")
            records.append(
                DiscoveryRecord.build(
                    host=host,
                    url=f"https://{host}/",
                    protocol="iiif",
                    source=self.name,
                    item_count=int(count) if count and count.isdigit() else None,
                    evidence={"sample_manifest": sample},
                )
            )
        return records


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
