"""Canonical domain models: providers, assets, jobs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from mnemosyne.util import stable_id, utcnow_iso


class SourceState(StrEnum):
    """Lifecycle of a provider inside the catalog (see heartbeat)."""

    DISCOVERED = "discovered"
    RESEARCHED = "researched"
    ONBOARDING = "onboarding"
    PENDING = "pending"
    CREDENTIALED = "credentialed"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    BROKEN = "broken"


#: Allowed transitions of the provider state machine.
TRANSITIONS: dict[SourceState, set[SourceState]] = {
    SourceState.DISCOVERED: {SourceState.RESEARCHED, SourceState.BROKEN},
    SourceState.RESEARCHED: {SourceState.ONBOARDING, SourceState.CONNECTED, SourceState.BROKEN},
    SourceState.ONBOARDING: {SourceState.PENDING, SourceState.CREDENTIALED, SourceState.BROKEN},
    SourceState.PENDING: {SourceState.CREDENTIALED, SourceState.BROKEN},
    SourceState.CREDENTIALED: {SourceState.CONNECTED, SourceState.BROKEN},
    SourceState.CONNECTED: {SourceState.DEGRADED, SourceState.BROKEN},
    SourceState.DEGRADED: {SourceState.CONNECTED, SourceState.BROKEN},
    SourceState.BROKEN: {SourceState.DISCOVERED, SourceState.ONBOARDING, SourceState.RESEARCHED},
}


class AuthKind(StrEnum):
    NONE = "none"
    API_KEY = "api_key"
    ACCOUNT = "account"
    OAUTH = "oauth"


class Protocol(StrEnum):
    IIIF = "iiif"
    SRU = "sru"
    OAIPMH = "oaipmh"
    SPARQL = "sparql"
    REST = "rest"
    HTML = "html"
    EMAIL = "email"


class SourceDescriptor(BaseModel):
    """Declarative description of a provider, loaded from `config/sources/*.yaml`."""

    id: str
    name: str
    institution: str | None = None
    country: str | None = None
    protocol: Protocol = Protocol.REST
    base_url: str
    auth: AuthKind = AuthKind.NONE
    key_env: str | None = None
    license: str | None = None
    rights: str | None = None
    rate_limit_per_s: float = 1.0
    priority: int = 100
    tags: list[str] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    enabled: bool = True
    notes: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Asset(BaseModel):
    """A normalized image record. Provider-specific shape never leaks past here."""

    id: str
    source_id: str
    source_asset_id: str
    title: str = ""
    description: str = ""
    creator: str | None = None
    date_text: str | None = None
    year: int | None = None
    license: str | None = None
    rights: str | None = None
    page_url: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    iiif_id: str | None = None
    width: int | None = None
    height: int | None = None
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: str = Field(default_factory=utcnow_iso)

    @classmethod
    def build(cls, source_id: str, source_asset_id: str, **kwargs: Any) -> Asset:
        return cls(
            id=stable_id(source_id, source_asset_id),
            source_id=source_id,
            source_asset_id=source_asset_id,
            **kwargs,
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_asset_id": self.source_asset_id,
            "page_url": self.page_url,
            "license": self.license,
            "rights": self.rights,
            "retrieved_at": self.retrieved_at,
        }


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    id: int | None = None
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state: JobState = JobState.PENDING
    priority: int = 100
    attempts: int = 0
    max_attempts: int = 5
    run_at: str = Field(default_factory=utcnow_iso)
    locked_at: str | None = None
    last_error: str | None = None
