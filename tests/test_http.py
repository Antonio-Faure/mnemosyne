"""HttpClient: retry policy and governor block reporting (403/429)."""

from __future__ import annotations

import httpx
import pytest

from mnemosyne.http import HttpClient


class _Governor:
    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.blocks: list[str] = []

    async def acquire(self, domain: str) -> None:
        self.acquired.append(domain)

    async def report_block(self, domain: str) -> None:
        self.blocks.append(domain)


def _client(handler, governor=None) -> HttpClient:
    client = HttpClient(governor=governor)
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    return client


@pytest.mark.asyncio
async def test_403_is_reported_to_the_governor_and_not_retried():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403, request=request)

    governor = _Governor()
    client = _client(handler, governor)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get("https://blocked.example.org/page")
    finally:
        await client.aclose()

    assert governor.blocks == ["blocked.example.org"]
    assert calls == ["https://blocked.example.org/page"]  # no retry on a denial


@pytest.mark.asyncio
async def test_429_is_reported_and_retried():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    governor = _Governor()
    client = _client(handler, governor)
    try:
        payload = await client.get_json("https://rate.example.org/x")
    finally:
        await client.aclose()

    assert payload == {"ok": True}
    assert governor.blocks == ["rate.example.org"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_other_errors_do_not_reach_the_governor():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    governor = _Governor()
    client = _client(handler, governor)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get("https://missing.example.org/x")
    finally:
        await client.aclose()

    assert governor.blocks == []
    assert governor.acquired == ["missing.example.org"]
