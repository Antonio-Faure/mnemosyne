"""The source health probe must test the real search path, not just base_url."""

from __future__ import annotations

import asyncio

import pytest

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset, AuthKind, SourceDescriptor


class _Dummy(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        return []


class _Boom(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        raise RuntimeError("HTTP 403")


def _descriptor(**overrides) -> SourceDescriptor:
    data = {"id": "x", "name": "X", "base_url": "https://example.org"}
    data.update(overrides)
    return SourceDescriptor(**data)


def test_health_accepts_a_working_search_even_with_no_result():
    assert asyncio.run(_Dummy(_descriptor(), object()).health()) is True


def test_health_reports_the_search_failure():
    with pytest.raises(RuntimeError, match="403"):
        asyncio.run(_Boom(_descriptor(), object()).health())


def test_health_reports_a_missing_api_key():
    with pytest.raises(RuntimeError, match="clé API absente"):
        asyncio.run(
            _Dummy(
                _descriptor(auth=AuthKind.API_KEY, key_env="MNEMOSYNE_TEST_MISSING_KEY"),
                object(),
            ).health()
        )
