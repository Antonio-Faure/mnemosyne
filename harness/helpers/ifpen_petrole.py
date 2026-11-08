"""IFPEN / Institut français du pétrole (IFP) — photographic-archive reconnaissance.

Reconnaissance by the mnemosyne navigator agent (task #190, source slug
``ifpen_petrole``, requested by the adversarial resolver for the phrase
yt_la_france_a_du_petrole_mais_elle_la_oublie).  Everything here is READ-ONLY:
the functions only GET and parse; nothing writes to any remote, ever.

==============================  BOTTOM LINE  ==============================
There is **no publicly accessible, programmatically-accessible photographic
archive of the IFP / IFPEN (Institut français du pétrole, founded 1944)** online.
IFPEN's own site exposes no photothèque/mediatheque and no image API/IIIF, and the
national archival aggregators that were checked do not surface a digitised IFP
oil-exploitation photo fonds (Parentis-en-Born, Lacq, bassin parisien, Schlumberger-
style mobile drilling/coring crews).  => ``ifpen_petrole`` cannot be wired as a
real IFPEN image connector today.

BUT the resolver's actual imagery need (French oil exploitation, Parentis/Lacq)
IS satisfiable from a real, open, programmatic source: the **Internet Archive
"ESSO FRANCE" petroleum-history corpus** (see IA section below) — verified
end-to-end here (advancedsearch + metadata + IIIF v3 Presentation + IIIF Image
API all 200).  It is ESSO corporate material, NOT IFPEN, and rights are unstated
=> reference/link only, never rehost.

==============================  EVIDENCE  ==============================
1) IFPEN official site  https://www.ifpenergiesnouvelles.fr  (Drupal corporate CMS)
   - Probed gallery-type URLs all return 404 (see PROBED_URL_404): /phototheque
     /mediatheque /medias /phototheque-historique /notre-histoire /histoire
     /patrimoine /galerie-photos.
   - robots.txt + sitemap.xml (-> ifpenergiesnouvelles.com/sitemap.xml?page=1..2).
   - Only "archive" on the homepage is HAL open-access PUBLICATIONS
     https://hal-ifp.archives-ouvertes.fr/ (scientific PDFs, NOT photos).
   - Media surfaces are corporate, not historical: /tags/videos,
     /tags/communiques-presse, /newsroom.  No image endpoint, no IIIF, no JSON API.

2) FranceArchives  https://francearchives.gouv.fr  (national archival aggregator)
   - IFP authority record  https://francearchives.gouv.fr/fr/agent/794087623
     links only to ARCHITECTURAL descriptions, e.g. "Immeubles de bureaux et
     laboratoires pour l'Institut français du pétrole" (Cité de l'architecture
     et du patrimoine) — buildings, not oil-field photographs.
   - Search UI is a bot-mitigated SPA (token redirect), client-side results.

3) Gallica (BnF)  https://gallica.bnf.fr  — SRU API  https://gallica.bnf.fr/SRU
   - SRU answers ONLY a real browser (bot UA -> HTTP 403).
   - "pétrole Parentis/Lacq", "forage pétrolier" return generic old PRINTED
     monographs/serials; no curated IFP/oil photo set.  (Gallica is already a
     catalog source; not IFPEN-specific.)

4) POP  https://api.pop.culture.gouv.fr  — "pétrole" (1044) = oil lamps; "Lacq"
   = gas-works (Mérimée, built heritage); no oil-exploitation photos, no IFP.

5) ANMT Roubaix  https://recherche-anmt.culture.gouv.fr  (ALREADY a catalog source,
   helper ligeo_archives.py) — "pétrole" => 13 hits, coal-mining / finance
   (Charbonnages de France photothèque); no IFP/Elf/SNPA petroleum-field photo
   fonds surfaced.  Plain HTTP is challenged by "Anubis"; use the browser.

6) Internet Archive  https://archive.org   *** the real, verified imagery ***
   31 issues of "ESSO REVUE" (Jan 1950 – Nov 1952) + the two field books:
     - "Histoire De Parentis ESSO 1955"  id histoire-de-parentis-esso-1955_202502
       (Esso France - Esso Standard, IIIF v3, 25 canvases)
     - "Le pétrole des Landes ESSO 1957" id petrole-des-landes-esso-1957
       (Esso France, IIIF v3, 38 canvases)
   ESSO REVUE = Esso France's illustrated corporate magazine: rich period
   photography of French oil refining / distribution / the emerging basins.
   All under IIIF v3; open APIs.  licenceurl/rights = None on every item
   (rights UNCLEAR => reference only, no rehost; descriptor should mark unknown).

==============================  RECOMMENDATION  ==============================
- Descriptor for `ifpen_petrole`: ``enabled: false`` with reason
  "no public IFPEN/IFP photographic archive or API exists".
- For the resolver's French-oil imagery, add a SEPARATE source on the Internet
  Archive ESSO corpus (e.g. slug ``ia_esso_petrole``), using discover_ia_esso_corpus()
  + ia_iiif_manifest() + ia_page_image_url() below.  Label as ESSO/period docs on
  IA, licence unknown, reference only.
- IFPEN's historic IFP photothèque itself needs official access via an outreach
  e-mail to IFPEN (per docs/OUTREACH.md) if the operator wants it.
"""

from __future__ import annotations

import time

import requests

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json, */*"}

# IFPEN gallery-type URLs probed -> HTTP 404 (no photothèque exists).
PROBED_URL_404 = [
    "https://www.ifpenergiesnouvelles.fr/phototheque",
    "https://www.ifpenergiesnouvelles.fr/mediatheque",
    "https://www.ifpenergiesnouvelles.fr/medias",
    "https://www.ifpenergiesnouvelles.fr/phototheque-historique",
    "https://www.ifpenergiesnouvelles.fr/notre-histoire",
    "https://www.ifpenergiesnouvelles.fr/histoire",
    "https://www.ifpenergiesnouvelles.fr/patrimoine",
    "https://www.ifpenergiesnouvelles.fr/galerie-photos",
]

# Verified Internet Archive French-oil-exploitation items (ESSO, NOT IFPEN).
IA_PETROLEUM_ITEMS = {
    "histoire-de-parentis-esso-1955_202502": {
        "title": "Histoire De Parentis ESSO 1955",
        "creator": "Esso France - Esso Standard",
        "date": "1955-05-02",
        "iiif_version": "3",
        "canvases": 25,
        "license": None,
    },
    "petrole-des-landes-esso-1957": {
        "title": "Le pétrole des Landes ESSO 1957",
        "creator": "Esso France",
        "date": "1957-06",
        "iiif_version": "3",
        "canvases": 38,
        "license": None,
    },
}

IA_SS = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/"
IA_IIIF = "https://iiif.archive.org/iiif/"


def _get(url: str, tries: int = 3, timeout: int = 60) -> requests.Response | None:
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (attempt + 1))
    return None


def ia_search(query: str, rows: int = 60) -> list[dict]:
    """Internet Archive advancedsearch -> list of item docs (open API, no key)."""
    params = [
        ("q", query), ("rows", rows), ("output", "json"),
        ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "date"),
        ("fl[]", "creator"), ("fl[]", "mediatype"),
    ]
    r = _get(IA_SS + "?" + "&".join(
        f"{requests.utils.quote(str(k))}={requests.utils.quote(str(v))}"
        for k, v in params))
    if r is None:
        return []
    try:
        return r.json().get("response", {}).get("docs", []) or []
    except Exception:  # noqa: BLE001
        return []


def discover_ia_esso_corpus() -> dict:
    """Return the verified French-oil-exploitation corpus on the Internet Archive.

    {"esso_revue": [docs...], "field_books": [docs...]} — all IIIF v3, open.
    """
    revue = ia_search('title:("ESSO REVUE")', 80)
    books = []
    for q in ('Parentis pétrole', '"pétrole des Landes"'):
        for d in ia_search(q, 20):
            ident = d.get("identifier", "")
            if ident and ("parentis" in ident or "petrole-des-landes" in ident):
                books.append(d)
    seen = set()
    uniq = []
    for d in books:
        i = d.get("identifier")
        if i not in seen:
            seen.add(i)
            uniq.append(d)
    return {"esso_revue": revue, "field_books": uniq}


def ia_iiif_manifest(identifier: str) -> dict:
    """Summarise an Internet Archive IIIF manifest (v3) for one item.  Read-only."""
    out = {"ok": False, "status": None, "version": None, "canvases": 0,
           "image_service": None, "error": None}
    r = _get(f"{IA_IIIF}{identifier}/manifest.json")
    if r is None:
        out["error"] = "no_200_response"
        return out
    out["status"] = r.status_code
    try:
        d = r.json()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"not_json:{exc}"[:80]
        return out
    if "items" in d:
        out["version"] = "3"
        out["canvases"] = len(d["items"])
        try:
            body = d["items"][0]["items"][0]["items"][0]["body"]
            svc = body.get("service")
            if isinstance(svc, list):
                svc = svc[0]
            out["image_service"] = (svc or {}).get("id") or (svc or {}).get("@id")
        except Exception:  # noqa: BLE001
            pass
    elif "sequences" in d:
        out["version"] = "2"
        out["canvases"] = sum(len(s.get("canvases", [])) for s in d["sequences"])
    out["ok"] = out["version"] is not None
    return out


def ia_page_image_url(image_service: str, size: int = 400) -> str:
    """Build a bounded IIIF Image API v3 URL from a canvas image service id.

    Verified: .../full/!400,400/0/default.jpg -> 200 image/jpeg.
    Use bounded sizes only; /full/max/0/default.jpg is huge and slow.
    """
    return f"{image_service}/full/!{int(size)},{int(size)}/0/default.jpg"


if __name__ == "__main__":  # tiny self-check
    corpus = discover_ia_esso_corpus()
    print("ESSO REVUE issues:", len(corpus["esso_revue"]),
          "| field books:", len(corpus["field_books"]))
    for ident in IA_PETROLEUM_ITEMS:
        print(ident, ia_iiif_manifest(ident))
