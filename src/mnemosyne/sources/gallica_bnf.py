"""Gallica (BnF) — presse & photographie: SRU search + IIIF, image-tagged.

Resolver-facing "press & photography" variant of the generic ``gallica``
connector. It speaks the same protocol (Gallica's official SRU search API
returning Dublin Core notices, images served through IIIF) so no HTML scraping
is involved, and it reuses the proven SRU→:class:`Asset` normalization of
:class:`~mnemosyne.sources.gallica.GallicaConnector`.

The only behavioural difference is provenance tagging: ``dc:type`` and
``dc:subject`` from each SRU notice are lifted onto ``Asset.tags`` so the
catalog and the resolver can tell photographs and press engravings (e.g.
*Le Petit Journal*, *L'Illustration*) apart from text-only books, and every
asset is marked as the ``press-photography`` face of Gallica.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from mnemosyne.models import Asset
from mnemosyne.sources.gallica import GallicaConnector, _texts


class GallicaBnfConnector(GallicaConnector):
    """BnF Gallica — press & photographic collections (SRU + IIIF)."""

    #: id of the parent, generic Gallica source this connector specializes
    variant_of = "gallica"

    def _parse_record(self, record: ET.Element) -> Asset | None:
        asset = super()._parse_record(record)
        if asset is None:
            return None
        tags: list[str] = []
        for value in (*_texts(record, "type"), *_texts(record, "subject")):
            value = value.strip()
            if value and value not in tags:
                tags.append(value)
        if tags:
            asset.tags = tags[:10]
        asset.extra = {
            **asset.extra,
            "connector": "gallica-bnf",
            "variant_of": self.variant_of,
        }
        return asset
