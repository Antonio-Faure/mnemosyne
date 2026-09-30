"""Engine: wires catalog, connectors, governor and store together.

Shared by the CLI, the aggregation API and the heartbeat.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mnemosyne.catalog import Catalog
from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.http import HttpClient
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset, SourceDescriptor, SourceState
from mnemosyne.normalize import DedupIndex, normalize
from mnemosyne.reputation import Governor, GovernorBlocked
from mnemosyne.sources import build_connector

log = get_logger("engine")


class Engine:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_file())
        self.catalog = Catalog(config.sources_path, self.db)
        self.governor = Governor(config.reputation, self.db)
        self.http = HttpClient(governor=self.governor, contact=None)

    async def aclose(self) -> None:
        await self.http.aclose()

    # ── search ───────────────────────────────────────────────────────────
    async def search(
        self,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 20,
        dedup: bool = True,
    ) -> list[Asset]:
        descriptors = [
            d
            for d in self.catalog.list()
            if d.enabled and (source_ids is None or d.id in source_ids)
        ]
        if not descriptors:
            return []

        results = await asyncio.gather(
            *(self._search_one(d, query, limit, dedup) for d in descriptors),
            return_exceptions=True,
        )
        merged: list[Asset] = []
        for res in results:
            if isinstance(res, list):
                merged.extend(res)
            elif isinstance(res, Exception):
                log.debug("source search failed: %s", res)
        return normalize(merged)

    async def _search_one(
        self, descriptor: SourceDescriptor, query: str, limit: int, dedup: bool
    ) -> list[Asset]:
        connector = build_connector(descriptor, self.http)
        if connector is None:
            log.debug(
                "no connector for %s (declared protocol=%s)",
                descriptor.id,
                descriptor.protocol,
            )
            return []
        if not self.governor.allowed("harvest"):
            log.info("harvest cap reached for today; skipping %s", descriptor.id)
            return []
        index = DedupIndex(dedup)
        try:
            assets = await connector.search(query, limit=limit)
        except GovernorBlocked as exc:
            log.warning("%s: %s", descriptor.id, exc)
            return []
        except Exception as exc:  # noqa: BLE001 - one provider must not break the call
            log.warning("%s search error: %s", descriptor.id, exc)
            await self._degrade(descriptor.id, str(exc))
            return []
        self.governor.record("harvest")
        fresh = [a for a in normalize(assets) if not index.is_duplicate(a)]
        for a in fresh:
            index.add(a)
        return fresh

    # ── harvest / verify ─────────────────────────────────────────────────
    async def harvest(self, source_id: str, query: str, limit: int = 20) -> int:
        descriptor = self.catalog.get(source_id)
        if descriptor is None:
            return 0
        assets = await self._search_one(descriptor, query, limit, dedup=True)
        saved = self.db.save_assets(assets)
        if saved:
            self.catalog.set_state(source_id, SourceState.CONNECTED)
        return saved

    async def verify(self, source_id: str) -> bool:
        descriptor = self.catalog.get(source_id)
        if descriptor is None:
            return False
        connector = build_connector(descriptor, self.http)
        if connector is None:
            return False
        try:
            ok = await connector.health()
        except Exception as exc:  # noqa: BLE001
            await self._degrade(source_id, str(exc))
            return False
        self.catalog.set_state(
            source_id, SourceState.CONNECTED if ok else SourceState.DEGRADED
        )
        return ok

    async def _degrade(self, source_id: str, error: str) -> None:
        try:
            self.catalog.set_state(source_id, SourceState.DEGRADED, error)
        except Exception:  # noqa: BLE001
            pass

    # ── introspection ────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        sources = []
        for record in self.db.list_sources():
            descriptor = record["descriptor"]
            sources.append(
                {
                    "id": record["id"],
                    "name": descriptor.get("name"),
                    "state": record["state"],
                    "protocol": descriptor.get("protocol"),
                    "auth": descriptor.get("auth"),
                    "last_error": record["last_error"],
                    "asset_count": self.db.count_assets(record["id"]),
                }
            )
        return {
            "sources": sources,
            "assets_total": self.db.count_assets(),
            "governor": self.governor.status(),
        }
