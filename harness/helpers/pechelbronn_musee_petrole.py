"""Musée français du Pétrole (Merkwiller-Pechelbronn) — WP REST API reference.

Source: https://www.musee-du-petrole.com/  (WordPress).
Researched by the navigator agent (mnemosyne) for the catalogue source
``musee_petrole_pechelbronn`` (adversarial-resolver phrase: a French oil well /
Pechelbronn, "ciment + torche => puits foutu").

API
---
The site exposes the public WordPress REST API (open, GET, NO auth, JSON)::

    {ORIGIN}/wp-json/wp/v2/media?search=<term>&per_page=100&page=<n>

Useful per-media fields: id, date (WP *upload* date, NOT the capture date),
slug, title.rendered, caption.rendered, description.rendered, alt_text,
media_type, mime_type, source_url (direct, hot-linkable file URL),
media_details, parent.  ``/posts`` and ``/pages`` are also open.

Known limitations
-----------------
- Metadata is VERY thin: titles are derived from the filename; caption / alt /
  description are empty; no photographer, no capture date, no rights field.
- ``per_page`` is capped at 100. The ``mime_type=image`` filter is NOT applied
  server-side — filter client-side on ``mime_type.startswith("image")``.
- ``"derrick"`` yields 0 hits; prefer ``"pechelbronn"``, ``"puits"``, ``"sonde"``.

Licensing (BLOCKER)
-------------------
Every image is "Tous droits réservés" (musée © / photos © Association des Amis
du Musée du Pétrole). Reproduction / re-hosting requires WRITTEN permission. The
linked WebMuseo portal (webmuseo.com/ws/musees-parc-vosges-nord/) returns 403
on ``/app/collection/*`` and exposes no OAI-PMH endpoint.

This module only *reads* the open API (GET) to catalogue / verify visuals; it
never bypasses the rights. A curated inventory of historic heroes (wells,
derricks, drilling, refinery) is provided as an anchor for that research.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

ORIGIN = "https://www.musee-du-petrole.com"
API = ORIGIN + "/wp-json/wp/v2"
USER_AGENT = "mnemosyne-research/1.0 (+https://github.com/Antonio-Faure/mnemosyne)"

# Search terms that return useful results on this API ("derrick" -> 0 hits).
HISTORIC_TERMS = (
    "pechelbronn",
    "puits",
    "sonde",
    "chevalement",
    "raffinerie",
    "distillerie",
    "schlumberger",
)

# Curated historic visuals: WP media id -> short note (era / subject).
HISTORIC_HEROES = {
    1436: "Derrick / chevalement (06pechelbronn_cherot)",
    464: "Derrick / chevalement, série Antar",
    4285: "Puits n°1 (carreau Clemenceau), années 1920",
    1419: "Puits d'exploitation, années 1920",
    1832: "Installation de forage",
    1092: "Sondage au câble et au treuil, 5 sept. 1927",
    806: "Carottage Schlumberger, 1928-1929",
    4380: "Vue aérienne de la raffinerie (2e Guerre mondiale)",
    4125: "Ancienne distillerie",
    462: "Raffinerie / installations de surface",
    813: "Carte postale d'époque — installations",
    1105: "Carte postale d'époque",
    1430: "Vue d'époque du site pétrolifère",
    1124: "Installations — figure d'époque",
    460: "Conrad Schlumberger",
    4657: "Château Lebel",
    2310: "Aquarelle Sauer (vue du site)",
}


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET a WP REST endpoint and return parsed JSON (list or dict)."""
    query = ""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            query = "?" + urllib.parse.urlencode(clean)
    url = API + path + query
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wp_media_search(
    term: str,
    per_page: int = 100,
    page: int = 1,
    images_only: bool = True,
    fields: str | None = None,
) -> list[dict[str, Any]]:
    """Search media via /media. Returns a list of media dicts (images only)."""
    params: dict[str, Any] = {
        "search": term,
        "per_page": max(1, min(int(per_page), 100)),
        "page": max(1, int(page)),
        "_fields": fields,
    }
    data = _get("/media", params)
    if not isinstance(data, list):
        return []
    if images_only:
        data = [
            media for media in data
            if str(media.get("mime_type", "")).startswith("image")
        ]
    return data


def resolve_ids(
    ids: list[int],
    fields: str | None = "id,source_url,title,date,mime_type,media_details",
) -> list[dict[str, Any]]:
    """Fetch specific media records by id (single request, include=...)."""
    clean_ids = [int(i) for i in ids]
    if not clean_ids:
        return []
    params = {
        "include": ",".join(str(i) for i in clean_ids),
        "per_page": min(len(clean_ids), 100),
        "_fields": fields,
    }
    data = _get("/media", params)
    return data if isinstance(data, list) else []


def hero_records() -> list[dict[str, Any]]:
    """Resolve the curated HISTORIC_HEROES ids to full media records."""
    return resolve_ids(list(HISTORIC_HEROES))


def historic_inventory(per_term: int = 100) -> list[dict[str, Any]]:
    """Run all HISTORIC_TERMS searches and return deduplicated media."""
    seen: dict[Any, dict[str, Any]] = {}
    for term in HISTORIC_TERMS:
        for media in wp_media_search(term, per_page=per_term):
            seen[media.get("id")] = media
    return list(seen.values())
