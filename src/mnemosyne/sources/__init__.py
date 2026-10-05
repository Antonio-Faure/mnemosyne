"""Provider registry: maps a source id to its connector implementation."""

from __future__ import annotations

from mnemosyne.connectors.base import Connector
from mnemosyne.http import HttpClient
from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.anmt import AnmtConnector
from mnemosyne.sources.archives_nord import ArchivesNordConnector
from mnemosyne.sources.cleveland import ClevelandConnector
from mnemosyne.sources.dpla import DplaConnector
from mnemosyne.sources.europeana import EuropeanaConnector
from mnemosyne.sources.gallica import GallicaConnector
from mnemosyne.sources.iiif import IIIFConnector
from mnemosyne.sources.internet_archive import InternetArchiveConnector
from mnemosyne.sources.openverse import OpenverseConnector
from mnemosyne.sources.pop import PopConnector
from mnemosyne.sources.smithsonian import SmithsonianConnector
from mnemosyne.sources.wikidata import WikidataConnector
from mnemosyne.sources.wikimedia import WikimediaConnector

#: exact connector per source id
CONNECTORS: dict[str, type[Connector]] = {
    "anmt": AnmtConnector,
    "archives_nord": ArchivesNordConnector,
    "cleveland": ClevelandConnector,
    "gallica": GallicaConnector,
    "wikidata": WikidataConnector,
    "wikimedia": WikimediaConnector,
    "internet_archive": InternetArchiveConnector,
    "openverse": OpenverseConnector,
    "europeana": EuropeanaConnector,
    "dpla": DplaConnector,
    "smithsonian": SmithsonianConnector,
    "pop": PopConnector,
}

#: fallback connector by protocol (used by discovered sources, e.g. IIIF hosts)
PROTOCOL_CONNECTORS: dict[Protocol, type[Connector]] = {
    Protocol.IIIF: IIIFConnector,
}


def build_connector(descriptor: SourceDescriptor, http: HttpClient) -> Connector | None:
    cls = CONNECTORS.get(descriptor.id)
    if cls is None:
        cls = PROTOCOL_CONNECTORS.get(descriptor.protocol)
    return cls(descriptor, http) if cls else None


__all__ = ["CONNECTORS", "PROTOCOL_CONNECTORS", "build_connector"]
