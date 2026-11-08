"""IFPEN / Institut français du pétrole — no public photo archive (stub).

Recon (2026-11-08) found that IFPEN's official site (a Drupal CMS at
ifpenergiesnouvelles.fr) exposes **no** public photographic archive and **no**
media/JSON/IIIF API for its historical petroleum photographs (exploitation in
Parentis-en-Born, Lacq, the Paris Basin, and mobile Schlumberger-style drilling
crews). Tested paths (``/phototheque``, ``/mediatheque``, ``/medias``,
``/phototheque-historique``, ``/notre-histoire``, ``/histoire``,
``/patrimoine``, ``/galerie-photos``) all return 404; the only "archive" is
HAL-IFP (scientific publications, no photos); FranceArchives' IFP authority
record returns only building/urbanism material (CAPA), and POP / ANMT / Gallica
carry no IFP petroleum-field photography set.

This connector is therefore intentionally inert: it normalises nothing and
returns no assets. The descriptor stays ``enabled: false`` so the engine never
queries it. The French petroleum imagery the adversarial resolver needs is
served by the sibling ``ia_esso_petrole`` source (ESSO France corpus on the
Internet Archive). Reactivating IFPEN is a one-line change once the Foundation
grants a public/API endpoint or written reuse authorisation for its historical
photothèque (see docs/OUTREACH.md).
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset


class IfpenPetroleConnector(Connector):
    """Inert connector: IFPEN publishes no addressable photo archive."""

    async def search(
        self, query: str, limit: int = 20, **filters: Any
    ) -> list[Asset]:
        # No public API / photo archive exists at IFPEN: nothing to normalise.
        return []

    async def health(self) -> bool:
        return False
