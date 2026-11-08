"""Musée français du pétrole / fonds Pechelbronn — mnemosyne browser research.

Source slug : pechelbronn_petrole
Resolver     : phrase yt_la_france_a_du_petrole_mais_elle_la_oublie_...
Institution  : Musée français du pétrole, 67250 Merkwiller-Pechelbronn (Bas-Rhin,
               Alsace). "Fonds Pechelbronn" = berceau du pétrole français
               (source « Baechel-Brunn » ; extraction dès le 18e s. jusqu'en 1970 ;
               premier carottage électrique Schlumberger ; naissance d'Antar et de
               l'IFP). Directement pertinent pour « la France a du pétrole mais
               elle l'a oublié ».

This module is a READ-ONLY reference the coder uses to build
`config/sources/pechelbronn_petrole.yaml` + its connector. It performs NO writes
and NEVER scrapes HTML for images: image data comes only from the open WordPress
REST JSON API. Title strings are the only human metadata the site exposes.

=====================================================================
0. DOMAIN CORRECTION (important)
=====================================================================
* The task URL `https://www.musee-petrole.com/` does NOT resolve (DNS NXDOMAIN).
  The LIVE domain is  **https://www.musee-du-petrole.com/**  (note "-du-").
* The museum's former online catalogue subdomain
  `musee-petrole.webmuseo.com` (cited in the mentions légales) is DEAD:
  ERR_SSL_UNRECOGNIZED_NAME_ALERT / connection blocked. Webmuseo is unusable.
* The site is a WordPress (GeneratePress theme, Polylang `pll/v1`, MetaSlider).
  The museum is temporarily closed to visitors (arrêté municipal 10 mars 2026)
  but the website + REST API are fully live.
* Contacts (mentions légales): museedupetrole@wanadoo.fr ;
  musee.petrole@musees-vosges-nord.org ; tél 03.88.80.91.08.

=====================================================================
1. PROGRAMMATIC ACCESS  (open, JSON, NO auth) — verified 2026-10
=====================================================================
WordPress REST API, public, answers ANY User-Agent with JSON for GETs:

    ROOT     https://www.musee-du-petrole.com/wp-json/
    MEDIA    /wp-json/wp/v2/media
    POSTS    /wp-json/wp/v2/posts        (actus / articles)
    PAGES    /wp-json/wp/v2/pages        (38 pages)
    SEARCH   /wp-json/wp/v2/search       (cross-type; ?search=...)
    TYPES    /wp-json/wp/v2/types        (post, page, attachment='media', ...)

MEDIA enumeration (the asset source):

    GET /wp-json/wp/v2/media?media_type=image&per_page=100&page=N
        &_fields=id,date,slug,title,source_url,link,media_details,
                 alt_text,caption,description,post,mime_type
        &orderby=id&order=asc          # stable deep pagination
    Response headers:  X-WP-Total: 913 (images)   X-WP-TotalPages: 10
    per_page max = 100.  media_type=image excludes the ~196 PDFs/others.

Convenience queries (all verified 200):
    /media?include=4380,4175,4498         # fetch specific ids
    /media?search=<term>&media_type=image # server-side title/content search
    search counts seen: PECH_=62, Pechelbronn=15, Antar=25, raffinerie=9,
                        pétrole=20, puits=5, carte postale=4.

=====================================================================
2. FIELD MAPPING  (WP media record -> normalised asset)
=====================================================================
  asset_id        <- str(m["id"])  (namespace as "pechelbronn-petrole:<id>")
  title           <- strip_tags(m["title"]["rendered"])   # the ONLY caption;
                     caption/description/alt_text are EMPTY for most fonds items
  date_upload     <- m["date"]      # UPLOAD date, NOT the historical date
  date_original   <- parse from title when present ("5 sept 1927", "années 1920",
                     "1re moitié 20e s", "après reconstruction 2WW", "1913"...)
  landing/source  <- m["link"]      # public attachment page (may end "/#main")
  image_full      <- m["source_url"]
  image_thumb     <- m["media_details"]["sizes"]["medium"]["source_url"]
  width/height    <- m["media_details"]["width"/"height"]
  parent_post     <- m["post"]      # parent id; 0 = unattached
  mime_type       <- m["mime_type"] # "image/jpeg" etc.
  license         <- NONE EXPOSED  (no licence/CC/domaine public field anywhere)

=====================================================================
3. THREE GOTCHAS  (must handle or connector breaks)
=====================================================================
(a) BURST WAF -> HTTP 410.
    ~10-13 rapid requests then the server replies 410 with an HTML error page
    (not JSON). It recovers after a short pause. Mitigation:
      * ~1 request every 2 s (REQUEST_DELAY_S = 2.0), sequential, no parallel;
      * on 410/429/503: exponential backoff (2s,4s,8s...) and retry the page;
      * treat 410 as retryable, NOT fatal.

(b) LATIN-1 FILENAMES.
    Some uploaded filenames with accents are stored as Latin-1, so the correct
    percent-encoding of "â" is %E2 (a single byte), NOT UTF-8 %C3%A2 and NOT a
    plain "a". Verified: "5-sept-1927_Pechelbronn-c%E2ble-et-treuil.jpg" -> 200.
    Use `latin1_url()` below on source_url when a plain GET 404s.

(c) DEAD UPLOADS.
    A few source_urls 404 (image deleted but media record kept). Validate the
    image (HEAD/GET -> 200 + image/* content-type) and fall back to a smaller
    size variant (media_details.sizes.*.source_url) before dropping the item.

=====================================================================
4. HISTORICAL FONDS CLASSIFIER  (the library is a MIX)
=====================================================================
There is NO taxonomy term to isolate the fonds. Of ~913 images, ~96 are
recognisably historical and ~63 carry a PECH / year.cote.matiere inventory
code. Identify them from the title + slug with `is_historical()`:
  POSITIVE: "PECH_2013-1-2", "1997.0.256", "CollectionMFDP", and domain
            vocabulary (pechelbronn, merkwiller, antar, raffinerie, forage,
            puits, derrick, sonde, treuil, carottage, sauer, schlumberger,
            hepting, carte postale, aquarelle, photographie, année 18xx/19xx,
            2WW / guerres).
  NOISE (exclude): Logo, Amuse-musées, IMG_*, Présentation, stockcake,
            favicon/bannière/header, AND staff snapshots whose slug starts with
            a modern compact 8-digit date (e.g. 20210608_...). Those are recent
            photos, not archive, so `is_historical()` hard-excludes any slug
            matching a leading 20YYMMDD_ prefix.

=====================================================================
5. RECOMMENDED DESCRIPTOR  (config/sources/pechelbronn_petrole.yaml)
=====================================================================
  slug: pechelbronn_petrole
  name: "Musée français du pétrole — fonds Pechelbronn"
  base_url: "https://www.musee-du-petrole.com"
  protocol: http_json            # or a dedicated "wordpress-media" connector
  rights: in_copyright           # NO open licence — reuse needs permission
  credit: "© Musée français du pétrole / Association des Amis du Musée"
  extra:
    media_endpoint: "https://www.musee-du-petrole.com/wp-json/wp/v2/media"
    media_type: image
    per_page: 100
    orderby: id
    order: asc
    fields: "id,date,slug,title,source_url,link,media_details,
             alt_text,caption,description,post,mime_type"
    request_delay_s: 2.0
    retry_status: [410, 429, 503]
    url_encode_fallback: latin1
    historical_regex: >
      (?i)pech[ _-]?\\d|\\d{4}\\.\\d+\\.\\d+|collection\\s*mfdp|
      pechelbronn|antar|raffiner|forage|puits|carte\\s*postale

Pagination: loop page=1..X-WP-TotalPages, keep only is_historical() items.
Dedup by id. Total first-run ≈ 96-160 historical images from 913 candidates.

=====================================================================
6. RIGHTS / AUTHORIZATION
=====================================================================
No open licence is published. Catalog as FINDER, in_copyright, mandatory
credit. To obtain written reuse permission, contact the museum (the ONLY case
where a scraper/permission matters):  museedupetrole@wanadoo.fr
Suggested email subject: "Demande d'autorisation — réutilisation d'images du
fonds Pechelbronn (projet de recherche ouvert mnemosyne)"; body asks for
written permission to reference + hotlink/thumbnail historical photos with
full credit, referencing the project URL.

=====================================================================
7. VERIFIED FIXTURES  (all HTTP 200 image/jpeg — good tests)
=====================================================================
  id 4380  carte postale aérienne raffinerie (916x579)
  id 4498  publicité Antar (2560x1860)
  id 4175  portrait Louis Hepting (2010x2560)
  id 1092  "5 sept 1927_Pechelbronn câble et treuil" (1254x833)  # latin-1 case
  id 5283  Aquarelle Sauer PECH_2013-1-2
  id 1117  Atelier_ANTAR_ex_01
  id 4501  PECH_1997.0.256
  id 4289  PECH_2020-0-52_2
  page id 218 (historique) embeds Schlumberger portraits + raffinerie views.

=====================================================================
8. OPEN COMPLEMENT  (Wikimedia Commons fallback)
=====================================================================
If an openly-licensed image is required, Commons has 269 File: hits for
"Pechelbronn". Public-domain: File:XXe - Pechelbronn - 02.jpg / -04.jpg
(Victor Forbin 1864-1947). Also Kasino Pechelbronn.jpg (CC BY-SA 4.0).
Commons API is open (action=query&list=search / generator=search&prop=imageinfo)
and can be an IIF-style open source; attribution required per file.

=====================================================================
9. TESTS
=====================================================================
  * is_historical() flags every fixture id above and the "5 sept 1927",
    PECH_1997.0.256, Schlumberger, Carreau-de-Mine titles as True.
  * is_historical() returns False for Logo, Amuse-musées, IMG_*, Présentation,
    stockcake and leading modern 8-digit-date staff snapshots (e.g. 20210608_).
  * extract_inventory() returns "PECH_2013-1-2", "PECH_1997.0.256", etc.
  * latin1_url("...Pechelbronn-câble...") contains "%E2" and resolves 200.
"""
from __future__ import annotations

import re
import urllib.parse

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
BASE = "https://www.musee-du-petrole.com"
ROOT_API = BASE + "/wp-json/"
MEDIA_API = ROOT_API + "wp/v2/media"
POSTS_API = ROOT_API + "wp/v2/posts"
PAGES_API = ROOT_API + "wp/v2/pages"
SEARCH_API = ROOT_API + "wp/v2/search"

MEDIA_FIELDS = (
    "id,date,slug,title,source_url,link,media_details,"
    "alt_text,caption,description,post,mime_type"
)

DEFAULT_PER_PAGE = 100
REQUEST_DELAY_S = 2.0          # ~1 req / 2 s avoids the 410 burst WAF
RETRY_ON_STATUS = (410, 429, 503)

CREDIT = "© Musée français du pétrole / Association des Amis du Musée"
CONTACT_EMAILS = ("musedupetrole@wanadoo.fr",
                  "musee.petrole@musees-vosges-nord.org")

# --------------------------------------------------------------------------
# Regexes (compiled once); all case-insensitive
# --------------------------------------------------------------------------
_HISTORICAL_RE = re.compile(
    r"("
    r"pech[ _-]?\d"                       # PECH inventory codes
    r"|\b\d{4}\.\d+\.\d+\b"               # 1997.0.256 cote
    r"|collection\s*mfdp"
    r"|pechelbronn|merkwiller|baechel|baechelbrunn"
    r"|antar|sauer|schlumberger|hepting"
    r"|raffiner|forage|puits|derrick|sonde|treuil|carottage|sondage"
    r"|carte\s*postale|\bcpa\b|aquarelle|gravure|dessin|photograph"
    r"|1[789]\d{2}|19[0-6]\d"
    r"|premi[èe]re\s*guerre|seconde\s*guerre|\b2\s*ww\b|\bww\s*2\b"
    r")",
    re.IGNORECASE,
)

_NOISE_RE = re.compile(
    r"("
    r"^logo|logo[-_ ]|amuse[-_ ]?mus|^img[-_]|pr[ée]sentation"
    r"|stockcake|^screenshot|capture[-_ ]d|placeholder|favicon"
    r"|banni[èe]re|header|footer|background|picto|\bic[oô]ne\b"
    r")",
    re.IGNORECASE,
)

# modern (21st-century) compact date prefix = recent staff snapshot -> noise
_LEADING_DATE_RE = re.compile(r"^20\d{6}[_\-]")

_INVENTORY_RE = re.compile(
    r"(PECH[ _\-]?\d[\w.\-]*|\b\d{4}\.\d+\.\d+\b)", re.IGNORECASE
)

THEMES = {
    "forage": ("forage", "puits", "derrick", "sonde", "treuil",
               "carottage", "sondage"),
    "raffinerie": ("raffiner", "distiller", "usine", "huile"),
    "portrait": ("portrait", "hepting", "schlumberger", "directeur"),
    "carte_postale": ("carte postale", "\bcpa\b", "vue générale"),
    "publicite": ("antar", "publicité", "publicite", "affiche"),
    "materiel": ("matériel", "materiel", "machine", "pompe", "chevalet"),
}


# --------------------------------------------------------------------------
# Pure, import-safe helpers (no network here; the connector does the I/O)
# --------------------------------------------------------------------------
def strip_tags(text) -> str:
    """Strip WordPress rendered-HTML tags and collapse whitespace."""
    if not text:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(text))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _title(record: dict) -> str:
    return strip_tags((record.get("title") or {}).get("rendered", ""))


def is_historical(record: dict) -> bool:
    """True if a WP media record looks like an authentic fonds/archive image."""
    title = _title(record)
    slug = record.get("slug") or ""
    hay = (title + " " + slug).strip()
    if not hay:
        return False
    if _NOISE_RE.search(hay):
        return False
    # leading modern compact date (e.g. 20210608_) = recent staff photo
    if _LEADING_DATE_RE.search(slug):
        return False
    return bool(_HISTORICAL_RE.search(hay))


def extract_inventory(record: dict):
    """Return the museum inventory code (e.g. PECH_2013-1-2 or PECH_1997.0.256)."""
    title = _title(record)
    m = _INVENTORY_RE.search(title)
    if not m:
        m = _INVENTORY_RE.search(record.get("slug") or "")
    return m.group(1) if m else None


def classify_theme(record: dict) -> str:
    """Coarse theme bucket from title+slug (for light tagging)."""
    hay = (_title(record) + " " + (record.get("slug") or "")).lower()
    for theme, kws in THEMES.items():
        if any(k in hay for k in kws):
            return theme
    return "autre"


def latin1_url(url: str) -> str:
    """Percent-encode a URL whose path/query was stored as Latin-1 bytes.

    WordPress sometimes keeps accented filenames as Latin-1, so the HTTP fetch
    must send the raw single byte (â -> 0xE2 -> %E2), NOT UTF-8's %C3%A2.
    """
    if not url:
        return url
    parts = urllib.parse.urlsplit(url)
    path = parts.path.encode("latin-1", "ignore")
    query = parts.query.encode("latin-1", "ignore")
    path = urllib.parse.quote(path, safe="/%")
    query = urllib.parse.quote(query, safe="=&%")
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path, query, parts.fragment)
    )


def normalise(record: dict) -> dict:
    """Map a WP media record to the normalised asset shape (no network)."""
    md = record.get("media_details") or {}
    sizes = md.get("sizes") or {}
    medium = (sizes.get("medium") or {}).get("source_url")
    return {
        "asset_id": "pechelbronn-petrole:" + str(record.get("id")),
        "title": _title(record),
        "date_upload": record.get("date"),
        "inventory": extract_inventory(record),
        "theme": classify_theme(record),
        "source_url": record.get("source_url"),
        "thumb_url": medium or record.get("source_url"),
        "landing_url": record.get("link"),
        "width": md.get("width"),
        "height": md.get("height"),
        "parent_post": record.get("post"),
        "mime_type": record.get("mime_type"),
        "credit": CREDIT,
        "license": "in_copyright",  # no open licence exposed by the site
    }


__all__ = [
    "BASE", "ROOT_API", "MEDIA_API", "POSTS_API", "PAGES_API", "SEARCH_API",
    "MEDIA_FIELDS", "DEFAULT_PER_PAGE", "REQUEST_DELAY_S", "RETRY_ON_STATUS",
    "CREDIT", "CONTACT_EMAILS", "THEMES",
    "strip_tags", "is_historical", "extract_inventory", "classify_theme",
    "latin1_url", "normalise",
]
