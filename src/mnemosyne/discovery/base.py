"""Discoverer contract: find candidate providers from a structured source."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mnemosyne.discovery.models import DiscoveryRecord
from mnemosyne.http import HttpClient


class Discoverer(ABC):
    name: str = "discoverer"

    @abstractmethod
    async def discover(self, http: HttpClient, limit: int = 50) -> list[DiscoveryRecord]:
        """Return up to `limit` candidate providers."""
