"""Library of Congress — Prints & Photographs (all periods), via the loc.gov JSON API.

Sister source of :mod:`mnemosyne.sources.loc_wwi_photos`, but scoped to the whole
Prints & Photographs Online Catalog (PPOC, ``https://www.loc.gov/pictures/``)
rather than the single World War I collection. It targets any period and subject
— notably the American petroleum industry and oil-well fires/blowouts (gushers
on fire, fire-control crews such as Myron Kinley, Texas oil) that the WWI-scoped
catalogue cannot reach.

The wire format is identical to the WWI connector: the public, keyless JSON
search API (``?fo=json``) returns a ``results[]`` array whose entries carry the
item page URL (``id``/``url``) and an ordered list of ``image_url`` derivatives on
``tile.loc.gov``. Only the descriptor's ``base_url`` (PPOC instead of the WWI
collection) and the search seeds differ, so the proven parsing — normalize to
the canonical :class:`Asset`, never leak the provider shape — is reused verbatim.
No HTML scraping: the documented JSON endpoint is the sole access path.
"""

from __future__ import annotations

from mnemosyne.sources.loc_wwi_photos import LocWwiPhotosConnector


class LocPpConnector(LocWwiPhotosConnector):
    """Search the full LoC Prints & Photographs catalog (any period/subject).

    Same loc.gov JSON wire format as :class:`LocWwiPhotosConnector`; the
    difference is entirely configuration (PPOC ``base_url`` and broader seeds
    live in ``config/sources/loc_pp.yaml``). Inheriting keeps a single, tested
    implementation of the loc.gov result parser for both sister sources.
    """
