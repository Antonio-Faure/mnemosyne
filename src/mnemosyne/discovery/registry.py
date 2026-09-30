"""Run every discoverer and merge their candidates."""

from __future__ import annotations

import asyncio

from mnemosyne.discovery.base import Discoverer
from mnemosyne.discovery.models import DiscoveryRecord
from mnemosyne.discovery.wikidata_iiif import WikidataIIIFDiscoverer
from mnemosyne.http import HttpClient
from mnemosyne.logger import get_logger

log = get_logger("discovery")


def discoverers() -> list[Discoverer]:
    return [WikidataIIIFDiscoverer()]


async def run_discovery(http: HttpClient, limit: int = 50) -> list[DiscoveryRecord]:
    results = await asyncio.gather(
        *(d.discover(http, limit=limit) for d in discoverers()),
        return_exceptions=True,
    )
    merged: dict[str, DiscoveryRecord] = {}
    for result in results:
        if isinstance(result, Exception):
            log.warning("discoverer failed: %s", result)
            continue
        for record in result:
            current = merged.get(record.id)
            if current is None or (record.item_count or 0) > (current.item_count or 0):
                merged[record.id] = record
    return list(merged.values())
