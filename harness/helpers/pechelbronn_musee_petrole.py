"""Musée français du Pétrole — Merkwiller-Pechelbronn (photothèque / collections).

Access reference discovered by the navigator agent (mnemosyne), task #177.

WHY THIS SOURCE
---------------
The adversarial resolver wants a genuine, *freely reusable* photograph of a
French oil well / derrick / field installation for the phrase
« Ils ont coulé du ciment, installé une torche, mais du coup le puits, il est
foutu, non ? » (vidéo « la France a du pétrole mais elle la oublié »).
Pechelbronn (Bas-Rhin) is the cradle of French oil (exploited ~18th c. → 1970).
Le catalogue ne contient AUCUNE photo libre de puits/derrick pétrolier
français : Europeana/Gallica = cartes postales/dessins (NoC-OKLR), DPLA =
In Copyright, Wikimedia = prises modernes (musée/mémorial). Ce musée conserve
la photothèque d'époque (puits, chevalements/derricks, raffinerie, torchères,
cartes postales, figures). C'est la source la plus pertinente — MAIS sous
droits réservés (voir LICENCE).

TECHNICAL SURFACES (verified 2026)
----------------------------------
1) musee-du-petrole.com — WordPress REST API (OPEN, JSON, no auth, reads 200)
   Base: https://www.musee-du-petrole.com/wp-json/wp/v2
   - /media   (1109 items; per_page MAX 100 -> 12 pages; per_page=200 -> HTTP 400)
        params: search=<keyword>, per_page, page, _fields=..., mime_type,
                media_type, after/before (ISO dates), parent, orderby, order
        fields: id, date, slug, title.rendered, caption.rendered,
                description.rendered, alt_text, media_type, mime_type,
                source_url (direct file), media_details{width,height,sizes{}},
                post (attached article id)
        NB: metadata THIN — titles are filename-derived; caption/alt/description
            are empty (no photographer, no date-of-origin, no rights field).
        NB: mime_type=image does NOT filter server-side; filter client-side
            (mime_type.startswith('image')).
   - /posts, /pages   (articles/pages; historic images are embedded in history
        articles). Example: media 4380 attached to post 2067.
   Direct image files are served from /wp-content/uploads/... and are hot-linkable.

2) webmuseo.com/ws/musees-parc-vosges-nord/  — the REAL catalogued collections
   portal (WebMuseo by A&A Partners) for the 10 museums of the Parc naturel
   régional des Vosges du Nord, incl. Musée du Pétrole. Inventory numbers like
   PECH_2013-1-2, PECH_1997-0-184 (PECH = Pechelbronn).
   - Editorial/report pages are OPEN (HTML):
       /app/report/index.html, decouvrir-les-collections.html, credits.html,
       mentions-legales.html
   - /app/collection (search, notice, expo, sitemap) -> HTTP 403 "Accès protégé"
       (OGO Security bot wall). NOT programmatically accessible; do not force.
   - /oai and /oai?verb=Identify -> HTTP 404 (no OAI-PMH endpoint).
   Legacy per-museum subdomain musee-petrole.webmuseo.com no longer resolves.

LICENCE (the blocker)
---------------------
- musee-du-petrole.com/mentions-legales/ : « Musée du Pétrole © 2026 »,
  crédits photos Association des Amis du Musée du Pétrole ; aucune licence libre.
- Parc/WebMuseo mentions légales: « Les photographies … sont la propriété de
  l'éditeur du site ou de tiers … Toute reproduction ou représentation, en tout
  ou en partie, à d'autres fins sur un quelconque support est interdite …
  contrefaçon. »
=> ALL RIGHTS RESERVED on both surfaces. NOT freely reusable. Cannot be ingested
   / re-hosted in an open aggregator without WRITTEN permission from the museum.

PERMISSION REQUEST (sent)
-------------------------
By the museum being a small structure whose images are © reserved, the sanctioned
path is a written permission request (never scrape the rights-held images).
Email sent from archivist.mnemosyne@gmail.com to:
  To : museedupetrole@wanadoo.fr
  Cc : musee.petrole@musees-vosges-nord.org, contact@parc-vosges-nord.fr
Subject: Demande d'autorisation — réutilisation d'images historiques de Pechelbronn
Asked for: (1) written authorisation, (2) a reuse licence (CC BY / CC BY-SA 4.0
or public-domain confirmation) + exact credit line, (3) official API / OAI / IIIF
/ open-data access (or OK to use the wp-json media API + WebMuseo portal).

USAGE
-----
Call from inside browser(): navigate first to https://www.musee-du-petrole.com/
(same-origin fetch required), then e.g. wp_media_search("Pechelbronn").

Inventory numbers can be reused as-is (PECH_yyyy-…); direct URLs are in
HISTORIC_HEROES below.
"""

from __future__ import annotations

import json

from browser_harness.helpers import js

ORIGIN = "https://www.musee-du-petrole.com"
API = ORIGIN + "/wp-json/wp/v2"

# Curated, phrase-relevant historic items (verified ids + direct file URLs).
# Pechelbronn field: wells, headframes/derricks, drilling, refinery, postcards,
# historic figures. weight = theme fit for the video phrase (my judgement).
HISTORIC_HEROES = [
    # --- wells / derricks / drilling (the core of the phrase) ---
    {"id": 1436, "title": "06pechelbronn_cherot", "weight": 5,
     "url": ORIGIN + "/wp-content/uploads/2019/02/06pechelbronn_cherot.jpg",
     "note": "Chevalement/derrick du champ de Pechelbronn (chevalement = headframe)"},
    {"id": 464, "title": "06pechelbronn-cherot_Antar", "weight": 5,
     "url": ORIGIN + "/wp-content/uploads/2015/03/06pechelbronn-cherot_Antar.jpg",
     "note": "Même chevalement, variante Antar"},
    {"id": 4285, "title": "Carreau-de-Mine-Clemenceau_Puits-1_annees-1920", "weight": 5,
     "url": ORIGIN + (
         "/wp-content/uploads/2024/04/Carreau-de-Mine-Clemenceau_Puits-1_annees-1920-scaled.jpg"),
     "note": "Puits I du carreau Clemenceau, années 1920 (2560x1932)"},
    {"id": 1419, "title": "016 Puits I a2", "weight": 4,
     "url": ORIGIN + "/wp-content/uploads/2019/02/016-Puits-I-a2-scaled.jpg",
     "note": "Puits I (2560x1684)"},
    {"id": 1832, "title": "carreau mines_ Puits I-01 Terril", "weight": 3,
     "url": ORIGIN + "/wp-content/uploads/2020/02/carreau-mines_-Puits-I-01-Terril.jpg",
     "note": "Puits I et terril"},
    {"id": 1092, "title": "5 sept 1927_Pechelbronn câble et treuil", "weight": 4,
     "url": ORIGIN + "/wp-content/uploads/2015/03/5-sept-1927_Pechelbronn-câble-et-treuil.jpg",
     "note": "Forage : câble et treuil, 1927"},
    {"id": 806, "title": "Bayle et Sauvage au potentiomètre en Alsace_1928-29", "weight": 3,
     "url": ORIGIN + (
         "/wp-content/uploads/2015/02/Bayle-et-Sauvage"
         "-avec-le-potentiomètre-en-Alsace_1928-29.jpg"),
     "note": "Premier carottage électrique (Schlumberger), 1928-29"},
    {"id": 3808, "title": "PECH_20230708 transfert pompe à balancier Durrenbach", "weight": 2,
     "url": ORIGIN + (
         "/wp-content/uploads/2023/07/"
         "PECH_20230708__transfert_pompe_balancier_Durrenbach-23-002-scaled.jpg"),
     "note": "Pompe à balancier (pumpjack) — photo de transfert RÉCENTE (2023), pas d'époque"},
    # --- refinery / installations ---
    {"id": 462, "title": "vue de la raffinerie", "weight": 4,
     "url": ORIGIN + "/wp-content/uploads/2015/03/vue-de-la-raffinerie-scaled.jpg",
     "note": "Vue de la raffinerie de Pechelbronn (2560x951)"},
    {"id": 4380,
     "title": "carte-postale apres reconstruction 2WW vue aerienne raffinerie",
     "weight": 3,
     "url": ORIGIN + (
         "/wp-content/uploads/2024/07/"
         "carte-postale-apres-reconstruction-2WW_vue-aerienne-raffinerie-de-Pechelbronn_CollectionM"
         "FDP.jpg"),
     "note": "Carte postale aérienne de la raffinerie (Collection MFDP)"},
    {"id": 4125, "title": "ancienne distillerie d'huile brute_CollectionMFDP", "weight": 3,
     "url": ORIGIN + (
         "/wp-content/uploads/2024/02/ancienne-distillerie-dhuile-brute_CollectionMFDP.jpg"),
     "note": "Ancienne distillerie d'huile brute (Collection MFDP)"},
    # --- postcards / historic figures / art / objects ---
    {"id": 813, "title": "carte postale", "weight": 3,
     "url": ORIGIN + "/wp-content/uploads/2015/02/carte-postale.jpg",
     "note": "Carte postale ancienne Pechelbronn"},
    {"id": 1105, "title": "Joseph Kautzmann par Simone, mineur 1920", "weight": 3,
     "url": ORIGIN + "/wp-content/uploads/2015/03/Joseph-Kautzmann-par-Simone-_mineur-1920.jpg",
     "note": "Mineur, 1920"},
    {"id": 1430, "title": "louis Hepting vendeur de graisse ambulant_1er mitié 20e s", "weight": 2,
     "url": ORIGIN + (
         "/wp-content/uploads/2019/02/"
         "louis-Hepting_vendeur-de-graisse-ambulant-de-Pechelbronn_1er-mitoié-20e-s-scaled.jpg"),
     "note": "Vendeur de graisse ambulant, début XXe"},
    {"id": 1124, "title": "publicité Antar Pechelbronn", "weight": 2,
     "url": ORIGIN + "/wp-content/uploads/2015/03/publicité-Antar-Pechelbronn.jpg",
     "note": "Publicité Antar (3509x2550)"},
    {"id": 460, "title": "Conrad Schlumberger 1878-1936", "weight": 2,
     "url": ORIGIN + "/wp-content/uploads/2015/03/Conrad-Schlumberger_1878-1936.jpg",
     "note": "Portrait Conrad Schlumberger"},
    {"id": 4657, "title": "Château Lebel b1", "weight": 1,
     "url": ORIGIN + "/wp-content/uploads/2025/03/Chateau-Lebel-b1.jpg",
     "note": "Château Le Bel (siège historique)"},
    {"id": 2764, "title": "Medaille Le Bel PECH_1997-0-184", "weight": 1,
     "url": ORIGIN + "/wp-content/uploads/2021/04/Medaille-Le-Bel-PECH_1997-0-184.jpg",
     "note": "Médaille Le Bel (coll. PECH_1997-0-184)"},
    {"id": 2310, "title": "Aquarelle Sauer_1 PECH_2013-1-2", "weight": 1,
     "url": ORIGIN + "/wp-content/uploads/2020/12/Aquarelle-Sauer_1-PECH_2013-1-2.jpg",
     "note": "Aquarelle Théo Sauer (friche industrielle) — œuvre moderne"},
]

# Search terms that reliably surface the historic subset in the media library.
HISTORIC_TERMS = [
    "Pechelbronn", "carte postale", "mine", "puits", "raffinerie", "distillerie",
    "pompe", "balancier", "forage", "Antar", "Le Bel", "Boussingault", "Sauer",
    "aquarelle", "medaille", "CollectionMFDP", "PECH_", "1927", "1928", "1920",
    "clemenceau", "carreau", "terril", "treuil", "cherot",
]


def _origin_ok() -> bool:
    return (js("location.origin") or "").strip() == ORIGIN


def wp_media_search(term: str, per_page: int = 100, page: int = 1,
                    images_only: bool = True) -> list[dict]:
    """Search the museum WP media library. MUST be called on the museum origin.

    Returns a list of compact dicts: id, title, date, mime, w, h, url, post.
    """
    if not _origin_ok():
        raise RuntimeError("Navigate to " + ORIGIN + " first (same-origin fetch).")
    path = (f"/wp-json/wp/v2/media?per_page={int(per_page)}&page={int(page)}"
            f"&search=" + __import__("urllib.parse", fromlist=["quote"]).quote(term)
            + "&_fields=id,date,title,caption,media_type,mime_type,source_url,media_details,post")
    raw = js(
        "(async()=>{const r=await fetch(" + json.dumps(path) + ");"
        "if(!r.ok)return JSON.stringify({__error__:r.status});"
        "return await r.text();})()"
    )
    data = json.loads(raw)
    if isinstance(data, dict) and "__error__" in data:
        raise RuntimeError(f"WP media HTTP {data['__error__']} for term={term!r}")
    out = []
    for m in data:
        md = m.get("media_details") or {}
        if images_only and not (m.get("mime_type", "") or "").startswith("image"):
            continue
        out.append({
            "id": m.get("id"),
            "title": (m.get("title") or {}).get("rendered", ""),
            "date": (m.get("date") or "")[:10],
            "mime": m.get("mime_type", ""),
            "w": md.get("width"), "h": md.get("height"),
            "url": m.get("source_url", ""),
            "post": m.get("post"),
        })
    return out


def historic_inventory(per_term: int = 50) -> list[dict]:
    """Aggregate + de-duplicate historic Pechelbronn images across HISTORIC_TERMS."""
    seen = {}
    for t in HISTORIC_TERMS:
        for m in wp_media_search(t, per_page=per_term):
            seen[m["id"]] = m
    return sorted(seen.values(), key=lambda x: x["date"], reverse=True)
