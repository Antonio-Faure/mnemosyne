"""Paris en Images / Paris Musees -- public search + IIIF reference (task #561).

Reconnaissance + reference implementation by the mnemosyne navigator agent
(Archivist). Read-only: every function only GETs and parses; nothing here
writes to the remote, copies an image, or bypasses any access control.

WHAT "paris_en_images" ACTUALLY IS
----------------------------------
The legacy site https://www.parisenimages.fr/ is DEFUNCT: it 301/302-redirects
to https://www.paris.fr/ (the City of Paris portal), no dedicated phototheque
anymore. The live home of the photographic collections of the City of Paris
(the former "Paris en Images" / "Phototheque historique de la Ville de Paris",
operated by Paris Musees) is:

    https://www.parismuseescollections.paris.fr   (public portal, Drupal 10)
    https://apicollections.parismusees.paris.fr    (API host: IIIF + GraphQL)

For the requested subject (tribunal de commerce de Paris / ile de la Cite, and
the 15e arrondissement with the usine de Javel, 1930s), the collections live
here, e.g.:
    /fr/musee-carnavalet/oeuvres/tribunal-de-commerce-1er-arrondissement-paris
    /fr/musee-carnavalet/oeuvres/escalier-du-tribunal-de-commerce
    /fr/musee-carnavalet/oeuvres/cour-d-usine-15-rue-de-javel-15eme-arrondissement-paris

ACCESS MODEL -- two routes, both VERIFIED reachable WITHOUT any account/token
-----------------------------------------------------------------------------
1. PUBLIC FULL-TEXT SEARCH (the key breakthrough; no auth):
       GET https://www.parismuseescollections.paris.fr/fr/recherche?keywords=<q>&page=<n>&limit=<n>
   Returns SERVER-RENDERED HTML. `page` is 1-indexed (page=0 is empty/invalid;
   page=1 is the first page). `limit` default 50, options 50/100/150/200/300.
   Verified counts: "tribunal de commerce" -> 191, "usine de Javel" -> 6,
   "ile de la Cite" -> 1385. Each result is an <article id="node-<NID>"
   about="<notice_path>"> card containing the thumbnail and title.

2. PUBLIC IIIF MANIFESTS (no auth), one per digitised object:
       GET https://apicollections.parismusees.paris.fr/iiif/<visuel_id>/manifest
   Presentation API v2; full-size image = sequences[0].canvases[0].images[0]
   .resource.@id, a static Drupal image at .../styles/4k/... . There is NO
   IIIF Collection (cannot enumerate from the IIIF side); enumeration goes
   through route 1. The <visuel_id> (e.g. 320198168) is internal and appears
   on the notice page inside a `/iiif/<visuel_id>/manifest` link.

NOT usable without an account (documented, do NOT rely on):
   POST https://apicollections.parismusees.paris.fr/graphql  -> 403
   requires a per-account `auth-token` header; account creation needs email
   verification, which the autonomous agent cannot complete (placeholder
   contact email). So the GraphQL search is NOT the basis of this source.

RIGHTS -- vary PER ITEM (verified), must be read per notice
-----------------------------------------------------------
* CC0 items (Creative Commons Zero, "domaine public"): the notice carries
  `publicdomain/zero`, a "Telecharger" link `/fr/zip/oeuvre/<NID>` and a
  `/iiif/<visuel_id>/manifest`. Full-resolution image is freely usable;
  credit requested "CC0 Paris Musees / <museum>".
* In-copyright items: NO CC0, NO zip, NO IIIF manifest -> thumbnail only.
  Show metadata + a link to the notice page; do NOT serve full-res.
Detection regexes below read the three markers off the notice page.

BONUS: results are also exportable as a spreadsheet:
   GET /fr/export-search-xls?keywords=<q>&page=<n>   (and -pdf / -print).

RECOMMENDED DESCRIPTOR (hand-off to the coder)
----------------------------------------------
    # config/sources/paris_en_images.yaml
    slug: paris_en_images
    name: Paris Musees - Collections (Paris en Images)
    protocol: html            # public HTML search + per-notice IIIF
    base_url: https://www.parismuseescollections.paris.fr
    auth: none
    search:
      path: /fr/recherche
      params: {keywords: "{query}", page: "{page}"}
    image:
      iiiF_manifest: https://apicollections.parismusees.paris.fr/iiif/{visuel_id}/manifest
    rights: per-item   # CC0 -> full-res ok (credit); else thumbnail + link
Caveats for the coder: (1) confirm whether a `paris_musees` or `archives_paris`
source already exists in config/sources (Archives de Paris is a DIFFERENT,
separate institution); (2) confirm the resolver needs the literal key
`paris_en_images`; (3) get the live source count for docs from config/sources.
"""

from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.parse
import urllib.request

PORTAL = "https://www.parismuseescollections.paris.fr"
API = "https://apicollections.parismusees.paris.fr"
SEARCH_PATH = "/fr/recherche"
MANIFEST_TMPL = API + "/iiif/{visuel_id}/manifest"
ZIP_TMPL = PORTAL + "/fr/zip/oeuvre/{node_id}"
XLS_TMPL = PORTAL + "/fr/export-search-xls?keywords={q}&page={page}"

_UA = ("Mozilla/5.0 (compatible; MnemosyneArchivist/1.0; "
       "+https://github.com/Antonio-Faure/mnemosyne)")


def _fetch(url, tries=5, timeout=30):
    """GET *url* as text with a bot UA and retry/backoff on 5xx / transient.

    The portal intermittently answers 503 under light load; a short backoff
    clears it. Returns the decoded body (str). Raises the last error on
    persistent failure.
    """
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, "replace")
        except Exception as e:  # noqa: BLE001 - transient network/5xx
            last = e
            time.sleep(2 + attempt * 2)
    raise last


def _strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- #
# 1. SEARCH (public HTML, no auth)
# --------------------------------------------------------------------------- #
def search_url(keywords, page=1, limit=None):
    """Build the public search URL. `page` is 1-indexed."""
    q = urllib.parse.quote(keywords)
    url = f"{PORTAL}{SEARCH_PATH}?keywords={q}&page={int(page)}"
    if limit:
        url += f"&limit={int(limit)}"
    return url


def parse_search(html):
    """Parse a search results page -> {count, results:[card,...]}.

    Each card: node_id, notice_url (absolute), thumbnail (or None), title.
    Only <article id="node-..."> result cards are read; facet HTML is ignored.
    """
    m = re.search(
        r'<div class="count">\s*<span>\s*([\d\s\.]+?)\s*</span>', html)
    count = int(re.sub(r"[^\d]", "", m.group(1))) if m else 0
    results = []
    for am in re.finditer(
            r'<article id="node-(\d+)"[^>]*about="([^"]+)"[^>]*>(.*?)</article>',
            html, re.S):
        nid, about, body = am.group(1), am.group(2), am.group(3)
        tm = re.search(r'<img[^>]+src="(https://apicollections[^"]+)"', body)
        thumb = _html.unescape(tm.group(1)) if tm else None
        ttl = re.search(
            r'field-name-title[^>]*>.*?<div class="field-item[^"]*">(.*?)</div>',
            body, re.S)
        title = _strip_tags(ttl.group(1)) if ttl else None
        results.append({
            "node_id": nid,
            "notice_url": urllib.parse.urljoin(PORTAL, _html.unescape(about)),
            "thumbnail": thumb,
            "title": title,
        })
    return {"count": count, "results": results}


def search(keywords, page=1, limit=None):
    """Public full-text search. Verified counts: 'tribunal de commerce'->191,
    'usine de Javel'->6. `page` is 1-indexed (page=0 is empty)."""
    return parse_search(_fetch(search_url(keywords, page, limit)))


# --------------------------------------------------------------------------- #
# 2. NOTICE (per-object metadata + rights)
# --------------------------------------------------------------------------- #
def parse_fields(html):
    """Parse the Drupal notice metadata blocks -> {field_name: {label, values}}.

    Field classes look like `<div class="field field-name-<name> ...">`, each
    with a `.field-label` and `.field-items > .field-item`. Keys of interest:
    field-oeuvre-auteurs, field-date-production, field-oeuvre-num-inventaire,
    field-musee, field-oeuvre-description-icono, field-oeuvre-epoque-periode.
    """
    out = {}
    marks = list(re.finditer(r'<div class="field field-name-([a-zA-Z0-9\-]+)', html))
    for i, m in enumerate(marks):
        fname = m.group(1)
        end = marks[i + 1].start() if i + 1 < len(marks) else m.start() + 3000
        chunk = html[m.start():end]
        lm = re.search(r'<div class="field-label">(.*?)<span', chunk, re.S)
        label = _strip_tags(lm.group(1)) if lm else ""
        items = re.findall(r'<div class="field-item [^"]*">(.*?)</div>', chunk, re.S)
        if not items:
            im = re.search(r'<div class="field-items">(.*?)</div>\s*</div>', chunk, re.S)
            items = [im.group(1)] if im else []
        vals = [v for v in (_strip_tags(x) for x in items) if v]
        if vals and fname not in out:
            out[fname] = {"label": label, "values": vals[:5]}
    return out


def parse_notice(html):
    """Parse a notice page -> structured record incl. per-item rights.

    Returns dict with: title, authors, date, inventory_number, museum,
    description, period, rights{cc0, iiif_manifest, download_zip, credit}.
    """
    f = parse_fields(html)

    def first(field):
        v = f.get(field, {}).get("values")
        return v[0] if v else None

    cc0 = ("publicdomain/zero" in html) or ("CC0" in html)
    z = re.search(r"/zip/oeuvre/(\d+)", html)
    ii = re.search(r"/iiif/(\d+)/manifest", html)
    cred = re.search(r"(CC0 Paris M[^<\n]{0,80})", html)

    return {
        "title": first("title-field"),
        "authors": first("field-oeuvre-auteurs"),
        "date": first("field-date-production"),
        "inventory_number": first("field-oeuvre-num-inventaire"),
        "museum": first("field-musee"),
        "description": first("field-oeuvre-description-icono"),
        "period": first("field-oeuvre-epoque-periode"),
        "rights": {
            "cc0": cc0,
            "iiif_manifest": (MANIFEST_TMPL.format(visuel_id=ii.group(1))
                              if ii else None),
            "download_zip": (ZIP_TMPL.format(node_id=z.group(1)) if z else None),
            "credit": cred.group(1).strip() if cred else None,
        },
    }


def notice(url_or_path):
    """Fetch + parse a notice page. Accepts a path (/fr/...) or full URL."""
    url = urllib.parse.urljoin(PORTAL, url_or_path)
    rec = parse_notice(_fetch(url))
    rec["notice_url"] = url
    return rec


# --------------------------------------------------------------------------- #
# 3. IIIF manifest -> full-resolution image (public, no auth)
# --------------------------------------------------------------------------- #
def parse_manifest(man):
    """Pick the full-size image @id (and label) out of a v2 manifest dict."""
    try:
        img = man["sequences"][0]["canvases"][0]["images"][0]["resource"]["@id"]
    except (KeyError, IndexError, TypeError):
        img = None
    return {"label": man.get("label"), "image_url": img,
            "manifest_url": None}


def manifest_image(visuel_id):
    """GET a public IIIF manifest and return its full-size image URL.

    `visuel_id` is the internal id found in a `/iiif/<visuel_id>/manifest`
    link on the notice page (NOT the node id, NOT the inventory number).
    """
    url = MANIFEST_TMPL.format(visuel_id=visuel_id)
    out = parse_manifest(json.loads(_fetch(url)))
    out["manifest_url"] = url
    return out


# --------------------------------------------------------------------------- #
# High-level convenience
# --------------------------------------------------------------------------- #
def resolve(keywords, page=1, limit=None, per_result_notice=False):
    """Search then (optionally) enrich the first page with per-item records.

    With per_result_notice=True each result gets a `notice` dict (rights,
    full-res image if CC0). Use sparingly -- one HTTP GET per result.
    """
    data = search(keywords, page=page, limit=limit)
    if per_result_notice:
        for r in data["results"]:
            try:
                rec = notice(r["notice_url"])
                if rec["rights"]["cc0"] and rec["rights"]["iiif_manifest"]:
                    vid = re.search(r"/(\d+)/manifest", rec["rights"]["iiif_manifest"])
                    if vid:
                        rec["full_image"] = manifest_image(vid.group(1))["image_url"]
                r["notice"] = rec
            except Exception as e:  # noqa: BLE001 - keep other results
                r["notice"] = {"error": repr(e)}
    return data


if __name__ == "__main__":  # tiny manual smoke test (no writes)
    d = search("tribunal de commerce")
    print("count:", d["count"], "| cards on page 1:", len(d["results"]))
    for card in d["results"][:3]:
        print(" -", card["title"], "->", card["notice_url"])
    rec = notice(d["results"][1]["notice_url"]) if d["results"] else {}
    print("sample notice rights:", rec.get("rights"))
