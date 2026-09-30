"""Provider registry: maps a source id to its connector implementation."""

from __future__ import annotations

from mnemosyne.connectors.base import Connector
from mnemosyne.http import HttpClient
from mnemosyne.models import SourceDescriptor
from mnemosyne.sources.europeana import EuropeanaConnector
from mnemosyne.sources.gallica import GallicaConnector
from mnemosyne.sources.internet_archive import InternetArchiveConnector
from mnemosyne.sources.openverse import OpenverseConnector
from mnemosyne.sources.wikidata import WikidataConnector
from mnemosyne.sources.wikimedia import WikimediaConnector

CONNECTORS: dict[str, type[Connector]] = {
    "gallica": GallicaConnector,
    "wikidata": WikidataConnector,
    "wikimedia": WikimediaConnector,
    "internet_archive": InternetArchiveConnector,
    "openverse": OpenverseConnector,
    "europeana": EuropeanaConnector,
}


def build_connector(descriptor: SourceDescriptor, http: HttpClient) -> Connector | None:
    cls = CONNECTORS.get(descriptor.id)
    return cls(descriptor, http) if cls else None


def supported_source_ids() -> list[str]:
    return sorted(CONNECTORS)


__all__ = ["CONNECTORS", "build_connector", "supported_source_ids"]
