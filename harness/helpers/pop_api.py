"""POP — Plateforme Ouverte du Patrimoine (ministère de la Culture) API reference.

Discovered by the navigator agent (mnemosyne). The routes are NOT literal strings
in the frontend bundle: the Next.js app ships a *generated OpenAPI client*
(chunk `4994-*.js`) whose endpoint table is built from `{method, path,
pathPrefix}` triples. The routes below were read from that table and then
replayed as live XHR / HTTP calls (all 200).

Hosts
-----
API .............. https://api.pop.culture.gouv.fr        (open, NO auth, JSON)
IIIF Image API ... https://iiif.prd.cloud.culture.fr/iiif/3
Asset bucket ..... https://popcorn-prd-perf-assets.s3.gra.io.cloud.ovh.net
Frontend ......... https://pop.culture.gouv.fr
(runtimeEnv in layout-*.js: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_BUCKET_URL,
 NEXT_PUBLIC_DIFFUSION_URL)

The API answers ANY User-Agent (browser, curl, bot) with JSON. No key, no auth
header, no CORS origin needed server-side. Elasticsearch-backed (`took`,
`timed_out`, `total`, `aggregations`, `hits[]._index/_id/_score/_source`).

DatabasesNamesEnum (path segment / `bases[]` value -> frontend label)
--------------------------------------------------------------------
joconde=Joconde  museo=Muséofile  merimee=Mérimée  memoire=Mémoire
palissy=Palissy  autor=Autor      rose-valland=Rose-Valland  enluminures=Enluminures

Routes (pathPrefix + path)
--------------------------
/search  GET  /simple                 SimpleSearchQuerySchema  -> OpenSearchResult
/search  GET  /facets                 FacetsQuerySchema        -> AggregationsResult
/search  POST /advanced               AdvancedSearchBodySchema -> OpenSearchResult
/search  GET  /advanced-fields/diffusion -> [{base, fields, label, isDefault, fieldType}]
/search  GET  /export-simple          (same query as /simple; public CSV/export)

/notices GET  /:database/:noticeRef               -> notice object (no wrapper)
/notices GET  /:database/:noticeRef/public      -> {"notice":{...},"sections":[...],"fields":[...]}
/notices GET  /:database/:noticeRef/iiif/manifest -> IIIF Presentation v3 Manifest

Query serialisation (/search/simple, bracket notation, all confirmed)
---------------------------------------------------------------------
  text=<free text>            full-text (multi_match)
  from=<int>                  offset  (default 0)
  size=<int>                  page size (default 20; tested up to 2000)
  bases[0]=memoire            restrict to a database (array)
  facets[base][0]=memoire     facet-style filter (same effect on /search/simple)
  facets[<FIELD>][0]=<value>  filter on any facetable field
  filters[hasImage]=true      only notices carrying an image
  filters[hasCoordinates]=true
  sort[0][<field>]=asc|desc   sortable field; text fields need `.keyword`
                              (e.g. sort[0][NUM.keyword]=asc). `_score` works.
  search_after[0]=<value>     deep pagination (pair with a unique-field sort)
  geo=true

  NOTE: on /search/simple both `bases[0]=memoire` and `facets[base][0]=memoire`
  restrict results (text=usine total 64830 -> 48196 with either filter).

FacetsQuerySchema: text, fields[] (fields[0]=DOM ...), bases[]/facets{}, query,
  size (default 20). Aggregations come back keyed "<FIELD>.keyword" with buckets
  [{key, doc_count}]. `total` in the facets reply is the WHOLE index size, not
  the filtered count.

AdvancedSearchBodySchema (POST /search/advanced, JSON body)
-----------------------------------------------------------
{
  "bases": ["memoire"],
  "crits": [ {"crits":[ {"base":"memoire",
                         "fields":"TICO, SUJET, TITRE, LEG",
                         "operator":"*","value":"usine"} ],
              "combinator":"AND"} ],
  "size": 20, "from": 0, "search_after": [...], "sort": [{"NUM.keyword":"asc"}]
}
Operators: * contient | == égal | ^ commence par | !* | != | ===* | === | ===^
  | !==* | !== | >= | <= | > | ∃ (existe) | !∃ (n'existe pas).
`fields` is a comma-separated list of field GROUPS from
/search/advanced-fields/diffusion. e.g. memoire group "Sujet de la photographie"
= "MCPER, ROLE, THEATRE, DOM, EDIF, MCL, LEG, SERIE, TITRE, OBJT, DENO, TICO,
SUJET".

Notice fields — base Mémoire (photographs)
------------------------------------------
REF            notice reference used in /notices paths (e.g. "SAPR44_20235700043")
_id            ES id — NOT a valid noticeRef
IMG            STRING path, e.g. "memoire/SAPR44_20235700043/sapr44_...jpg"
VIDEO          optional video path
COPY           credit / rights statement ("© Ministère de la Culture ... Tous
               droits réservés")
DIFF           reuse statement, the authoritative rights text (may be empty)
MANIFEST_IIIF  (usually empty in _source; build via /iiif/manifest instead)
CONTIENT_IMAGE "oui"/"non"
Plus descriptive fields: TITRE, LEG, DOM, DENO, EDIF, SUJET, TICO, NUM, ...

Notice fields — base Joconde (museum objects) DIFFERENCES
---------------------------------------------------------
IMG   is a LIST of paths (one object -> many photos)
DIFFU "oui"/"non"  (diffusable flag)
COPY  credit / rights statement
UTIL  is a SUBJECT thesaurus (usage/function), NOT a rights field
REF   e.g. "06180000873"

Images / IIIF
-------------
IIIF Image API v3, level 2. For an IMG path P (URL-quote with safe=""):

  info.json  https://iiif.prd.cloud.culture.fr/iiif/3/<quote(P,safe='')>/info.json
  full       .../<quote(P,safe='')>/full/max/0/default.jpg
  thumb      .../<quote(P,safe='')>/full/200,/0/default.jpg

  Direct asset bucket (no IIIF): https://popcorn-prd-perf-assets.s3.gra.io.cloud.ovh.net/<P>

  Per-notice IIIF Presentation v3 manifest:
  https://api.pop.culture.gouv.fr/notices/<db>/<ref>/iiif/manifest
  -> items[].items[].items[].body.service[0].id is the ImageService3 id.

Rights model (IMPORTANT)
------------------------
* METADATA: POP's global terms are "Sauf mention contraire ... Licence etalab-2.0"
  (CGU + footer). The public CRPA notice metadata is free to reuse, incl.
  commercial. So the *catalogue metadata* is effectively Licence Ouverte 2.0.
* IMAGES: governed PER NOTICE by the rights text in DIFF (memoire) / DIFFU+COPY
  (joconde). These are PREDOMINANTLY restrictive. Live DIFF facet distribution
  on base memoire:
      "reproduction soumise à autorisation du titulaire ..."   1 018 341
      "communication libre, reproduction soumise à autorisation" 161 777
      "tous droits réservés"                                       5 494
      "reproduction interdite"                                     3 399
      "communication libre, reproduction interdite"                  619
  => The task hint "souvent Licence Ouverte/CC BY-SA" applies to METADATA, not
     to the images. A connector must therefore carry a per-notice restrictive
     flag and NOT republish restricted images.

Corpus sizes (search/simple, filters[hasImage]=true)
----------------------------------------------------
  memoire:  usine=47 992  machine=8 238  chantier=7 816
  joconde:  usine=3 256   machine=863    chantier=1 231

Self-contained HTTP: urllib (no third-party deps). When running inside the
browser harness, `http_get` is available too and is equivalent.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

API_BASE = "https://api.pop.culture.gouv.fr"
IIIF_IMAGE_BASE = "https://iiif.prd.cloud.culture.fr/iiif/3"
ASSET_BUCKET = "https://popcorn-prd-perf-assets.s3.gra.io.cloud.ovh.net"
FRONTEND = "https://pop.culture.gouv.fr"

DATABASES = [
    "joconde", "museo", "merimee", "memoire",
    "palissy", "autor", "rose-valland", "enluminures",
]

# Industrial-heritage search terms for base Mémoire / Joconde.
INDUSTRIAL_TERMS = [
    "usine", "manufacture", "atelier", "machine", "machinerie", "moteur",
    "chantier", "fabrique", "filature", "tissage", "forge", "fonderie",
    "haut-fourneau", "aciérie", "minoterie", "sucrerie", "brasserie",
    "papeterie", "briqueterie", "tuilerie", "verrerie", "corderie",
    "scierie", "moulin", "cheminée d'usine", "chevalement", "grue",
    "wagon", "locomotive", "locomobile", "chaudière", "turbine",
]

_UA = "mnemosyne/1.0 (+https://github.com/Antonio-Faure/mnemosyne)"


# --------------------------------------------------------------------------- #
# low-level
# --------------------------------------------------------------------------- #
def _get_json(url: str, timeout: int = 30) -> dict:
    """GET a POP endpoint and return parsed JSON. Open API: no auth needed."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _qs(params: dict) -> str:
    """Serialize a POP query dict with bracket notation into a query string."""
    return urllib.parse.urlencode(params, doseq=True)


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #
def search_simple(params: dict) -> dict:
    """GET /search/simple. `params` uses bracket keys, e.g.:
        {"text": "usine", "bases[0]": "memoire", "filters[hasImage]": "true",
         "from": 0, "size": 20}
    Returns the OpenSearchResult (keys: took, total, hits, aggregations, ...).
    """
    return _get_json(f"{API_BASE}/search/simple?{_qs(params)}")


def search_page(base: str, text: str, offset: int = 0, size: int = 100,
                has_image: bool = True, sort: str | None = None) -> dict:
    """Convenience wrapper around search_simple for one database + free text."""
    p = {"text": text, "bases[0]": base, "from": offset, "size": size}
    if has_image:
        p["filters[hasImage]"] = "true"
    if sort:
        p["sort[0][" + sort + "]"] = "asc"
    return search_simple(p)


def facets(base: str, field: str, size: int = 20, text: str = "") -> dict:
    """GET /search/facets. Aggregations are keyed "<FIELD>.keyword"."""
    p = {"bases[0]": base, "fields[0]": field, "size": size}
    if text:
        p["text"] = text
    return _get_json(f"{API_BASE}/search/facets?{_qs(p)}")


def search_advanced(body: dict) -> dict:
    """POST /search/advanced. See AdvancedSearchBodySchema in the docstring."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}/search/advanced", data=data,
                                 headers={"User-Agent": _UA,
                                          "Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def advanced_fields() -> list:
    """GET /search/advanced-fields/diffusion -> list of {base, fields, label,
    isDefault, fieldType}."""
    return _get_json(f"{API_BASE}/search/advanced-fields/diffusion")


# --------------------------------------------------------------------------- #
# notices
# --------------------------------------------------------------------------- #
def notice(db: str, ref: str) -> dict:
    """GET /notices/:db/:ref -> the notice object directly (no wrapper)."""
    ref = urllib.parse.quote(str(ref), safe="")
    return _get_json(f"{API_BASE}/notices/{db}/{ref}")


def notice_public(db: str, ref: str) -> dict:
    """GET /notices/:db/:ref/public -> {"notice":{...},"sections":[...],"fields":[...]}."""
    ref = urllib.parse.quote(str(ref), safe="")
    return _get_json(f"{API_BASE}/notices/{db}/{ref}/public")


def iiif_manifest(db: str, ref: str) -> dict:
    """GET /notices/:db/:ref/iiif/manifest -> IIIF Presentation v3 Manifest."""
    ref = urllib.parse.quote(str(ref), safe="")
    return _get_json(f"{API_BASE}/notices/{db}/{ref}/iiif/manifest")


# --------------------------------------------------------------------------- #
# images / IIIF
# --------------------------------------------------------------------------- #
def _enc(path: str) -> str:
    return urllib.parse.quote(path, safe="")


def iiif_info_url(path: str) -> str:
    return f"{IIIF_IMAGE_BASE}/{_enc(path)}/info.json"


def iiif_image_url(path: str, size: str = "max", rotation: int = 0,
                   quality: str = "default", fmt: str = "jpg") -> str:
    """IIIF Image API v3 URL. size examples: "max", "200,", "1024,"."""
    return f"{IIIF_IMAGE_BASE}/{_enc(path)}/full/{size}/{rotation}/{quality}.{fmt}"


def iiif_thumb_url(path: str, width: int = 200) -> str:
    return iiif_image_url(path, size=f"{width},")


def bucket_url(path: str) -> str:
    return f"{ASSET_BUCKET}/{path}"


def notice_image_paths(src: dict) -> list:
    """Return IMG path(s) for a notice _source, tolerating str OR list."""
    img = src.get("IMG")
    if not img:
        return []
    if isinstance(img, str):
        return [img] if img.strip() else []
    if isinstance(img, (list, tuple)):
        return [p for p in img if isinstance(p, str) and p.strip()]
    return []


# --------------------------------------------------------------------------- #
# rights
# --------------------------------------------------------------------------- #
_RESTRICTIVE_MARKERS = (
    "soumis", "soumise", "interdit", "interdite", "tous droits",
    "autorisation", "ayant droit", "ayants droit", "non diffus",
    "non diffusable", "droits réservés", "droits reserves", "©", "(c)",
)

_FREE_MARKERS = (
    "domaine public", "public domain", "creative commons", "cc0", "cc by",
    "licence ouverte", "etalab", "libre de droits", "sans restriction",
    "communication libre",  # NOTE: often paired with a reproduction caveat
)


def is_restrictive(src: dict) -> bool:
    """Conservative per-notice rights test.

    Returns True when the notice's rights text looks restrictive (so the
    connector must NOT republish the image). Checks memoire DIFF/COPY and
    joconde DIFFU/COPY.

    Conservative default: if there is no positive free-reuse signal, treat the
    notice as restrictive (True).
    """
    # Joconde explicit flag
    diffu = src.get("DIFFU")
    if isinstance(diffu, str) and diffu.strip():
        if diffu.strip().lower() in ("non", "no", "false"):
            return True
        if diffu.strip().lower() in ("oui", "yes", "true"):
            # still confirm the text isn't carrying a restriction caveat
            pass

    text = " ".join(
        str(src.get(k, "")) for k in ("DIFF", "COPY", "MENTIONS", "REPRO")
    ).lower()

    if not text.strip():
        # No rights statement -> do not assume it is freely reusable.
        return True

    # A clear free marker only wins if no restrictive marker is present.
    has_free = any(m in text for m in _FREE_MARKERS)
    has_restrict = any(m in text for m in _RESTRICTIVE_MARKERS)
    if has_restrict:
        return True
    if has_free:
        return False
    return True
