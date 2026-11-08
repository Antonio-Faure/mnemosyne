"""Provider registry: maps a source id to its connector implementation."""

from __future__ import annotations

from mnemosyne.connectors.base import Connector
from mnemosyne.http import HttpClient
from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.anmt import AnmtConnector
from mnemosyne.sources.cleveland import ClevelandConnector
from mnemosyne.sources.contentdm import ContentDmConnector
from mnemosyne.sources.cooper_hewitt import CooperHewittConnector
from mnemosyne.sources.digital_commonwealth import DigitalCommonwealthConnector
from mnemosyne.sources.digitalnz import DigitalNzConnector
from mnemosyne.sources.dpla import DplaConnector
from mnemosyne.sources.eol import EolConnector
from mnemosyne.sources.europeana import EuropeanaConnector
from mnemosyne.sources.gallica import GallicaConnector
from mnemosyne.sources.gbif import GbifConnector
from mnemosyne.sources.ia_esso_petrole import IaEssoPetroleConnector
from mnemosyne.sources.ifpen_petrole import IfpenPetroleConnector
from mnemosyne.sources.iiif import IIIFConnector
from mnemosyne.sources.inaturalist import INaturalistConnector
from mnemosyne.sources.internet_archive import InternetArchiveConnector
from mnemosyne.sources.japan_search import JapanSearchConnector
from mnemosyne.sources.loc_wwi_photos import LocWwiPhotosConnector
from mnemosyne.sources.mai_saint_etienne import MAISaintEtienneConnector
from mnemosyne.sources.met import MetConnector
from mnemosyne.sources.musee_petrole_pechelbronn import MuseePetrolePechelbronnConnector
from mnemosyne.sources.nasa import NasaConnector
from mnemosyne.sources.nb_no import NbNoConnector
from mnemosyne.sources.openverse import OpenverseConnector
from mnemosyne.sources.pop import PopConnector
from mnemosyne.sources.smithsonian import SmithsonianConnector
from mnemosyne.sources.texas_history import TexasHistoryConnector
from mnemosyne.sources.wikidata import WikidataConnector
from mnemosyne.sources.wikimedia import WikimediaConnector
from mnemosyne.sources.wikimedia_commons_photos import WikimediaCommonsPhotosConnector

#: exact connector per source id
CONNECTORS: dict[str, type[Connector]] = {
    "anmt": AnmtConnector,
    "atlanta": ContentDmConnector,
    "auc": ContentDmConnector,
    "byu": ContentDmConnector,
    "carli": ContentDmConnector,
    "cleveland": ClevelandConnector,
    "cooper_hewitt": CooperHewittConnector,
    "digital_commonwealth": DigitalCommonwealthConnector,
    "digitalnz": DigitalNzConnector,
    "dpla": DplaConnector,
    "eol": EolConnector,
    "europeana": EuropeanaConnector,
    "gallica": GallicaConnector,
    "gbif": GbifConnector,
    "hennepin": ContentDmConnector,
    "hillsborough": ContentDmConnector,
    "wikidata": WikidataConnector,
    "wikimedia": WikimediaConnector,
    "wikimedia_commons_photos": WikimediaCommonsPhotosConnector,
    "internet_archive": InternetArchiveConnector,
    "ia_esso_petrole": IaEssoPetroleConnector,
    "ifpen_petrole": IfpenPetroleConnector,
    "japan_search": JapanSearchConnector,
    "loc_wwi_photos": LocWwiPhotosConnector,
    "inaturalist": INaturalistConnector,
    "openverse": OpenverseConnector,
    "scdl": ContentDmConnector,
    "smithsonian": SmithsonianConnector,
    "texas_history": TexasHistoryConnector,
    "teva": ContentDmConnector,
    "mai_saint_etienne": MAISaintEtienneConnector,
    "met": MetConnector,
    "musee_petrole_pechelbronn": MuseePetrolePechelbronnConnector,
    "nasa": NasaConnector,
    "nb_no": NbNoConnector,
    "north_dakota": ContentDmConnector,
    "penn_state": ContentDmConnector,
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
