r"""La Contemporaine (ex-BDIC), Nanterre — fonds photographique des ANNÉES 1930.

Complément 1930s du helper `la_contemporaine.py` (qui couvre 1914-1918).
Écrit par l'agent navigateur (Archivist) pour la tâche #554.

Institution : La Contemporaine, 184 cours Nicole Dreyfus, 92001 Nanterre.
Bibliothèque numérique : L'Argonnaute — https://argonnaute.parisnanterre.fr
Plateforme maison (« Nakalona »), ARK NAAN = 14707. ~200 000 documents
numérisés (imprimés, archives, dessins, photographies, affiches, objets).

Ce module est une RÉFÉRENCE read-only que le codeur utilise pour bâtir /
étendre `config/sources/la_contemporaine.yaml` + connecteur. Il n'écrit RIEN
sur le distant, ne copie/réhéberge aucune image : il renvoie des URLs
publiques servies par l'institution (hotlink) — mnemosyne n'héberge pas.

=====================================================================
CE QUI COUVRE LES ANNÉES 1930 (vérifié en live, tâche #554)
=====================================================================
Le fonds photographique interguerres est l'inventaire
    « France, entre-deux guerres 1918-1939. Photographies »
(cotes série PH C4 / PH C6 ; « Fonds issu d'agences et de studios
photographiques divers »). C'est de la PHOTOGRAPHIE DE PRESSE : légendes
d'événements politiques et sociaux à Paris / Île-de-France.

Couverture vérifiée (requêtes dans CE fonds, facet_media=image) :
    grève ........... 77      manifestation ... 77      1936 ......... 25
Sujets réels : grèves des transports (janvier 1938), grèves des taxis,
batellerie / bateliers de Conflans (barrages sur la Seine), marcheurs de la
faim du Nord arrivés à Paris (1933), Front Populaire (1936-1938), élections
législatives 1936, congrès PPF/socialiste, Croix de Feu, Armistice, etc.
=> Parfait pour « grèves des années 1930 en Île-de-France ».

=== LIMITE IMPORTANTE (à ne pas masquer dans la doc source) ===
Recherche de l'USINE / des OUVRIERS / de CITROËN en 1930s : ABSENTE.
    Dans le fonds interguerres : Citroën=0, Renault=0, Billancourt=0,
    Javel=0, usine=0, ouvrier(s)=0, atelier=0, métallurgistes=0
    (les métadonnées sont des légendes de presse, pas d'indexation usine).
Les photos « Usines Citroën », « ouvriers/ouvrières d'usine », « chantiers
Niclausse » de La Contemporaine sont de la PREMIÈRE GUERRE MONDIALE
(inventaire « Albums Valois », cotes VAL xxx/xxx, 1915-1918) — PAS 1930s.
Conséquence : l'hypothèse « ouvriers de Citroën 1930s » n'est PAS couverte.
La source RESTE pertinente pour le volet « grèves / mouvements sociaux
1930s en Île-de-France » (dockers, bateliers, taxis, manifestations).

=====================================================================
CHEMIN D'ACCÈS (vérifié) — identique au helper PGM, + une API JSON
=====================================================================
1) RECHERCHE (découverte) — HTML rendu côté serveur, GET, sans anti-bot
   (pas de Cloudflare/Anubis ; `requests`/urllib + UA descriptif -> 200 avec
   résultats). Il n'y a PAS d'API de recherche JSON (/search/api,
   /api/search, ?format=json -> 404).
       https://argonnaute.parisnanterre.fr/search/results
           ?q=<requête URL-encodée>
           &scope=all
           &facet_media=image          # images seulement (recommandé)
           [&facet_titleProper=France%2C%20entre-deux%20guerres%201918-1939.%20Photographies]
           [&page=<N>]                 # pagination 1-based
           [&resultsPerPage=20|40|80]  # 20 par défaut
   - SÉMANTIQUE **AND** : TOUS les mots requis -> une longue phrase renvoie
     PEU/0. => Toujours envoyer des requêtes COURTES (2–3 mots-clés) :
     « grève 1936 », « grève transports », « manifestation Front populaire »,
     « marcheurs de la faim », « batellerie ». NE PAS envoyer la phrase
     entière de l'utilisateur telle quelle (résultat garanti = 0).
   - Total sur la page : le texte « N résultats » (regex nombre + « résultats »).
   - Pagination : texte « Page suivante : 1/4 » (regex « <courante>/<total> »).
   - Vide : présence de « Aucun résultat ».

2) MÉTADONNÉES PAR DOCUMENT — API JSON interne (découverte tâche #554).
   Les 2 paramètres sont REQUIS (sinon 400) :
       https://argonnaute.parisnanterre.fr/visualizer/api?arkName=<ARK>&uuid=<UUID>
   Champs utiles (dans `media[0]`) :
       record.title            (liste)  -> titre
       record.referenceCode    (liste)  -> cote archivistique (ex. PH C4 03 (16))
       record.description      (liste)  -> légende de presse
       record.period.boundaries(liste)  -> [dateMin, dateMax] ex. 1936-01-01/1936-12-31
       record.locationKeywords (liste)  -> lieux (ex. Paris (France))
       location.original       (str)    -> image pleine /images/<UUID>.jpg (HEAD 200)
       location.thumb          (str)    -> vignette /images/<UUID>_thumbnail.jpg
       iiif                    (None)   -> TOUJOURS null
       app.toolbar.isIIIFEnabled (bool) -> TOUJOURS False
   => IIIF ABSENT/DÉSACTIVÉ (/iiif/manifest -> 404). Ne pas tenter IIIF.
   => OAI-PMH existe (/oai-pmh?verb=Identify -> 200) MAIS robots.txt le
      DISALLOW + métadonnée pauvre : NE PAS l'utiliser.

3) ROBOTS.TXT — `User-agent: * Disallow: /private/ /oai-pmh /user/`.
   Tout le reste est autorisé. Bloque nommément GPTBot, ChatGPT-User,
   OAI-SearchBot, Applebot, Amazonbot, meta-externalagent(s), Ahrefs*,
   Semrush*, PetalBot, RyteBot, SiteAuditBot, SplitSignalBot.
   Un UA descriptif `mnemosyne-research-bot/1.0` passe.

=====================================================================
DROITS (vérifié — page /page/licences-d-utilisation)
=====================================================================
La Contemporaine est labellisée « Culture Libre » (argent) par Wikimédia
France (16/06/2025).
  - Documents en DOMAINE PUBLIC (dont la presse : 70 ans après publication,
    => photos de presse d'avant ~1955 en principe PD) :
        -> Licence Ouverte / Etalab (libre, gratuit, commercial, attribution).
  - Documents PROTÉGÉS (« Tous droits réservés » / accord préalable) :
        -> afficher métadonnées + lien SEULEMENT.
Mnemosyne, par principe : affiche titre/date/lieu/droits + lien, hotlink de
l'image, ne revendique AUCUNE réutilisation, n'héberge/copie/redistribue rien.

=====================================================================
EXEMPLES 1930s (ark/uuid vérifiés via visualizer/api)
=====================================================================
Voir EXAMPLE_ITEMS ci-dessous. Tous dans le fonds interguerres (PH C4/PH C6).
"""

import json
import re
import urllib.parse
import urllib.request

BASE = "https://argonnaute.parisnanterre.fr"
SEARCH_ENDPOINT = BASE + "/search/results"
ITEM_API = BASE + "/visualizer/api"
ARK_NAAN = "14707"
DEFAULT_UA = "mnemosyne-research-bot/1.0 (+https://github.com/Antonio-Faure/mnemosyne)"

# Inventaire exact du fonds photographique entre-deux-guerres.
INTERWAR_FONDS = "France, entre-deux guerres 1918-1939. Photographies"

# Requêtes courtes (AND) qui renvoient des résultats dans le fonds interguerres.
# NE PAS envoyer de phrases longues : la sémantique est AND -> 0 résultat.
EXAMPLE_QUERIES = [
    "grève 1936",
    "grève transports",
    "manifestation Front populaire",
    "marcheurs de la faim",
    "batellerie",
]

# Exemples vérifiés : 6 photos 1930s (grèves / mouvements sociaux IdF).
EXAMPLE_ITEMS = [
    {
        "title": "Grève des transports, janvier 1938",
        "date": "1938",
        "location": "France",
        "reference_code": "PH C4 03 (23)",
        "ark": "qt4hcw0f9bxk",
        "uuid": "200278be-a725-4b71-b677-e64d1ca00f00",
    },
    {
        "title": "Manifestation Front Populaire à la Nation",
        "date": "1938",
        "location": "Paris",
        "reference_code": "PH C4 03 (02)",
        "ark": "6vhzx0sg4r9c",
        "uuid": "e5c8c654-ce04-4403-befd-c812c38a9d99",
    },
    {
        "title": "Marcheurs de la faim arrivés à Paris",
        "date": "1933",
        "location": "Paris",
        "reference_code": "PH C4 06 (11)",
        "ark": "m8sk62047fqg",
        "uuid": "a89eb33f-07ab-4f47-b858-96a3d96af8d6",
    },
    {
        "title": "Grève des Bateliers à Conflans",
        "date": "1936",
        "location": "Paris",
        "reference_code": "PH C4 03 (16)",
        "ark": "4l6m9krbngfv",
        "uuid": "36b0a7b5-c8a7-4b1d-9ae4-6a685f4eac3d",
    },
    {
        "title": "Grève de la Batellerie terminée",
        "date": "1936",
        "location": "Paris",
        "reference_code": "PH C4 03 (15)",
        "ark": "f28sr7k1vjt5",
        "uuid": "aa587925-2bad-4ab1-bd33-2ff33831037d",
    },
    {
        "title": "Grève des taxis",
        "date": "1933",
        "location": "Paris",
        "reference_code": "PH C4 06 (05)",
        "ark": "1hbndgm24r75",
        "uuid": "c7102347-6987-4bae-8cf5-9e86a57d3450",
    },
]


def search_url(q, page=1, results_per_page=20, images_only=True, fonds=False):
    """Construit l'URL de recherche (découverte) d'L'Argonnaute.

    Args:
        q: requête COURTE (2-3 mots-clés ; sémantique AND).
        page: page 1-based.
        results_per_page: 20 (défaut), 40 ou 80.
        images_only: ne garder que facet_media=image.
        fonds: restreindre à l'inventaire interguerres (facet_titleProper).
    """
    params = {
        "q": q,
        "scope": "all",
        "page": str(page),
        "resultsPerPage": str(results_per_page),
    }
    if images_only:
        params["facet_media"] = "image"
    if fonds:
        params["facet_titleProper"] = INTERWAR_FONDS
    return SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def parse_search_html(html):
    """Parse la page de résultats HTML rendue côté serveur.

    Renvoie un dict :
        {
          "total": int|None,          # « N résultats »
          "page": int|None,           # « Page courante » de « 1/4 »
          "pages": int|None,          # total de pages de « 1/4 »
          "items": [ {"ark","uuid","title"} ... ],
          "empty": bool,              # « Aucun résultat » présent
        }
    """
    out = {"total": None, "page": None, "pages": None, "items": [], "empty": False}

    m = re.search(r"(\d+)\s*résultats", html)
    if m:
        out["total"] = int(m.group(1))

    m = re.search(r"Page suivante\s*:?\s*(\d+)\s*/\s*(\d+)", html)
    if not m:
        m = re.search(r"(\d+)\s*/\s*(\d+)", html)
    if m:
        out["page"] = int(m.group(1))
        out["pages"] = int(m.group(2))

    if "Aucun résultat" in html or (out["total"] == 0):
        out["empty"] = True

    # Blocs de résultat (séparés par la classe element-list).
    blocks = re.findall(r'class="element-list.*?(?=class="element-list|$)', html, re.S)
    if not blocks:
        blocks = [html]

    seen = set()
    for block in blocks:
        mk = re.search(r"/ark:/" + ARK_NAAN + r"/([0-9a-z]+)/([0-9a-f-]{36})", block)
        if not mk:
            continue
        ark, uuid = mk.group(1), mk.group(2)
        if uuid in seen:
            continue
        seen.add(uuid)
        # Titre : <h2> ... <span> ... </span> ... </h2>
        title = None
        mt = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S)
        if mt:
            span = re.search(r"<span[^>]*>(.*?)</span>", mt.group(1), re.S)
            raw = span.group(1) if span else mt.group(1)
            title = re.sub(r"<[^>]+>", "", raw).strip()
            title = re.sub(r"\s+", " ", title) or None
        out["items"].append({"ark": ark, "uuid": uuid, "title": title})

    return out


def _http_get(url, timeout=25, accept="*/*"):
    req = urllib.request.Request(
        url, headers={"User-Agent": DEFAULT_UA, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(q, page=1, results_per_page=20, images_only=True, fonds=False,
           timeout=25):
    """Recherche live : renvoie parse_search_html() enrichi de l'URL.
    Rappel : requête COURTE (AND). Lecture publique, pas d'API de recherche."""
    url = search_url(q, page=page, results_per_page=results_per_page,
                     images_only=images_only, fonds=fonds)
    html = _http_get(url, timeout=timeout).decode("utf-8", "replace")
    result = parse_search_html(html)
    result["query"] = q
    result["url"] = url
    return result


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def item_metadata(ark, uuid, timeout=25):
    """Récupère les métadonnées d'un document via l'API JSON interne.

    Renvoie un dict normalisé (champs Mnemosyne) :
        title, reference_code, description, date_start, date_end,
        location, image_url, thumb_url, iiif, is_iiif_enabled, record_url
    Aucune copie : on renvoie les URLs publiques de l'institution.
    """
    url = f"{ITEM_API}?arkName={ark}&uuid={uuid}"
    data = json.loads(_http_get(url, timeout=timeout, accept="application/json"))
    media = (data.get("media") or [{}])[0]
    rec = media.get("record", {}) or {}
    loc = media.get("location", {}) or {}
    period = (rec.get("period", {}) or {}).get("boundaries")
    date_start = date_end = None
    if isinstance(period, list) and len(period) >= 2:
        date_start, date_end = period[0], period[1]
    toolbar = ((data.get("app", {}) or {}).get("toolbar", {}) or {})
    return {
        "ark": ark,
        "uuid": uuid,
        "title": _first(rec.get("title")),
        "reference_code": rec.get("referenceCode"),
        "description": _first(rec.get("description")),
        "date_start": date_start,
        "date_end": date_end,
        "location": rec.get("locationKeywords"),
        "image_url": loc.get("original"),
        "thumb_url": loc.get("thumb"),
        "iiif": media.get("iiif"),
        "is_iiif_enabled": toolbar.get("isIIIFEnabled"),
        "record_url": f"{BASE}/ark:/{ARK_NAAN}/{ark}/{uuid}",
    }


if __name__ == "__main__":
    # Démo / smoke test (réseau requis).
    for q in EXAMPLE_QUERIES:
        r = search(q, results_per_page=20)
        print(f"[{q!r}] total={r['total']} items={len(r['items'])}")
    ex = EXAMPLE_ITEMS[3]  # Grève des Bateliers à Conflans (1936)
    print(item_metadata(ex["ark"], ex["uuid"]))
