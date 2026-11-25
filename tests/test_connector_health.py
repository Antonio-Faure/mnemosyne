"""The generic source health probe must not report a silent True."""

from __future__ import annotations

import asyncio

import httpx

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset, SourceDescriptor


class _Dummy(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        return []


class _Http:
    def __init__(self, *, status: int = 200):
        self.status = status

    async def get(self, url, **kwargs):
        if self.status >= 400:
            request = httpx.Request("GET", url)
            response = httpx.Response(self.status, request=request)
            raise httpx.HTTPStatusError("status", request=request, response=response)
        return httpx.Response(self.status, request=httpx.Request("GET", url))


def _health(status: int) -> bool:
    descriptor = SourceDescriptor(id="x", name="X", base_url="https://example.org")
    return asyncio.run(_Dummy(descriptor, _Http(status=status)).health())


def test_health_accepts_a_reachable_server():
    assert _health(200) is True


def test_health_treats_a_parameter_error_as_reachable():
    assert _health(400) is True


def test_health_rejects_forbidden_or_failed_servers():
    assert _health(403) is False
    assert _health(404) is False
