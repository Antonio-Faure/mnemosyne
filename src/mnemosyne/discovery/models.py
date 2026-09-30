"""Discovery records: candidate providers found before they enter the catalog."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mnemosyne.util import stable_id, utcnow_iso


class DiscoveryRecord(BaseModel):
    id: str
    host: str
    url: str
    name: str | None = None
    protocol: str | None = None
    institution: str | None = None
    country: str | None = None
    source: str = "unknown"
    item_count: int | None = None
    status: str = "new"  # new | connecting | connected | failed
    evidence: dict[str, Any] = Field(default_factory=dict)
    discovered_at: str = Field(default_factory=utcnow_iso)

    @classmethod
    def build(cls, host: str, **kwargs: Any) -> DiscoveryRecord:
        return cls(
            id=stable_id("discovery", host.lower()),
            host=host.lower(),
            url=kwargs.pop("url", f"https://{host}/"),
            **kwargs,
        )
