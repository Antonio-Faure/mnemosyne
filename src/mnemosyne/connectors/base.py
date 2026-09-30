"""Connector contract every provider adapter implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mnemosyne.http import HttpClient
from mnemosyne.models import Asset, SourceDescriptor


class Connector(ABC):
    """Normalizes one provider into the canonical `Asset` shape.

    Implementations must never leak provider-specific fields into `Asset`;
    everything extra goes into `Asset.extra`.
    """

    def __init__(self, descriptor: SourceDescriptor, http: HttpClient):
        self.descriptor = descriptor
        self.http = http

    @property
    def id(self) -> str:
        return self.descriptor.id

    @abstractmethod
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        """Return up to `limit` assets matching `query`."""

    async def fetch(self, asset: Asset) -> bytes | None:
        """Download the full-resolution image for an asset (lazy)."""
        if not asset.image_url:
            return None
        return await self.http.get_bytes(asset.image_url)

    def provenance(self, asset: Asset) -> dict[str, Any]:
        return {
            "provider": self.descriptor.name,
            "institution": self.descriptor.institution,
            **asset.provenance(),
        }

    async def health(self) -> bool:
        """Cheap connectivity check. Override for a real probe."""
        return True
