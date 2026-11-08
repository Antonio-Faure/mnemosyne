r"""Pechelbronn / Musee Français du Pétrole — fonds pétrolier d'Alsace (mnemosyne task #189).

Navigator reconnaissance. Read-only reference the coder uses to build the
`config/sources/pechelbronn_petrole.yaml` descriptor + connector. Every function
here only GETs and parses; nothing writes to the remote, and NO HTML is scraped
for images — image data comes only from the open JSON (WordPress REST) endpoint.

WHY THIS SOURCE
---------------
The adversarial resolver ("yt_la_france_a_du_petrole_mais_elle_la_oublie") found
ZERO French-oil images in the catalogue (Gallica/Europeana/ANMT -> empty on
"pétrole"). Pechelbronn (Merkwiller-Pechelbronn, Bas-Rhin) is the oldest
exploited oil field in Europe (extraction 18th c. -> 1970; first mechanical
drilling 1879 by J. A. Le Bel; birth of Antar and of the Institut Français du
Pétrole on site). The museum holds the region's petroleum fonds: derricks,
drilling rigs ("câble et treuil"), well-heads ("puits"), nodding-donkeys
("pompe à balancier"), the refinery, mine galleries, workers/technicians,
cartes postales, Antar advertising.

ACCESS PATH  (verified 2026-03, server-side `requests`, bot UA == 200)
----------------------------------------------------------------------
* The site is a WordPress install. There is NO IIIF, NO dedicated collection
  API, NO Museofile/POP record (POP `bases[0]=museo` "Pechelbronn" -> 0 hits;
  the only "pétrole" museo hit is Montmorency/Rousseau, unrelated).
* The ONLY programmatic surface is the **WordPress REST media API** — open,
  keyless, JSON:
        GET https://www.musee-du-petrole.com/wp-json/wp/v2/media
  Read-only GET answers any User-Agent (browser fetch AND a plain `requests`
  GET with the mnemosyne bot UA both returned 200 application/json).
  robots.txt disallows only /wp-admin/ (Sitemap: /wp-sitemap.xml).

  Useful query params (all confirmed):
     media_type=image        restrict to images (excludes PDFs/brochures)  -> X-WP-Total = 913
     mime_type=image/jpeg    811 jpeg / 98 png
     per_page=100            page size (WP caps at 100)
     page=N                  1-based page; paginate on header X-WP-TotalPages
     search=<text>           substring match over title/caption/description
     _fields=id,title,source_url,media_details,date,link   trim payload
  Totals come back in response headers: X-WP-Total, X-WP-TotalPages.

WHAT IS IN THERE
----------------
900 image records enumerable via media_type=image. Composition:
  * 62 items carry a museum INVENTORY CODE in the title  ("PECH_2019-2-147_1",
    "PECH_2014-2-4_1", "PECH_1997.0.256", ... )  -> the catalogued objects
    (photographs, postcards, medals, models, Théo Sauer watercolours, ...).
  * 102 items survive the archival filter below (is_archival) -> the usable
    photographic/object fonds. Flagships it captures:
       - "5 sept 1927_Pechelbronn câble et treuil"            (drilling rig/winch)
       - "Carreau-de-Mine-Clemenceau_Puits-1_annees-1920"     (well-head, 1920s)
       - "PECH_20230708__transfert_pompe_balancier_Durrenbach" (nodding-donkey pump)
       - "ancienne distillerie d'huile brute_CollectionMFDP"
       - "carte-postale-apres-reconstruction-2WW_vue-aerienne-raffinerie-de-Pechelbronn"
       - "louis Hepting_vendeur de graisse ambulant de Pechelbronn_1er mitoié 20e s"
       - "carte postale cité"  (workers' housing estate)
       - ~18 "ImageX_Antar" / "publicité Antar Pechelbronn"  (Antar brand history)
  * the rest are modern site media (dépliants, logos, banners, Facebook event
    photos, ateliers) -> excluded by is_archival()'s denylist.

FIELD MAPPING  (media record -> catalogue record)
-------------------------------------------------
  id                     -> external id  (stable, WP media id)
  title.rendered         -> title / label AND the depicted-date + subject
                            (SOME titles encode the historical date, e.g.
                            "1927", "annees-1920", "1er mitoié 20e s").
                            inventory code regex: r"PECH[_\-\s.]?\d"
  caption/description/alt.rendered -> usually EMPTY; append when present
  source_url             -> image_url (origin file, hotlink target)
  media_details.width/height -> dimensions
  media_details.sizes.{medium_large|large|medium|thumbnail}.source_url
                         -> thumbnail / display size
  link                   -> record_url (the object page). CAVEAT: some 404 now
                            (e.g. the 1927 treuil attachment page) -> fall back
                            to MUSEUM_URL / the collections page.
  date                   -> UPLOAD date, NOT the depicted date. Do NOT treat as
                            the historical year; take the year from the title.

RIGHTS / CREDIT
---------------
© Musée Français du Pétrole, Merkwiller-Pechelbronn — "tous droits réservés"
(site footer). NO open licence. mnemosyne's model applies: index + point back
(link to the museum / object page), display with the credit line, and NEVER
copy or re-host the image. Suggested credit:
    "© Musée Français du Pétrole – Merkwiller-Pechelbronn"
Suggested source link: https://www.musee-du-petrole.com/
Because the museum is a small association with no open licence, a courtesy
outreach (docs/OUTREACH.md) telling them we index + link back is appropriate,
BUT the WP REST API is public and keyless so this is NOT a gated-access source.

SECONDARY / AUGMENTING LEAD (not the assigned source, FYI for the resolver)
---------------------------------------------------------------------------
POP (api.pop.culture.gouv.fr, already in the catalogue via pop_api.py) DOES
carry French-oil material the resolver did not test:
    bases[0]=joconde  text="pétrole"     -> 136 notices
    bases[0]=memoire  text="Pechelbronn" ->  70 notices (Inventaire Général
                         architectural photos of the commune, IIIF-served)
These are a standard, IIIF-backed augmenting path if more volume is wanted; the
assigned `pechelbronn_petrole` source stays on the museum's own fonds.
"""

from __future__ import annotations

import re

import requests

MUSEUM_URL = "https://www.musee-du-petrole.com/"
MEDIA_ENDPOINT = MUSEUM_URL + "wp-json/wp/v2/media"
COLLECTIONS_URL = MUSEUM_URL + "le-musee-petrole-merkwiller-pechelbronn/les-collections/"
UA = (
    "mnemosyne-research-bot/1.0 "
    "(+https://github.com/Antonio-Faure/mnemosyne; open-source research aggregator)"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json, */*;q=0.8"}
CREDIT = "© Musée Français du Pétrole – Merkwiller-Pechelbronn"

# Archival inclusion / modern-junk exclusion (validated: 102 hits over 900 images).
_INC = re.compile(
    r"(\bPECH[_\-\s.]?\d|puits|forage|sonde|derrick|treuil|raffinerie|distill|"
    r"pompe|balancier|chevalement|carottage|antar|pechelbronn|carte.?postale|"
    r"hepting|cherot|carreau|huile|asphalt|\b1[89]\d\d\b|annees)",
    re.I,
)
_DENY = re.compile(
    r"(d[eé]pliant|flyer|banni|logo|facebook|instagram|whatsapp|screen|capture|"
    r"^img[_-]?\d|img20\d{6}|kfet|k.?ro|kro sauvage|atelier|visite|programme|"
    r"affiche|agenda|petitfute|pass.?alsace|g[iî]te|boutique|adh[eé]sion|^couv|"
    r"colorimetre|m[eé]daille|maquette|aquarelle|tableau|pain.?asphalte|copie|"
    r"dscn|dsc_|\d{9,}_\d+_n$|_n$|roadtrip|hearo?t|diorama|pelican)",
    re.I,
)
_PECH_CODE = re.compile(r"(PECH[_\-\s.]?\d[\w.\-]*)", re.I)


def _get(params: dict, timeout: int = 30) -> requests.Response:
    """One read-only GET against the media endpoint (raises on non-200)."""
    r = requests.get(MEDIA_ENDPOINT, params=params, headers=HEADERS,
                     timeout=timeout)
    r.raise_for_status()
    return r


def count_images(search: str | None = None) -> int:
    """Total number of image media (via X-WP-Total). 913 with no search."""
    p = {"media_type": "image", "per_page": 1}
    if search:
        p["search"] = search
    return int(_get(p).headers.get("X-WP-Total", 0))


def list_media(search: str | None = None, page: int = 1, per_page: int = 100,
               fields: str = "id,title,source_url,media_details,date,link,caption") -> list[dict]:
    """One page of image media records."""
    p = {"media_type": "image", "per_page": per_page, "page": page,
         "_fields": fields}
    if search:
        p["search"] = search
    return _get(p).json()


def iter_images(per_page: int = 100,
                fields: str = "id,title,source_url,media_details,date,link,caption"):
    """Yield every image record, following X-WP-TotalPages."""
    page = 1
    while True:
        p = {"media_type": "image", "per_page": per_page, "page": page,
             "_fields": fields}
        r = _get(p)
        batch = r.json()
        if not batch:
            break
        yield from batch
        if int(r.headers.get("X-WP-TotalPages", page)) <= page:
            break
        page += 1


def _title(m: dict) -> str:
    return ((m.get("title") or {}).get("rendered") or "").strip()


def is_archival(title: str) -> bool:
    """Heuristic: does this media title belong to the petroleum fonds?"""
    return bool(_INC.search(title)) and not bool(_DENY.search(title))


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def normalize(m: dict) -> dict:
    """Map one WP media record to a catalogue record (see FIELD MAPPING)."""
    title = _title(m)
    md = m.get("media_details") or {}
    sizes = md.get("sizes") or {}
    thumb = None
    for key in ("medium_large", "large", "medium", "thumbnail"):
        if key in sizes and sizes[key].get("source_url"):
            thumb = sizes[key]["source_url"]
            break
    cap = _strip_html((m.get("caption") or {}).get("rendered", ""))
    desc = _strip_html((m.get("description") or {}).get("rendered", ""))
    code = _PECH_CODE.search(title)
    return {
        "source": "pechelbronn_petrole",
        "id": str(m.get("id")),
        "title": title,
        "inventory": code.group(1) if code else None,
        "image_url": m.get("source_url"),
        "thumbnail_url": thumb or m.get("source_url"),
        "width": md.get("width"),
        "height": md.get("height"),
        "uploaded": m.get("date"),
        "record_url": m.get("link") or COLLECTIONS_URL,  # link may 404 -> fallback
        "credit": CREDIT,
        "source_url": MUSEUM_URL,
        "text": " . ".join(x for x in (title, cap, desc, code.group(1) if code else "") if x),
    }


def fetch_fonds(only_archival: bool = True, max_items: int | None = None) -> list[dict]:
    """Return the normalized fonds (default: the ~102 archival items)."""
    out: list[dict] = []
    for m in iter_images():
        if only_archival and not is_archival(_title(m)):
            continue
        out.append(normalize(m))
        if max_items and len(out) >= max_items:
            break
    return out


# Proposed descriptor the coder can drop in config/sources/pechelbronn_petrole.yaml.
DESCRIPTOR = {
    "slug": "pechelbronn_petrole",
    "name": "Musée Français du Pétrole – Pechelbronn (fonds pétrolier d'Alsace)",
    "protocol": "wordpress_media",   # bespoke JSON connector (no IIIF/POP available)
    "base_url": "https://www.musee-du-petrole.com",
    "auth": "none",
    "rights": "© Musée Français du Pétrole – Merkwiller-Pechelbronn (all rights "
              "reserved); index + link back only, never re-host",
    "credit": CREDIT,
    "extra": {
        "endpoint": MEDIA_ENDPOINT,
        "query": {"media_type": "image", "per_page": 100},
        "pagination": "X-WP-TotalPages / page",
        "archival_filter": "is_archival(title): inventory PECH code or domain "
                           "keyword (puits, treuil, raffinerie, pompe, Antar, "
                           "carte-postale, ...) minus modern-media denylist",
        "approx_items_all_images": 913,
        "approx_items_archival": 102,
        "record_link_fallback": COLLECTIONS_URL,
        "total": 102,
    },
}
