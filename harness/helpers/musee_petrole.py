"""Musee francais du petrole (Merkwiller-Pechelbronn) -- mnemosyne reference.

Browser-agent reconnaissance (task #187). Read-only: every function only GETs
and parses; nothing here writes to the remote.

WHY THIS SOURCE
---------------
The adversarial resolver needs a *French* petroleum-archive source to (1)
identify "lui" (a French/contemporary well-killing specialist behind the
documentary line "Son CV a lui, c'est la guerison de plus de 250 puits a travers
le monde") and (2) obtain a portrait or an authentic image of well intervention.
Gallica, Europeana, Paris Musees, ANMT (Roubaix) and POP return nothing on
petrole/puits. The Musee francais du petrole de Merkwiller-Pechelbronn is the
oldest oil field exploited in the world (systematic extraction from the first
half of the 18th c., traces back to 1498; the "Baechel-Brunn" spring) -- the
single most relevant French petroleum-heritage source. It documents the whole
chain: forage a battage (Raky), forage rotary, pompes a balancier, carottage
electrique (freres Schlumberger), la societe Antar, l'Institut francais du
petrole, raffineries, galeries de mine -- plus portraits of the French oil
pioneers (famille Le Bel, Boussingault, Conrad & Marcel Schlumberger, Cherot).

SITE / ACCESS
-------------
Public site ..... https://www.musee-du-petrole.com  (WordPress)
There is NO bespoke collection API and the `musee-petrole.webmuseo.com` host
named in the legal notice is the private WebMuseo CMS BACKEND (no public portal:
https -> SSL TLSV1_UNRECOGNIZED_NAME, http -> 404). But the site runs stock
WordPress and therefore exposes the **WordPress REST API** -- open, no auth,
JSON. That is the programmatic access we use (NOT HTML scraping):

    ROOT      https://www.musee-du-petrole.com/wp-json/
    MEDIA     https://www.musee-du-petrole.com/wp-json/wp/v2/media
    PAGES     https://www.musee-du-petrole.com/wp-json/wp/v2/pages
    POSTS     https://www.musee-du-petrole.com/wp-json/wp/v2/posts

Verified 2026-: HTTP 200, Content-Type application/json, any User-Agent.
`robots.txt` allows everything except /wp-admin/ (admin-ajax allowed) and points
to /wp-sitemap.xml (so the REST API is clearly within policy).

MEDIA SHAPE (GET /wp-json/wp/v2/media?media_type=image&per_page=100&page=N)
--------------------------------------------------------------------------
Returns a JSON array of attachment objects. Useful fields per item:
    id, date, slug, link, source_url                    (original, full-res)
    title.rendered, caption.rendered, description.rendered (HTML, often empty)
    alt_text, filename, filesize, mime_type, media_type ("image")
    media_details: {width, height, sizes:{ thumbnail, medium, large,
                      medium_large, full } each with {file,width,height,source_url}}
    post  -> parent page/post id
Pagination: ?per_page=100&page=1.. ; responses carry X-WP-Total/X-WP-TotalPages
headers (http_get body-only, so we paginate until a short page).
Search:     ?search=<term>  (full-text over title/caption/description). NOTE the
            term MUST be URL-encoded (a raw space raises "URL can't contain
            control characters"). Verified: search=puits -> 5, search=pompe -> 4,
            search=raffinerie -> 1, search=Antar -> 23 image hits.
Total catalogue: 599 image attachments (verified).

CONTENT SHAPE (GET /wp-json/wp/v2/pages|posts?search=<term>)
-----------------------------------------------------------
Pages/posts carry the historical NARRATIVE and caption the images inline as
    <a href=".../xx.jpg"><img class="... wp-image-<MEDIA_ID>" src=".../xx.jpg"
        alt="..." width height srcset=...></a>
There are NO <figcaption>/wp-caption blocks: the "caption" is the nearest
preceding <h1..h4> heading + the surrounding <p> paragraph. `wp-image-<ID>`
ties the inline image back to the media attachment. This is how we enrich a
search hit with real French context (e.g. heading "La marque Antar", paragraph
"Les freres Schlumberger et leur invention ...").

INVENTORY NUMBERS
-----------------
Many filenames/titles embed the museum inventory number, e.g.
    "Maquette presse filtre PECH_1997.0.214_1", "PECH_2019-1-1_3",
    "PECH_2014-1-1_v2", "06pechelbronn-cherot_Antar".
`inventory_number()` parses the PECH.<year>.<n>.<n> core (best-effort).

RIGHTS
------
Legal notice (https://www.musee-du-petrole.com/mentions-legales/) credits the
photos to the "Association des Amis du Musee du Petrole" and invites contact for
any erroneous/missing copyright. There is NO open (CC) licence on the site.
Treat this as **In Copyright** (https://rightsstatements.org/vocab/InC/1.0/):
catalogue the metadata + low-res thumbnail and DEEP-LINK the original to the
museum. Historical works (Schlumberger 1878-1936, early-20th c. postcards) may
well be in the public domain, but the reproduction credit belongs to the
association -> reuse of originals requires written permission from:
    museedupetrole@wanadoo.fr  /  musee.petrole@musees-vosges-nord.org
    +33 3 88 80 91 08   (Pascale Roll-Schneider, mediatrice culturelle)

RECOMMENDED DESCRIPTOR (coder finalises the exact product schema)
----------------------------------------------------------------
    slug: musee_francais_du_petrole
    name: Musee francais du petrole -- Merkwiller-Pechelbronn
    protocol: wordpress_rest          # or the product's generic rest_json enum
    base_url: https://www.musee-du-petrole.com/wp-json/wp/v2
    auth: none
    rate_limit_rps: 1
    rights: https://rightsstatements.org/vocab/InC/1.0/
    license: In Copyright -- Association des Amis du Musee du Petrole
    extra:
      media_endpoint: /media
      content_endpoints: [/pages, /posts]
      search_mode: media_title + page_content
      media_type: image
      thumbnail_size: medium         # 300 px; 'large' = 1024 px
      total_approx: 599

PERFORMANCE
-----------
~2 s/round-trip to the museum host. `search()` therefore builds a single
in-process media index (6 calls for 599 images, cached in `_INDEX`) and looks
thumbnails up locally instead of calling get_media() per inline image (that
naive path blows the 300 s step budget).
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

BASE = "https://www.musee-du-petrole.com"
API = BASE + "/wp-json/wp/v2"
UA = ("mnemosyne-browser/1.0 (+https://github.com/Antonio-Faure/mnemosyne; "
      "open research aggregator; contact agent@example.com)")

MUSEUM = "Musee francais du petrole - Merkwiller-Pechelbronn"
OWNER = "Association des Amis du Musee du Petrole"
COLLECTION = "Musee francais du petrole"
LICENSE = {
    "holder": "In Copyright - Association des Amis du Musee du Petrole",
    "rights": "https://rightsstatements.org/vocab/InC/1.0/",
    "statement": ("Photos credited to the Association des Amis du Musee du "
                  "Petrole; no open licence. Metadata + thumbnail are reused, "
                  "the original is deep-linked. Reuse of originals requires "
                  "written permission (museedupetrole@wanadoo.fr). Historical "
                  "works may be public domain."),
    "contact": "museedupetrole@wanadoo.fr",
    "nc": True,
    "enabled": True,
}


# --------------------------------------------------------------------- HTTP

def _get_text(url, timeout=25.0, retries=3):
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"GET failed: {url} :: {last}")


def _get_json(path, timeout=25.0):
    url = path if path.startswith("http") else (API + path)
    txt = _get_text(url, timeout=timeout)
    return json.loads(txt)


def _q(term):
    return urllib.parse.quote(str(term), safe="")


def _clean_html(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(re.sub(r"\s+", " ", s))
    return s.strip()


def _prettify(s):
    s = (s or "").replace("_", " ").replace("  ", " ")
    return re.sub(r"\s+", " ", s).strip()


def _https(u):
    return u.replace("http://www.musee-du-petrole.com", BASE).replace(
        "http://musee-du-petrole.com", BASE) if u else u


def _good_title(t):
    return bool(t) and len(t.strip()) >= 4 and not re.fullmatch(r"[\d\s\.\-]+", t.strip())


# --------------------------------------------------------------------- media

def list_media(page=1, per_page=100, media_type="image"):
    """One page of media attachments (raw WP objects)."""
    return _get_json(f"/media?per_page={per_page}&media_type={media_type}&page={page}")


def iter_all_media(per_page=100, max_pages=50, media_type="image"):
    """Yield every media attachment across pages (stops on a short page)."""
    for p in range(1, max_pages + 1):
        batch = list_media(page=p, per_page=per_page, media_type=media_type)
        if not isinstance(batch, list) or not batch:
            break
        yield from batch
        if len(batch) < per_page:
            break


def search_media(query, per_page=100, media_type="image"):
    """Full-text search over media title/caption/description."""
    return _get_json(f"/media?per_page={per_page}&media_type={media_type}&search={_q(query)}")


def get_media(media_id):
    """Single media attachment by id."""
    return _get_json(f"/media/{int(media_id)}")


def media_sizes(media):
    """Map of size-name -> source_url for a media object (largest fallback)."""
    md = (media or {}).get("media_details") or {}
    out = {}
    for name, info in (md.get("sizes") or {}).items():
        if info.get("source_url"):
            out[name] = _https(info["source_url"])
    full = media.get("source_url") or (md.get("file") and f"{BASE}/wp-content/uploads/{md['file']}")
    if full:
        out.setdefault("full", _https(full))
    return out


def _pick_thumb(sizes):
    for name in ("medium", "medium_large", "large", "thumbnail", "full"):
        if name in sizes:
            return sizes[name]
    return sizes.get("full")


_INDEX = None


def media_index(refresh=False):
    """id -> {source_url, title, date, filename, sizes} for all image media.
    Built once per process (~6 calls) and cached."""
    global _INDEX
    if _INDEX is None or refresh:
        idx = {}
        for m in iter_all_media():
            idx[m.get("id")] = {
                "source_url": _https(m.get("source_url")),
                "title": _clean_html(m.get("title", {}).get("rendered")),
                "date": (m.get("date") or "")[:10],
                "filename": m.get("filename"),
                "sizes": media_sizes(m),
            }
        _INDEX = idx
    return _INDEX


# --------------------------------------------------------------- inventory

_PECH_INV = re.compile(r"PECH[._\-\s]?\s*(\d{4})[._\-](\d{1,4})(?:[._\-](\d{1,4}))?", re.I)


def inventory_number(text):
    """Best-effort museum inventory number (PECH.<year>.<n>[.<n>]) or None."""
    m = _PECH_INV.search(text or "")
    if not m:
        return None
    parts = [p for p in m.groups() if p is not None]
    return "PECH." + ".".join(parts)


def _base_item():
    return {
        "collections": [COLLECTION],
        "domain": "Petrole / patrimoine industriel (Alsace du Nord)",
        "material": [],
        "owner": OWNER,
        "keywords": ["petrole", "Pechelbronn", "Alsace", "musee du petrole"],
        "license": LICENSE["holder"],
        "license_rights": LICENSE["rights"],
        "license_nc": LICENSE["nc"],
        "credit": "© " + OWNER,
        "enabled": LICENSE["enabled"],
        "source": "musee_francais_du_petrole",
    }


# --------------------------------------------------------------- normalize

def media_to_item(media):
    """Normalise one WP media attachment to the mnemosyne item shape."""
    raw_title = _clean_html(media.get("title", {}).get("rendered"))
    title = _prettify(raw_title) or (media.get("filename") or "").rsplit("/", 1)[-1]
    sizes = media_sizes(media)
    desc = _clean_html(media.get("caption", {}).get("rendered")) or \
        _clean_html(media.get("description", {}).get("rendered"))
    it = _base_item()
    it.update({
        "id": f"mfdp:media:{media.get('id')}",
        "native_id": str(media.get("id")),
        "title": title,
        "subtitle": "",
        "date": (media.get("date") or "")[:10],
        "url": _https(media.get("source_url")),
        "page_url": media.get("link"),
        "technique": media.get("mime_type"),
        "inventory_number": inventory_number(
            (media.get("filename") or "") + " " + (raw_title or "")),
        "description": desc,
        "has_image": media.get("media_type") == "image",
        "image": _https(media.get("source_url")),
        "thumbnail": _pick_thumb(sizes),
        "images": sizes,
        "dimensions": [media.get("media_details", {}).get("width"),
                       media.get("media_details", {}).get("height")],
    })
    return it


def all_items(limit=None):
    """Yield every media attachment normalised (full bulk harvest of 599)."""
    n = 0
    for m in iter_all_media():
        yield media_to_item(m)
        n += 1
        if limit and n >= limit:
            break


# ---------------------------------------------------------------- content

_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_IMG_SRC = re.compile(r'\bsrc="([^"]*)"', re.I)
_IMG_ALT = re.compile(r'\balt="([^"]*)"', re.I)
_IMG_WPID = re.compile(r"wp-image-(\d+)", re.I)
_HEAD = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.I | re.S)
_PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_SKIP = re.compile(r"(1x1-pixel|logo|slider|icon|banner|cropped-|blank\.|spacer)", re.I)


def extract_images(content_html):
    """Inline <img> of a WP page/post, each with the nearest preceding heading
    and paragraph as caption/context. Skips obvious decorative assets."""
    out = []
    for m in _IMG_TAG.finditer(content_html or ""):
        tag = m.group(0)
        src_m = _IMG_SRC.search(tag)
        if not src_m:
            continue
        src = src_m.group(1)
        if _SKIP.search(src):
            continue
        alt_m = _IMG_ALT.search(tag)
        wid_m = _IMG_WPID.search(tag)
        before = content_html[:m.start()]
        heads = _HEAD.findall(before)
        heading = _clean_html(heads[-1]) if heads else ""
        paras = _PARA.findall(before)
        context = _clean_html(paras[-1])[-400:] if paras else ""
        out.append({
            "media_id": int(wid_m.group(1)) if wid_m else None,
            "src": _https(src),
            "alt": html.unescape(alt_m.group(1)) if alt_m else "",
            "heading": heading,
            "context": context,
        })
    return out


def search_content(query, per_page=20, collections=("pages", "posts")):
    """Search WP pages/posts; return [(collection, page_obj)]."""
    hits = []
    for coll in collections:
        try:
            batch = _get_json(f"/{coll}?per_page={per_page}&search={_q(query)}")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(batch, list):
            hits += [(coll, p) for p in batch]
    return hits


def content_image_to_item(page, img, sizes=None):
    """Build an image item from an inline page image (enriched with context)."""
    sizes = sizes or {}
    src = img.get("src")
    # WP convention: a -WxH suffix marks a resized copy; strip it for the full.
    full = re.sub(r"-\d+x\d+(\.(?:jpg|jpeg|png|gif|webp))$", r"\1", src or "", flags=re.I)
    page_title = _clean_html(page.get("title", {}).get("rendered"))
    alt = _prettify(img.get("alt"))
    heading = img.get("heading") or ""
    title = alt if _good_title(alt) else (heading or page_title)
    subtitle = heading or page_title
    inv = inventory_number(" ".join(filter(None, [img.get("alt"), src])))
    it = _base_item()
    it.update({
        "id": "mfdp:page:{}:img:{}".format(
            page.get("id"), img.get("media_id") or (src or "").rsplit("/", 1)[-1]),
        "native_id": str(img.get("media_id") or page.get("id")),
        "title": title,
        "subtitle": subtitle,
        "alt_text": alt,
        "date": "",
        "url": full or src,
        "page_url": page.get("link"),
        "technique": None,
        "inventory_number": inv,
        "description": img.get("context") or page_title,
        "has_image": True,
        "image": full or src,
        "thumbnail": _pick_thumb(sizes) if sizes else src,
        "images": sizes or {"full": full or src},
    })
    return it


# ------------------------------------------------------------------ search

def search(query, limit=40, media_hits=100, content_pages=8, inline_per_page=8):
    """Composite search: media-title hits UNION page/post inline images
    (with heading+context). Returns de-duplicated mnemosyne items, best first."""
    items, seen = [], set()

    def add(it):
        key = it.get("url") or it.get("id")
        if key and key not in seen:
            seen.add(key)
            items.append(it)

    # 1) media library title/caption hits (complete metadata already present)
    for m in search_media(query, per_page=media_hits):
        add(media_to_item(m))

    # 2) page/post hits -> inline images, enriched with context; sizes from index
    idx = media_index()
    for _coll, page in search_content(query, per_page=content_pages):
        for img in extract_images(page.get("content", {}).get("rendered", ""))[:inline_per_page]:
            mid = img.get("media_id")
            entry = idx.get(mid) if mid else None
            add(content_image_to_item(page, img, entry["sizes"] if entry else None))

    return items[:limit]


def license_info():
    """Site-wide rights statement for this source."""
    return dict(LICENSE)


# ---------------------------------------------------------------- self-test

if __name__ == "__main__":
    import time
    t = time.time()
    print("media index:", len(media_index()), f"({time.time()-t:.1f}s)")
    print("inventory parse:", inventory_number("Maquette presse filtre PECH_1997.0.214_1"),
          inventory_number("PECH_2019-1-1_3"), inventory_number("06pechelbronn-cherot_Antar"))
    for q in ["Schlumberger", "raffinerie", "pompe", "Le Bel", "Antar"]:
        t = time.time()
        r = search(q, limit=6)
        print(f"\nSEARCH '{q}': {len(r)} items ({time.time()-t:.1f}s)")
        for it in r[:3]:
            print("  -", (it['title'] or '')[:44], "| sub:", (it['subtitle'] or '')[:34],
                  "| inv:", it['inventory_number'])
    print("\nlicense:", license_info()["holder"], "|", license_info()["rights"])
