"""Catalog: declarative source descriptors synced into the durable registry."""

from __future__ import annotations

from pathlib import Path

import yaml

from mnemosyne.db import Database
from mnemosyne.logger import get_logger
from mnemosyne.models import SourceDescriptor, SourceState

log = get_logger("catalog")


class Catalog:
    def __init__(self, sources_path: str | Path, db: Database):
        self.sources_path = Path(sources_path)
        self.db = db

    def load_descriptors(self) -> list[SourceDescriptor]:
        descriptors: list[SourceDescriptor] = []
        if not self.sources_path.exists():
            return descriptors
        for path in sorted(self.sources_path.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            try:
                descriptors.append(SourceDescriptor(**raw))
            except Exception as exc:  # noqa: BLE001 - surface a clear config error
                log.error("invalid descriptor %s: %s", path.name, exc)
        return descriptors

    def sync(self) -> list[SourceDescriptor]:
        """Upsert every descriptor into the DB (state preserved across syncs)."""
        descriptors = self.load_descriptors()
        for d in descriptors:
            existing = self.db.get_source(d.id)
            state = SourceState(existing["state"]) if existing else SourceState.DISCOVERED
            self.db.upsert_source(d.id, d.model_dump(mode="json"), state)
        return descriptors

    def get(self, source_id: str) -> SourceDescriptor | None:
        record = self.db.get_source(source_id)
        if not record:
            return None
        return SourceDescriptor(**record["descriptor"])

    def list(self) -> list[SourceDescriptor]:
        return [SourceDescriptor(**s["descriptor"]) for s in self.db.list_sources()]

    def state(self, source_id: str) -> SourceState:
        record = self.db.get_source(source_id)
        return SourceState(record["state"]) if record else SourceState.DISCOVERED

    def set_state(self, source_id: str, state: SourceState, error: str | None = None) -> None:
        self.db.set_source_state(source_id, state, error)
