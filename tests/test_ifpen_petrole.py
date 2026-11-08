"""IFPEN source: deliberately inert (no public photo archive) — no network."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.ifpen_petrole import IfpenPetroleConnector


class _NoNetwork:
    async def get_json(self, *args, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("ifpen_petrole must never touch the network")


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="ifpen_petrole",
        name="IFPEN",
        protocol=Protocol.REST,
        base_url="https://www.ifpenergiesnouvelles.fr/",
        auth="none",
        enabled=False,
    )


@pytest.mark.asyncio
async def test_search_returns_no_assets_without_network():
    connector = IfpenPetroleConnector(_descriptor(), _NoNetwork())
    assert await connector.search("pétrole Parentis") == []


@pytest.mark.asyncio
async def test_health_is_false():
    connector = IfpenPetroleConnector(_descriptor(), _NoNetwork())
    assert await connector.health() is False
