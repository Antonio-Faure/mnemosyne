"""Dossier de recherche — source « L'Aventure Michelin / fonds patrimonial Michelin »
(source candidate `michelin_heritage`). Agent navigateur, tâche #557.

Résolveur adversarial : phrase yt_01grGKLcVOc_74
(« Le plan de sauvetage est un plan de restructuration » → reprise/restructuration
de Citroën par Michelin 1934-1937 : contrôle de Pierre Michelin, réorganisation de
l'usine du quai de Javel, licenciements).

Ce module est une NOTE DE RECHERCHE versionnée (données statiques + URLs).
Il n'exécute AUCUNE requête réseau et ne copie / n'héberge aucune image.

====================================================================
CONCLUSION (vérifié en direct le 2026-11-27)
====================================================================
Il N'EXISTE PAS de collection photographique en ligne EXPLOITABLE (ni API, ni
IIIF, ni galerie/catalogue interrogeable) chez Michelin / L'Aventure Michelin
couvrant la reprise-restructuration de Citroën par Michelin (1934-1937).
=> NE PAS construire de connecteur « live » pour `michelin_heritage`.
   Marquer la source comme « sans collection en ligne / accès programmatique
   inexistant » dans la carte des sources.

====================================================================
1. L'URL FOURNIE PAR LE RÉSOLVEUR N'EXISTE PAS (DNS NXDOMAIN)
====================================================================
   https://www.aventure-michelin.com      -> NXDOMAIN
   https://aventure-michelin.com          -> NXDOMAIN
   https://www.aventuremichelin.com       -> NXDOMAIN
   https://aventuremichelin.fr            -> NXDOMAIN
   https://laventuremichelin.com / .fr    -> NXDOMAIN (le .fr répond au DNS mais le
                                             serveur bloque / ne répond jamais : timeout)
   => la cible « api/docs » indiquée est intrinsèquement fausse.

====================================================================
2. LE VRAI SITE DU MUSÉE = https://laventure.michelin.com (site VISITEUR)
====================================================================
   Sous-domaine officiel de michelin.com, WordPress + Yoast SEO.
   • Sitemaps (sitemap_index.xml) :
       - page-sitemap.xml                     (pages visiteurs)
       - download_document(-category)-sitemap.xml (PDF pédagogiques/presse)
       - news-sitemap.xml                     (actus marketing)
       - document_tags-sitemap.xml
     => AUCUN type de contenu « collection / objet / photo / catalogue ».
   • Pages (52) : infos pratiques, visites (individuelle/groupe/scolaire),
     découverte du musée, « La Serre Michelin », actus, presse, contact,
     mentions légales, FAQ, dossiers pédagogiques. Aucune page collection/galerie.
   • API : /wp-json/wp/v2/types -> HTTP 401 Unauthorized (REST WordPress verrouillée).
          Pas d'endpoint public exploitable.
   • Contact : formulaire (dont un objet « service patrimoine ») +
               contact@laventure.michelin.com   (adresse générale du musée).
   => Site de billetterie/communication d'un musée physique, pas un catalogue numérique.

====================================================================
3. PATRIMOINE GROUPE MICHELIN = une FRISE CHRONOLOGIQUE (SPA), pas un catalogue
====================================================================
   https://www.michelin.com/groupe/histoire        (FR)
   https://www.michelin.com/en/group/heritage      (EN)
   • Pages rendues CÔTÉ CLIENT (JS/SPA) : HTML initial ≈ 0 texte utile ; données
     dans un blob JSON __NEXT_DATA__-like. ~196 images, servies via CDN
     (agngnconpm.cloudimg.io/v7/https://dgaddcosprod.blob.core.windows.net/...).
   • Un chapitre 1935 existe bel et bien : « Michelin, Citroën, and the 2CV »
     — « Michelin took the reins of French carmaker Citroën and put Pierre
     Michelin and Pierre Boulanger in charge… » (rachat + programme TPV/2CV).
     MAIS les images vues de ce chapitre = prospectus années 1950 (pneu X + 2CV)
     et « Édouard Michelin et le prototype de la 2CV Citroën 1938 » :
     ce ne sont PAS l'usine du quai de Javel, les licenciements, ni la
     réorganisation industrielle 1934-1937 recherchés par la phrase.
   • Surtout : frise marketing unique, NON interrogeable (pas de recherche,
     pas d'API, pas de IIIF, pas d'URL stable par image, pas de métadonnée par item).
   => Inutilisable comme « source d'images d'archives » au sens Mnemosyne.

====================================================================
4. SOUS-DOMAINES « archives » TESTÉS — TOUS INEXISTANTS (NXDOMAIN)
====================================================================
   patrimoine / archives / mediatheque / collection / photo(s) / image(s) /
   heritage / histoire / bibliotheque / memoire / about / press(e) .michelin.com
   media.michelin.com, newsroom.michelin.com, brand.michelin.com  -> NXDOMAIN
   collector.michelin.com                                          -> NXDOMAIN
   www.michelin.com/en/our-group/heritage, /fr/patrimoine          -> 404
   www.michelin.com/groupe/histoire/patrimoine                     -> 404
   www.michelin.com/fr/espace-presse                               -> 404
   => Aucune banque d'images / photothèque / médiathèque patrimoniale en ligne.

====================================================================
5. LA « COLLECTION HISTORIQUE MICHELIN » EST PHYSIQUE, PAS EN LIGNE
====================================================================
   Source : RVA (8/12/2022), Stéphane Nicolas, responsable de la collection et du
   patrimoine du groupe Michelin — « cette collection historique n'est pas
   confidentielle, elle a vocation à être partagée et connue ».
   Il s'agit d'objets physiques (fiacre, pneus d'origine, cartes, guides, affiches,
   véhicules) répartis en réserves. Aucune mention d'un catalogue numérique API/IIIF.

====================================================================
6. OÙ SONT VRAIMENT LES PHOTOS DE L'ÉVÉNEMENT (sources SÉPARÉES)
====================================================================
   Les photos de l'usine Citroën (Javel) et de la réorganisation 1934-1937 ont été
   prises par des AGENCES DE PRESSE, pas par Michelin :
   • BnF / Gallica — fonds Agence Meurisse / Mondial / Rol (IIIF) : candidat
     naturel. (Note : un probe SRU avec UA bot générique a renvoyé HTTP 403 →
     à traiter comme une VRAIE source distincte, avec le protocole IIIF/SRU de
     Gallica, et pas via http_get « bot ». NE PAS contourner un 403.)
   • L'Aventure Peugeot Citroën DS — Centre d'archives de Terre Blanche
     (voir tâche #553 / helper `citroen_heritage.py`) : HTML scrape, pas d'API,
     autorisation obligatoire, réponse en attente.

====================================================================
7. RECOMMANDATION
====================================================================
   `michelin_heritage` : NE PAS ajouter de connecteur. Statut source =
   « pas de collection en ligne, pas d'accès programmatique ». La couverture
   photographique de la phrase, si elle doit venir d'un « fonds patrimonial »,
   relève de Gallica (agences de presse, IIIF) ou de Terre Blanche (#553),
   pas du patrimoine Michelin. Un e-mail au « service patrimoine » du musée
   ne donnerait accès à rien de programmatique tant qu'aucune collection
   numérique n'existe (et il faudrait une validation opérateur pour l'envoyer).
"""

from __future__ import annotations

VERIFIED_ON = "2026-11-27"
TASK = "#557"
RESOLVER_PHRASE = "yt_01grGKLcVOc_74"

# L'URL fournie par le résolveur n'existe pas (DNS NXDOMAIN).
PROVIDED_URL_DEAD = [
    "https://www.aventure-michelin.com",
    "https://aventure-michelin.com",
    "https://www.aventuremichelin.com",
    "https://aventuremichelin.fr",
    "https://laventuremichelin.com",
    "https://laventuremichelin.fr",
]

# Le vrai site du musée : site VISITEUR, aucune collection numérique.
MUSEUM_SITE = "https://laventure.michelin.com"
MUSEUM_SITEMAPS = [
    "https://laventure.michelin.com/page-sitemap.xml",
    "https://laventure.michelin.com/download_document-sitemap.xml",
    "https://laventure.michelin.com/news-sitemap.xml",
    "https://laventure.michelin.com/download_document_category-sitemap.xml",
    "https://laventure.michelin.com/document_tags-sitemap.xml",
]
MUSEUM_WP_REST_TYPES = "https://laventure.michelin.com/wp-json/wp/v2/types"  # -> 401
MUSEUM_CONTACT = "contact@laventure.michelin.com"  # adresse générale (non utilisée)

# Frise chronologique du groupe (SPA marketing, pas un catalogue).
HERITAGE_TIMELINE = {
    "fr": "https://www.michelin.com/groupe/histoire",
    "en": "https://www.michelin.com/en/group/heritage",
    "has_1935_chapter": "Michelin, Citroën, and the 2CV",
    "chapter_images": [
        # prospectus années 1950 (pneu X + 2CV) et prototype 2CV 1938 — PAS Javel
        "1935-4-prospectus-b-to-b-le-pneu-michelin-x-et-la-2cv-1950s",
        "1935-2-edouard-michelin-et-le-prototype-de-la-2cv-citroen-1938",
    ],
    "queryable": False,
    "has_api": False,
    "has_iiif": False,
    "per_item_urls": False,
}

# Où sont (plus probablement) les photos réelles de l'événement.
EVENT_PHOTO_CANDIDATES = [
    {"source": "gallica_bnf", "why": "agences de presse Meurisse/Mondial/Rol, IIIF",
     "note": "source distincte ; probe SRU UA-bot = 403 (ne pas contourner)"},
    {"source": "citroen_heritage", "why": "Centre d'archives de Terre Blanche (#553)",
     "note": "HTML scrape, autorisation obligatoire, réponse en attente"},
]

VERDICT = (
    "AUCUNE collection photographique en ligne exploitable (API/IIIF/galerie "
    "interrogeable) chez Michelin / L'Aventure Michelin couvrant la reprise-"
    "restructuration de Citroën 1934-1937. Ne pas ajouter le connecteur."
)


def summary() -> dict:
    """Résumé structuré pour le codeur / la carte des sources (sans réseau)."""
    return {
        "source": "michelin_heritage",
        "task": TASK,
        "resolver_phrase": RESOLVER_PHRASE,
        "verified_on": VERIFIED_ON,
        "provided_url_exists": False,
        "addable": False,
        "museum_site": MUSEUM_SITE,
        "museum_has_collection": False,
        "museum_wp_rest": "401 Unauthorized",
        "heritage_timeline": HERITAGE_TIMELINE,
        "recommended_status": "no_online_collection_no_programmatic_access",
        "verdict": VERDICT,
        "event_photo_candidates": EVENT_PHOTO_CANDIDATES,
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
