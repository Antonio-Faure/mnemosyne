"""Offline tests for the Musée français du pétrole / Pechelbronn connector.

The source has no programmatic access and no written scraping consent yet, so
its descriptor is disabled and its connector abstains. Everything here is
offline: a fake HTTP client fails loudly if the connector ever touches the net.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import CONNECTORS, build_connector
from mnemosyne.sources.musee_petrole_pechelbronn import (
    MuseePetrolePechelbronnConnector,
)

YAML_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "sources"
    / "musee_petrole_pechelbronn.yaml"
)


class _FakeHttp:
    """Any network access is a test failure: the connector must abstain."""

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError(f"connector must not perform network I/O: {url}")

    async def get_bytes(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError(f"connector must not perform network I/O: {url}")


def _raw() -> dict[str, Any]:
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def test_descriptor_is_disabled_and_declares_pending_authorization() -> None:
    raw = _raw()
    assert raw["id"] == "musee_petrole_pechelbronn"
    assert raw["enabled"] is False
    assert raw["auth"] == "none"
    # Not an html protocol => no scraping-consent requirement, and no scraping.
    assert raw["protocol"] != "html"
    extra = raw["extra"]
    assert extra["authorization_status"] == "pending"
    request = extra["authorization_request"]
    assert "2026-11-08" in request
    assert "formulaire" in request
    assert extra.get("scraping_consent") in (None, "")


def test_dead_contacts_are_not_relayed_as_live() -> None:
    """The museum's official mailboxes bounce; they must not be listed as active."""
    extra = _raw()["extra"]
    assert not extra.get("scraping_consent")
    dead = " ".join(extra.get("dead_contacts") or [])
    assert "wanadoo.fr" in dead
    # the only relay that did not bounce is the regional natural park
    assert "parc-vosges-nord.fr" in (extra.get("live_relay") or "")


def test_connector_is_registered_and_built() -> None:
    descriptor = _descriptor()
    assert CONNECTORS["musee_petrole_pechelbronn"] is MuseePetrolePechelbronnConnector
    connector = build_connector(descriptor, _FakeHttp())
    assert isinstance(connector, MuseePetrolePechelbronnConnector)


@pytest.mark.asyncio
async def test_search_abstains_without_network() -> None:
    connector = MuseePetrolePechelbronnConnector(_descriptor(), _FakeHttp())
    assets = await connector.search("pétrole")
    assert assets == []
