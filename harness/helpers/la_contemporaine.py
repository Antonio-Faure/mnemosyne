"""La Contemporaine (ex-BDIC), Nanterre — bibliothèque numérique L'Argonnaute.

Référence read-only, écrite par l'agent navigateur (Archivist) pour mnemosyne.
C'est le module que le codeur utilise pour bâtir
`config/sources/la_contemporaine.yaml` + son connecteur. Il n'écrit rien sur le
distant, ne copie/réhéberge aucune image : il renvoie des URLs publiques
servies par l'institution (hotlink). mnemosyne n'héberge pas l'image.

Institution : La Contemporaine, 184 cours Nicole Dreyfus, 92001 Nanterre.
Bibliothèque numérique : **L'Argonnaute**.
~200 000 documents numérisés (imprimés, archives, dessins, photographies,
affiches). Fonds clés : « Albums Valois » (PGM 1914-1918), presse 1914-1918,
affiches (PGM, Entre-Deux-Guerres 1918-1939, Après-Guerre 1945-1989, Mai 68),
et la grande collection photographique « France, entre-deux guerres
1918-1939. Photographies » (Cote PH C1-C5, ~1372 objets).
Labellisée **Culture Libre** : œuvres du domaine public réutilisables sous
**Licence Ouverte** ; le reste « Tous droits réservés ».

=====================================================================
DOMAINE — ATTENTION
=====================================================================
Le domaine correct est **https://argonnaute.parisnanterre.fr**
(le domaine `argonnaute.contemporaine-parisnanterre.fr` ne résout PAS — DNS
NXDOMAIN, vérifié). Utiliser parisnanterre.fr.

=====================================================================
CHEMIN D'ACCÈS VÉRIFIÉ  (re-vérifié en direct)
=====================================================================
1) PAS de IIIF. L'instance a `app.toolbar.isIIIFEnabled = false` dans son JSON,
   `location.iiif = null` sur chaque média, et tous les chemins IIIF renvoient
   404 (`/iiif/2/<uuid>/info.json`, `/iiif/<ark>/manifest`, `/manifest/<ark>`,
   `/images/<uuid>.jp2`). => NE PAS chercher un manifest IIIF : il n'existe pas.

2) PAS d'index de recherche JSON. La recherche est rendue CÔTÉ SERVEUR (HTML).
   Le bundle JS (`/static/js/main.*.js`) n'expose que `/visualizer/api*` et
   `/user/api/v1/*`. Il n'y a ni `/api/search`, ni Solr/Elasticsearch public.

3) IL Y A un **endpoint JSON par document** (métadonnées riches) :
       GET https://argonnaute.parisnanterre.fr/visualizer/api
           ?arkName=<ARK>&uuid=<UUID>
   -> JSON : media[0].record {title, referenceCode, description, period
      {boundaries:[from,to]}, locationKeywords}, media[0].location
      {original, thumb, iiif:null}, et app.licenses.visualizer.text (le texte
      de licence global). C'est l'API exploitable pour les métadonnées d'un item.

4) Les IMAGES sont des assets publics directs (hotlink, aucun IIIF) :
       original : https://argonnaute.parisnanterre.fr/images/<UUID>.jpg
       vignette : https://argonnaute.parisnanterre.fr/images/<UUID>_search_result_thumbnail.jpg
   (aussi `<UUID>_thumbnail.jpg`). Vérifié : HTTP 200 image/jpeg.

=> MODÈLE CONNECTEUR = (a) découverte par le HTML de recherche SSR, puis
   (b) métadonnées par item via /visualizer/api, images par hotlink /images/*.jpg.

robots.txt (User-agent: *) : Disallow /private/, /oai-pmh, /user/ — TOUT LE
RESTE EST AUTORISÉ, dont /search/results, /visualizer/api, /images/.
ATTENTION : robots.txt bloque nommément GPTBot, OAI-SearchBot, Applebot,
meta-externalagent, AhrefsBot, SemrushBot, Amazonbot, PetalBot, etc.
=> Noter UA descriptif `mnemosyne-research-bot/1.0` (il passe, 200). Ne PAS
usurper les UA bloqués. Cadence douce (0.5-1 s entre requêtes). Pas d'/oai-pmh
(inutile de toute façon : oai_dc = simple UUID).

Anti-bot : pas d'Anubis/Cloudflare sur ces pages. `requests` + UA descriptif
reçoit la vraie page (200, résultats présents). Un `data-captcha="hcaptcha"`
traîne dans le <head> mais ne bloque PAS la lecture (formulaire de contact).

=====================================================================
RECHERCHE (découverte) — HTML, GET
=====================================================================
    https://argonnaute.parisnanterre.fr/search/results
        ?q=<requête>&scope=all
        &facet_media=image            # seulement les images (recommandé)
        &facet_typology=Photographie  # optionnel, resserre sur photos
        &page=<N>                     # pagination 1-based
        &resultsPerPage=20|40|80      # 20 par défaut
    - SÉMANTIQUE AND : plusieurs mots = tous requis. Requêtes courtes (2-3
      mots) ; q supporte les guillemets.
    - Le total « N résultats » est dans la page ; nb de pages dans
      `<input name="page" ... max="M">` (ex. 45 pages pour « ouvriers »).
    - Facettes disponibles : facet_media, facet_typology, facet_century,
      facet_decade, facet_corpName, facet_personalName, facet_geographicName,
      facet_subject, facet_titleProper. PAS de facette « droits/licence ».

CARTE DE RÉSULTAT (une <li class="element-list">) :
    <a href="/ark:/14707/<ARK>/<UUID>" title="Visualiser le media">   (image)
    <img src="/images/<UUID>_search_result_thumbnail.jpg" alt="<TITRE>">
    <a href="https://argonnaute.parisnanterre.fr/ark:/14707/<ARK>"
       title="Voir la notice complète : <TITRE>"><h2><span><TITRE></span></h2></a>
    <div class="date-cote"> ... <h3>Date</h3><p><span><DATE></span></p>
                              <h3>Cote</h3><p class="referenceCodes"><COTE></p>
    <ul class="context"> ... Contexte : <COLLECTION>
NB : <ARK> = ark de la collection/notice parente ; <UUID> = le média précis
(un item = un média). La « notice complète » pointe sur l'ARK, mais les vraies
métadonnées de l'item (titre/date/desc/lieu) viennent de /visualizer/api.

=====================================================================
COUVERTURE vérifiée (facet_media=image) — pour la phrase « condition ouvrière
et grandes grèves chez Citroën (Javel, 1933/1936) »
=====================================================================
    'Citroën'          -> 102 (89 photos)   (surtout Albums Valois PGM 1915)
    'Citroën Javel'    ->  75 (75 photos)    (tout 1915)
    'grève Citroën'    ->   5 (0 photos)     (affiches 1968 + 1 affiche 1919/39)
    'usines Citroën'   ->  90 (88 photos)
    'grèves 1936'      -> 235 (235 photos)   <- vraies photos de grèves 1930s
    'Front populaire'  -> 339 (299 photos)
    'manifestation ouvriers' -> 277 (231 photos)
    'métallurgistes'   -> 213 (211 photos)
    'occupation usine' ->  23 (7 photos)
    'grève 1933'       ->  10 (10 photos)
=> Le fonds couvre TRÈS BIEN la condition ouvrière / les grandes grèves des
   années 1930 (photos), et correctement Citroën-Javel mais surtout 1915 (PGM).
   Il n'y a PAS de photo « grève Citroën Javel 1936 » isolée : la couverture
   Citroën est PGM + affiches. À signaler honnêtement au résolveur.

=====================================================================
DROITS / LICENCE
=====================================================================
Texte de licence global (app.licenses.visualizer.text via /visualizer/api) :
« Les conditions de réutilisation ... varient selon ... domaine public ou ...
droits d'auteur. ... Pour les œuvres du domaine public, la réutilisation est
libre et gratuite, à condition d'indiquer leur source selon les termes de la
Licence Ouverte / Open Licence. Les documents protégés ... « Tous droits
réservés » ... soumises à l'accord préalable de La contemporaine. »
=> Il n'y a PAS de champ « droits » machine-readable par item ni de facette
   dédiée : la notice expose parfois « Conditions d'utilisations » (absent sur
   les items échantillonnés). Attribuer : « La Contemporaine / L'Argonnaute,
   Licence Ouverte (œuvres du domaine public) — voir la notice » et toujours
   renvoyer à la notice (record_url). Ne PAS affirmer un domaine public non
   vérifié : afficher la licence connue + lien.
"""

from __future__ import annotations

import html
import re

import requests

BASE = "https://argonnaute.parisnanterre.fr"
UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource archive image search engine)"
)
HEADERS = {"User-Agent": UA, "Accept": "*/*"}

LATIN = False  # UTF-8 partout.

# Résumé de licence affiché côté mnemosyne (dérivé du texte global de l'app).
LICENSE_SUMMARY = (
    "La Contemporaine / L'Argonnaute. Œuvres du domaine public : réutilisation "
    "libre sous Licence Ouverte (attribution requise). Autres documents : "
    "« Tous droits réservés », voir la notice du document."
)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _total(txt: str) -> int:
    m = re.search(r"(\d[\d\s\t]*)\s*r[ée]sultats?", txt, re.I)
    if not m:
        return 0
    try:
        return int(re.sub(r"\s", "", m.group(1)))
    except ValueError:
        return 0


def image_url(uuid: str) -> str:
    return f"{BASE}/images/{uuid}.jpg"


def thumb_url(uuid: str) -> str:
    return f"{BASE}/images/{uuid}_search_result_thumbnail.jpg"


def search(q: str, page: int = 1, per_page: int = 20, images_only: bool = True,
           typology: str | None = None, timeout: int = 30) -> tuple[int, list[dict]]:
    """Recherche HTML SSR. Renvoie (total, items[]).

    Chaque item : ark, uuid, path, title, date, cote, collection, thumb.
    """
    params = {"q": q, "scope": "all", "page": page, "resultsPerPage": per_page}
    if images_only:
        params["facet_media"] = "image"
    if typology:
        params["facet_typology"] = typology
    r = requests.get(f"{BASE}/search/results", headers=HEADERS, params=params,
                     timeout=timeout)
    r.raise_for_status()
    txt = r.text
    total = _total(txt)
    items: list[dict] = []
    for blk in re.findall(r'<li class="element-list">.*?</li>', txt, re.S):
        a = re.search(r'href="(/ark:/14707/([^/"]+)/([^"/]+))"[^>]*title="Visualiser', blk)
        if not a:
            continue
        title = re.search(r"<h2>\s*<span>(.*?)</span>", blk, re.S)
        date = re.search(r"<h3>Date</h3>\s*<p><span>(.*?)</span>", blk, re.S)
        cote = re.search(r"<h3>Cote</h3>\s*<p[^>]*>(.*?)</p>", blk, re.S)
        ctx = re.search(r"Contexte\s*:\s*([^<]+)", blk)
        thumb = re.search(r'<img[^>]+src="(/images/[^"]+)"', blk)
        items.append({
            "ark": a.group(2),
            "uuid": a.group(3),
            "path": a.group(1),
            "title": _clean(title.group(1)) if title else None,
            "date": _clean(date.group(1)) if date else None,
            "cote": _clean(cote.group(1)) if cote else None,
            "collection": _clean(ctx.group(1)) if ctx else None,
            "thumb": BASE + thumb.group(1) if thumb else thumb_url(a.group(3)),
        })
    return total, items


def iter_all(q: str, per_page: int = 80, max_items: int | None = None,
             images_only: bool = True, typology: str | None = None,
             pause: float = 0.6):
    """Générateur paginé sur tous les résultats d'une requête."""
    import time

    page = 1
    seen = 0
    while True:
        total, items = search(q, page=page, per_page=per_page,
                              images_only=images_only, typology=typology)
        if not items:
            break
        for it in items:
            yield it
            seen += 1
            if max_items and seen >= max_items:
                return
        if page * per_page >= total:
            break
        page += 1
        time.sleep(pause)


def get_item(ark: str, uuid: str, timeout: int = 30) -> dict:
    """Métadonnées d'un item via l'API JSON /visualizer/api (par document)."""
    r = requests.get(f"{BASE}/visualizer/api",
                     headers={**HEADERS, "Accept": "application/json"},
                     params={"arkName": ark, "uuid": uuid}, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    med = j["media"][0]
    rec = med.get("record", {})

    def f1(k):
        v = rec.get(k)
        return v[0] if isinstance(v, list) and v else v

    b = (rec.get("period") or {}).get("boundaries") or [None, None]
    loc = med.get("location", {})
    return {
        "ark": ark,
        "uuid": uuid,
        "title": f1("title"),
        "referenceCode": f1("referenceCode"),
        "description": rec.get("description"),
        "date_from": b[0] if len(b) > 0 else None,
        "date_to": b[1] if len(b) > 1 else None,
        "keywords": rec.get("locationKeywords") or [],
        "image": loc.get("original") or image_url(uuid),
        "thumb": loc.get("thumb") or thumb_url(uuid),
        "iiif": loc.get("iiif"),  # toujours None : IIIF désactivé
        "record_url": rec.get("url") or f"{BASE}/ark:/14707/{ark}",
        "license_text": ((j.get("app", {}).get("licenses", {})
                          .get("visualizer", {}) or {}).get("text")),
    }


def to_document(it: dict, meta: dict | None = None) -> dict:
    """Mappe (résultat de recherche [+ méta API]) vers un doc mnemosyne normalisé.

    Hotlink seulement : aucune copie. `record_url` renvoie toujours à la notice.
    """
    m = meta or {}
    title = m.get("title") or it.get("title")
    return {
        "source": "la_contemporaine_argonnaute",
        "id": it.get("uuid"),
        "title": title,
        "date": it.get("date"),
        "date_from": m.get("date_from"),
        "date_to": m.get("date_to"),
        "reference_code": it.get("cote") or m.get("referenceCode"),
        "collection": it.get("collection"),
        "description": m.get("description"),
        "keywords": m.get("keywords") or [],
        "image_url": m.get("image") or image_url(it["uuid"]),
        "thumbnail_url": m.get("thumb") or it.get("thumb") or thumb_url(it["uuid"]),
        "license": LICENSE_SUMMARY,
        "record_url": m.get("record_url") or f"{BASE}/ark:/14707/{it.get('ark')}",
        "iiif": None,
        "is_hotlink": True,
    }
