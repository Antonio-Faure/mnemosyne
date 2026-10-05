"""Archives departementales du Nord (AD Nord) - source reference for mnemosyne.

Site:    https://archivesdepartementales.lenord.fr
Focus:   industrial heritage of the Nord (textile, mines, metallurgie), plus
         the whole online image corpus.
NAAN:    33518  (ARK = /ark:/33518/<arkName>[/<uuid>])

RECON SUMMARY (verified 2026-xx, read-only, via http_get; NO captcha needed
for any read endpoint - hCaptcha only guards account/contact forms):

* Stack: Symfony + a JS front (front.js / common.js) built by Nao (naoned.fr).
  `<head data-captcha="hcaptcha">`. There is NO IIIF: the viewer payload has
  `location.iiif: null` and `toolbar.isIIIFEnabled: false` everywhere.

* Search - HTML only (no JSON search API exists; probed many `/api/*/v1/*`
  names -> 404, `/search/results.json` -> 404, `mode=map` etc. -> no JSON):
    GET /search/results?q=<q>&facet_media=image&page=<n>&resultsPerPage=<20|40|80>
  Server-rendered HTML. `facet_media=image` keeps only image records.
  Each <li class="element-list"> yields:
    - viewer link  href="/ark:/33518/<ark>/<uuid>"  (media viewer)
    - record link  href="https://.../ark:/33518/<ark>" (full notice)
    - thumbnail    src="/images/<uuid>_search_result_thumbnail.jpg"
    - <h2><span>Title</span></h2>
    - Date   <h3>Date</h3><p><span>1906</span></p>
    - Cote   <p class="referenceCodes">M 474 / 177</p>
    - "N medias" in <p class="info-list-picture">

* Viewer - JSON (the real media API):
    GET /visualizer/api?arkName=<ark>&uuid=<uuid>          -> STATE (dict)
    GET /visualizer/api?arkName=<ark>&start=<s>&end=<e>&group=0 -> LIST
  LIST notes: `group` is REQUIRED (omit it -> HTTP 400). `end` is INCLUSIVE.
  `start=0` returns a JSON ARRAY; `start>0` returns an OBJECT keyed by index.
  `end >= counts.media` -> HTTP 400, so cap at `end = counts.media - 1`.
  STATE dict keys: counts{media,group}, positions, group, media[..],
  app{name, licenses{visualizer:{uuid,locale,text,enabled}},
      toolbar{isDownloadEnabled,isIIIFEnabled}, security{csrfToken,
      captcha{isEnabled,name:'hcaptcha',postDataKey,publicKey}}},
  tableOfContents, bookmarks, indexationCampaign.
  Each media item: {url (asset page), uuid, type:"image", format:"jpg",
    title, record:{arkId:{arkName,naan}, url, title[], referenceCode[],
      description, period:{boundaries[],certainty}, locationKeywords[]},
    location:{original, thumb, iiif:null}}.

* Classification plan - JSON tree (the `/api/.../v1/...` route family):
    GET /api/classificationPlan/v1/tree/<nodeId>      -> node (+children)
    GET /api/classificationPlan/v1/children/<nodeId>  -> children list
  node: {id, title, data:{url (ark), contentUrl, childrenUrl}, dataType}
  leaf.contentUrl   = /record/<naan>/<ark>/content   (HTML fragment)
  branch.contentUrl = /archdesc/<uuid>/content
  root example nodeId:
    9d2669b4-6d3a-4410-a4e4-d950058c1a95_9d2669b4-6d3a-4410-a4e4-d950058c1a95

* Images (valid JPEG bytes; http_get raises UnicodeDecodeError on them which
  just means binary - the bytes are fine):
    /images/<uuid>.jpg                       (original)
    /images/<uuid>_thumbnail.jpg
    /images/<uuid>_img-notice.jpg
    /images/<uuid>_search_result_thumbnail.jpg
    /images/<uuid>_2_column.jpg
  No IIIF. No /iiif/ endpoint (all 404).

* Record content fragment (HTML): GET /record/<naan>/<ark>/content

* Other: /page/<slug>, /search/form/<uuid>, /user/api/v1/bookmark/record/<ark>.
  robots.txt disallows /oai-pmh but it 404s (no OAI endpoint found).
  sitemap.xml -> sitemaps/Editorial_1.xml + Search_1.xml/Search_2.xml (the
  Search sitemaps enumerate ~millions of /ark:/33518/<ark> notices).

LICENSE  -> RESTRICTIVE / NON-COMMERCIAL  => enabled: false
------------------------------------------------------------
Read from `app.licenses.visualizer.text` (identical across every record
sampled; `enabled: true`). Délibération du Conseil départemental du Nord du
27 mars 2017:
  "La réutilisation commerciale des informations publiques issues
   d'operations de numerisation des archives ... est soumise au paiement
   d'une redevance et a la souscription d'une licence. Une demande ecrite
   est a effectuer.
   Toute autre reutilisation est gratuite, avec obligation de citer la
   source (Archives departementales du Nord, cote) et de ne pas alterer ces
   informations."
=> Commercial reuse requires a paid fee + a signed licence, so per the task
   rule this source is `enabled: false`.
Conditions page: /page/reutilisation-des-informations-publiques

The connector body + the YAML descriptor + the mocked tests the coder needs
are embedded at the bottom of this file (SOURCE_YAML, CONNECTOR_SPEC, TESTS_PY).
"""

from __future__ import annotations

import html as _html
import json
import re

import requests

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/json,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

BASE_URL = "https://archivesdepartementales.lenord.fr"
NAAN = 33518

SEARCH_ENDPOINT = "/search/results"          # GET q, facet_media, page, resultsPerPage
VIEWER_ENDPOINT = "/visualizer/api"          # GET arkName(+uuid | +start&end&group)
TREE_ENDPOINT = "/api/classificationPlan/v1/{kind}/{node_id}"  # kind: tree|children
RECORD_CONTENT_ENDPOINT = "/record/{naan}/{ark}/content"

IMAGE_SUFFIXES = {
    "original": ".jpg",
    "thumbnail": "_thumbnail.jpg",
    "notice": "_img-notice.jpg",
    "search_result_thumbnail": "_search_result_thumbnail.jpg",
    "column": "_2_column.jpg",
}

# --- License (site-wide, restrictive/NC) -----------------------------------
LICENSE_ENABLED = False
LICENSE_URL = BASE_URL + "/page/reutilisation-des-informations-publiques"
LICENSE_TEXT = (
    "Réutilisation des informations publiques contenues dans les documents "
    "mis en ligne aux Archives départementales du Nord. La réutilisation "
    "commerciale ... est soumise au paiement d'une redevance et à la "
    "souscription d'une licence (demande écrite). Toute autre réutilisation "
    "est gratuite, avec obligation de citer la source et de ne pas altérer "
    "ces informations. (Délibération du Conseil départemental du Nord du "
    "27 mars 2017.)"
)

_ARK_RE = re.compile(r"/ark:/33518/([a-z0-9]+)(?:/([0-9a-f-]+))?")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _get(url, params=None, timeout=40):
    """GET returning the Response (raises on non-200), like the harness http_get."""
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout,
                     allow_redirects=True)
    r.raise_for_status()
    return r


def search_records(q, facet_media="image", page=1, results_per_page=20, timeout=40):
    """GET the HTML search page and return the raw HTML (str)."""
    r = _get(BASE_URL + SEARCH_ENDPOINT, params={
        "q": q, "facet_media": facet_media, "page": page,
        "resultsPerPage": results_per_page,
    }, timeout=timeout)
    return r.text


def parse_search_html(page_html):
    """Parse a /search/results HTML page into a list of result dicts.

    Each dict: {ark, uuid, title, date, cote, media_count,
                viewer_url, record_url, thumbnail, page_url}
    """
    out = []
    # split on the per-item container
    chunks = re.split(r'<li[^>]*class="[^"]*element-list[^"]*"', page_html)
    for chunk in chunks[1:]:
        m = _ARK_RE.search(chunk)
        if not m:
            continue
        ark = m.group(1)
        uuid = m.group(2)
        title = None
        tm = re.search(r"<h2>\s*<span>(.*?)</span>", chunk, re.S)
        if tm:
            title = _html.unescape(tm.group(1).strip())
        if not title:
            tm = re.search(r'title="Voir la notice compl[^"]*:\s*(.*?)"', chunk)
            if tm:
                title = _html.unescape(tm.group(1).strip())
        date = None
        dm = re.search(r"<h3>Date</h3>\s*<p><span>(.*?)</span>", chunk, re.S)
        if dm:
            date = _html.unescape(dm.group(1).strip())
        cote = None
        cm = re.search(r'class="referenceCodes">(.*?)</p>', chunk, re.S)
        if cm:
            cote = _html.unescape(cm.group(1).strip())
        media_count = None
        mm = re.search(r"(\d+)\s+medias", chunk)
        if mm:
            media_count = int(mm.group(1))
        thumb = None
        if uuid:
            tm2 = re.search(r'src="(/images/[^"]+\.jpg)"', chunk)
            if tm2:
                thumb = BASE_URL + tm2.group(1)
        out.append({
            "ark": ark,
            "uuid": uuid,
            "title": title,
            "date": date,
            "cote": cote,
            "media_count": media_count,
            "viewer_url": f"{BASE_URL}/ark:/33518/{ark}" + (f"/{uuid}" if uuid else ""),
            "record_url": f"{BASE_URL}/ark:/33518/{ark}",
            "thumbnail": thumb,
            "page_url": f"{BASE_URL}{SEARCH_ENDPOINT}?q=&facet_media=image",
        })
    return out


def fetch_viewer_state(ark_name, uuid, timeout=40):
    """GET /visualizer/api?arkName&uuid -> full state dict (has app/licenses)."""
    r = _get(BASE_URL + VIEWER_ENDPOINT,
             params={"arkName": ark_name, "uuid": uuid}, timeout=timeout)
    return r.json()


def fetch_viewer_media(ark_name, start=0, end=None, group=0, timeout=60):
    """GET the viewer LIST form. `end` inclusive. `group` required.

    Returns a list of media items. Caps `end` at counts.media-1 when end is
    None or too large (the API 400s when end >= counts.media).
    """
    if end is None:
        # discover the count first
        state = fetch_viewer_state(ark_name, _first_uuid(ark_name), timeout=timeout)
        count = int(state.get("counts", {}).get("media", 0))
        end = max(0, count - 1)
    r = _get(BASE_URL + VIEWER_ENDPOINT, params={
        "arkName": ark_name, "start": start, "end": end, "group": group,
    }, timeout=timeout)
    data = r.json()
    if isinstance(data, dict):          # start>0 -> keyed object
        return [data[k] for k in sorted(data, key=lambda x: int(x))]
    return data


def _first_uuid(ark_name):
    """Find one uuid for an ark by reading its notice page."""
    r = _get(f"{BASE_URL}/ark:/33518/{ark_name}")
    m = _UUID_RE.search(r.text)
    if not m:
        raise ValueError(f"no uuid found for ark {ark_name}")
    return m.group(0)


def record_media(ark_name, limit=None, timeout=60):
    """Convenience: every media item of a notice, with absolute image URLs.

    Each item: {uuid, ark, title, cote, date, period, image, thumbnail, iiif}
    """
    state = fetch_viewer_state(ark_name, _first_uuid(ark_name), timeout=timeout)
    count = int(state.get("counts", {}).get("media", 0))
    if count == 0:
        return []
    end = count - 1 if limit is None else min(count - 1, limit - 1)
    items = fetch_viewer_media(ark_name, start=0, end=end, group=0, timeout=timeout)
    out = []
    for it in items:
        rec = it.get("record", {}) or {}
        loc = it.get("location", {}) or {}
        out.append({
            "uuid": it.get("uuid"),
            "ark": (rec.get("arkId") or {}).get("arkName") or ark_name,
            "title": (rec.get("title") or [None])[0],
            "cote": (rec.get("referenceCode") or [None])[0],
            "period": (rec.get("period") or {}).get("boundaries"),
            "image": loc.get("original"),
            "thumbnail": loc.get("thumb"),
            "iiif": loc.get("iiif"),
        })
    return out


def image_urls(uuid):
    """All known derivative URLs for a media uuid (no network)."""
    return {k: f"{BASE_URL}/images/{uuid}{suf}" for k, suf in IMAGE_SUFFIXES.items()}


def classification_tree(node_id, timeout=40):
    return _get(BASE_URL + TREE_ENDPOINT.format(kind="tree", node_id=node_id),
                timeout=timeout).json()


def classification_children(node_id, timeout=40):
    return _get(BASE_URL + TREE_ENDPOINT.format(kind="children", node_id=node_id),
                timeout=timeout).json()


def license_info(ark_name, uuid, timeout=40):
    """Return the site-wide license block + a restrictive flag."""
    state = fetch_viewer_state(ark_name, uuid, timeout=timeout)
    lic = ((state.get("app") or {}).get("licenses") or {}).get("visualizer") or {}
    text = lic.get("text") or LICENSE_TEXT
    restrictive = ("redevance" in text.lower()) or ("licence" in text.lower())
    return {"text": text, "enabled": lic.get("enabled"),
            "restrictive": restrictive, "url": LICENSE_URL}


# ==========================================================================
# Deliverables for the coder (embedded so nothing is lost in the message).
# ==========================================================================

# Proposed config/sources/archives_nord.yaml
SOURCE_YAML = r"""
id: archives_nord
name: "Archives départementales du Nord"
homepage: https://archivesdepartementales.lenord.fr
enabled: false          # restrictive license: commercial reuse = fee + signed licence
protocol: json          # HTML search + JSON viewer; NO IIIF
base_url: https://archivesdepartementales.lenord.fr
naan: 33518
region: "Nord (France)"
topics: ["patrimoine industriel", "textile", "mines", "métallurgie"]
search:
  kind: html
  endpoint: /search/results
  params:
    q: "{query}"
    facet_media: image          # image-only results
    page: "{page}"
    resultsPerPage: 20          # 20 | 40 | 80
  parse: parse_search_html      # see harness/helpers/archives_nord.py
viewer:
  endpoint: /visualizer/api
  state:                        # full record state (counts + app/licenses)
    params: {arkName: "{ark}", uuid: "{uuid}"}
  media:                        # paginated media list (JSON array)
    params: {arkName: "{ark}", start: 0, end: "{end}", group: 0}
    notes: "end is inclusive; group required; end must be < counts.media"
tree:
  endpoint: /api/classificationPlan/v1/{tree|children}/{node_id}
  root: "9d2669b4-6d3a-4410-a4e4-d950058c1a95_9d2669b4-6d3a-4410-a4e4-d950058c1a95"
record_content:
  endpoint: /record/{naan}/{ark}/content    # HTML fragment
images:
  base: /images/{uuid}
  variants:
    original: ".jpg"
    thumbnail: "_thumbnail.jpg"
    notice: "_img-notice.jpg"
    search_result_thumbnail: "_search_result_thumbnail.jpg"
    column: "_2_column.jpg"
  iiif: null
license:
  enabled: false
  commercial: "redevance + licence signée (demande écrite)"
  non_commercial: "gratuite, attribution 'Archives départementales du Nord, cote' + no alteration"
  reference: "Délibération du Conseil départemental du Nord du 27 mars 2017"
  url: https://archivesdepartementales.lenord.fr/page/reutilisation-des-informations-publiques
""".strip()

# Connector spec the coder should implement (mirror of the helpers above).
CONNECTOR_SPEC = r"""
Module: mnemosyne/sources/archives_nord.py  (adapt to the repo layout)
- BASE_URL, NAAN=33518, endpoints as in SOURCE_YAML.
- search(query, page=1, per_page=20) -> list[dict]:
    GET /search/results?q&facet_media=image&page&resultsPerPage ; parse HTML.
- record_media(ark, limit=None) -> list[dict]:
    GET /visualizer/api?arkName&uuid  (state -> counts.media, app/licenses)
    GET /visualizer/api?arkName&start=0&end=count-1&group=0  (media array)
- license() -> dict: read app.licenses.visualizer.text ; restrictive -> enabled:false
- Because enabled:false, the runner must NOT fetch images by default; the
  connector exists for documentation + a future licensed integration.
Handle: viewer 400 when end >= counts.media (cap at count-1); `group` required;
start=0 -> array, start>0 -> keyed object.
""".strip()

# Mocked pytest suite the coder should drop in tests/ (no network).
TESTS_PY = r'''
"""Mocked tests for the Archives departementales du Nord connector.

No network: the HTML/JSON fixtures below are real shapes captured during recon.
"""
from mnemosyne.sources import archives_nord as an  # adapt import path

SEARCH_HTML = """
<ol>
<li class="element-list">
  <div class="img-element">
    <div class="img image-thumbnail">
      <a href="/ark:/33518/j0h8xbmd3tkn/284c50a2-dd55-417e-8a09-980bdab78f80"
         title="Visualiser le media">
        <img class="list-picture img-fluid"
             src="/images/284c50a2-dd55-417e-8a09-980bdab78f80_search_result_thumbnail.jpg"
             alt="DOUCHY-LES-MINES">
      </a>
      <p class="info-list-picture">107 medias</p>
    </div>
  </div>
  <section class="content">
    <div class="intitup">
      <a href="https://archivesdepartementales.lenord.fr/ark:/33518/j0h8xbmd3tkn"
         title="Voir la notice complète : DOUCHY-LES-MINES">
        <h2><span>DOUCHY-LES-MINES</span></h2>
      </a>
      <div class="date-cote content-part clearfix">
        <div class="content-sub-part"><h3>Date</h3><p><span>1906</span></p></div>
        <div class="content-sub-part"><h3>Cote</h3>
          <p class="referenceCodes">M 474 / 177</p></div>
      </div>
    </div>
  </section>
</li>
</ol>
"""

VIEWER_STATE = {
    "counts": {"media": 107, "group": 1},
    "positions": {"media": 0, "group": 0},
    "group": {"title": None},
    "media": [{
        "url": "https://archivesdepartementales.lenord.fr/ark:/33518/j0h8xbmd3tkn/284c50a2-dd55-417e-8a09-980bdab78f80",
        "record": {"arkId": {"arkName": "j0h8xbmd3tkn", "naan": 33518},
                   "url": "https://archivesdepartementales.lenord.fr/ark:/33518/j0h8xbmd3tkn",
                   "title": ["DOUCHY-LES-MINES"], "referenceCode": ["M 474 / 177"],
                   "period": {"boundaries": ["1906-01-01", "1906-12-31"]}},
        "uuid": "284c50a2-dd55-417e-8a09-980bdab78f80",
        "type": "image", "format": "jpg",
        "location": {"original": "https://archivesdepartementales.lenord.fr/images/284c50a2-dd55-417e-8a09-980bdab78f80.jpg",
                     "thumb": "https://archivesdepartementales.lenord.fr/images/284c50a2-dd55-417e-8a09-980bdab78f80_thumbnail.jpg",
                     "iiif": None},
    }],
    "app": {"licenses": {"visualizer": {
        "text": ("La réutilisation commerciale ... est soumise au paiement "
                 "d'une redevance et à la souscription d'une licence."),
        "enabled": True}},
        "toolbar": {"isDownloadEnabled": True, "isIIIFEnabled": False}},
}

VIEWER_LIST = [VIEWER_STATE["media"][0]]  # start=0 -> array


def test_parse_search_html():
    rows = an.parse_search_html(SEARCH_HTML)
    assert len(rows) == 1
    r = rows[0]
    assert r["ark"] == "j0h8xbmd3tkn"
    assert r["uuid"] == "284c50a2-dd55-417e-8a09-980bdab78f80"
    assert r["title"] == "DOUCHY-LES-MINES"
    assert r["date"] == "1906"
    assert r["cote"] == "M 474 / 177"
    assert r["media_count"] == 107
    assert r["record_url"].endswith("/ark:/33518/j0h8xbmd3tkn")


def test_image_urls():
    u = "284c50a2-dd55-417e-8a09-980bdab78f80"
    urls = an.image_urls(u)
    assert urls["original"].endswith(f"/images/{u}.jpg")
    assert urls["thumbnail"].endswith(f"/images/{u}_thumbnail.jpg")
    assert urls["iiif"] is None or "iiif" not in urls


def test_fetch_viewer_state(monkeypatch):
    class R:
        def json(self): return VIEWER_STATE
        def raise_for_status(self): pass
    monkeypatch.setattr(an.requests, "get", lambda *a, **k: R())
    st = an.fetch_viewer_state("j0h8xbmd3tkn", "284c50a2-dd55-417e-8a09-980bdab78f80")
    assert st["counts"]["media"] == 107
    assert st["app"]["toolbar"]["isIIIFEnabled"] is False


def test_fetch_viewer_media_array(monkeypatch):
    class R:
        def json(self): return VIEWER_LIST
        def raise_for_status(self): pass
    monkeypatch.setattr(an.requests, "get", lambda *a, **k: R())
    items = an.fetch_viewer_media("j0h8xbmd3tkn", start=0, end=0, group=0)
    assert isinstance(items, list) and items[0]["type"] == "image"
    assert items[0]["location"]["iiif"] is None


def test_fetch_viewer_media_keyed(monkeypatch):
    keyed = {"1": VIEWER_STATE["media"][0], "2": VIEWER_STATE["media"][0]}
    class R:
        def json(self): return keyed
        def raise_for_status(self): pass
    monkeypatch.setattr(an.requests, "get", lambda *a, **k: R())
    items = an.fetch_viewer_media("j0h8xbmd3tkn", start=1, end=2, group=0)
    assert len(items) == 2


def test_license_restrictive(monkeypatch):
    class R:
        def json(self): return VIEWER_STATE
        def raise_for_status(self): pass
    monkeypatch.setattr(an.requests, "get", lambda *a, **k: R())
    lic = an.license_info("j0h8xbmd3tkn", "284c50a2-dd55-417e-8a09-980bdab78f80")
    assert lic["restrictive"] is True
    assert an.LICENSE_ENABLED is False
'''


# --------------------------------------------------------------------------
# Offline self-test (no network) - run inside the harness to sanity-check.
# --------------------------------------------------------------------------
def _selftest():
    sample = """
    <li class="element-list">
      <a href="/ark:/33518/j0h8xbmd3tkn/284c50a2-dd55-417e-8a09-980bdab78f80">
        <img src="/images/284c50a2-dd55-417e-8a09-980bdab78f80_search_result_thumbnail.jpg">
      </a>
      <h2><span>DOUCHY-LES-MINES</span></h2>
      <h3>Date</h3><p><span>1906</span></p>
      <p class="referenceCodes">M 474 / 177</p>
      <p class="info-list-picture">107 medias</p>
    </li>"""
    rows = parse_search_html(sample)
    assert rows and rows[0]["ark"] == "j0h8xbmd3tkn", rows
    assert rows[0]["media_count"] == 107
    assert image_urls("abc")["original"].endswith("/images/abc.jpg")
    assert LICENSE_ENABLED is False
    return "ok"


if __name__ == "__main__":
    print(_selftest())
