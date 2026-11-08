"""Connector for the Musée français du pétrole (Merkwiller-Pechelbronn).

The museum keeps an era photothèque of the Pechelbronn oilfield — wells,
derricks, installations and flares — which is exactly the material the resolver
wants for the “pétrole français oublié” sentence (cementing, flare, lost well).
It publishes that collection through a WebMuseo portal at
https://www.musee-du-petrole.com/ but exposes **no programmatic access**: no
REST/JSON API, no IIIF, SRU, OAI-PMH or SPARQL endpoint.

Project policy (AGENTS.md, ``docs/SOURCES.md``) forbids a network scraper unless
**written consent** is on file under ``extra.scraping_consent``. That
authorization is still *pending* — see the descriptor's
``extra.authorization_request``. The source is therefore declared
``enabled: false`` and this connector deliberately **abstains**: ``search``
returns no asset until a documented access method *and* a reusable licence are
secured. It never performs any network I/O.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset


class MuseePetrolePechelbronnConnector(Connector):
    """Abstaining connector for a source with no lawful programmatic access yet.

    The descriptor is disabled; even if it were enabled by mistake, ``search``
    returns an empty result set instead of scraping, so no request is ever sent
    to the museum portal.
    """

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        # No public API and no written scraping consent: the connector abstains.
        return []
