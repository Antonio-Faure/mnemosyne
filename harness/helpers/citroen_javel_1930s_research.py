"""NOTE DE RECHERCHE — source `citroen_heritage` vs. phrase yt_01grGKLcVOc_74
(Citroën / usine du quai de Javel / restructuration des années 1930).

Agent navigateur (Archivist), tâche #558. Ce module est une NOTE versionnée
(données/URLs vérifiées en direct). Il ne modifie rien, ne copie/héberge aucune
image. Il documente POURQUOI la source « entreprise » proposée par le résolveur
adversarial n'est PAS exploitable pour cette phrase.

BESOIN DU RÉSOLVEUR
-------------------
Phrase « le plan de sauvetage est un plan de restructuration » : restructuration
Michelin de Citroën (1935), grandes grèves de 1935, licenciements (7 000 ouvriers
sur 25 000). Le résolveur veut une image NUMÉRISÉE de l'ÉVÉNEMENT 1934-1937
(usine Javel / grèves / restructuration). Périmètre actuel jugé insuffisant :
photo d'usine Javel 1928 déjà prise, « obus 1915 » anachroniques.

1. OÙ EST LE CATALOGUE (re-vérifié en direct, tâche #558)
--------------------------------------------------------
• https://www.laventurepeugeotcitroends.fr  -> 301 -> https://laventure-association.com
  (association parapluie L'Aventure Peugeot Citroën DS).
• Le lien officiel « Rechercher une archive » pointe vers
  https://www.archives-laventurepeugeotcitroends.com/fr/recherche/recherche-principale
  -> redirige vers https://www.archives-terreblanche.fr/fr/recherche/... -> 404
  (lien périmé : le préfixe /fr/ n'existe pas sur Terre Blanche).
• Le vrai catalogue : https://www.archives-terreblanche.fr (Centre d'Archives
  de Terre Blanche, Hérimoncourt — Fonds de dotation Peugeot).

2. ACCÈS PROGRAMMATIQUE : INEXISTANT (re-vérifié)
-------------------------------------------------
Tous 404 text/html sur https://www.archives-terreblanche.fr :
  /api, /api/, /graphql, /sitemap.xml, /robots.txt, /iiif, /manifest, /oai,
  /.well-known/iiif, /search, /swagger, /api/doc, /rest, /collection,
  /fr/recherche/recherche-principale  -> 404.
Aucune négociation JSON. Seule surface = HTML rendu serveur + JPEG directs.
  Recherche : GET /recherche?search[search]=<q>&search[groupTypeElement]=1&page=<N>
  (groupTypeElement=1 = iconographique ; dateDebut ISO optionnel sur date de début).

3. COUVERTURE 1934-1937 « Javel / restructuration » : NULLE (numérisée)
-----------------------------------------------------------------------
Scan iconographique (groupe 1) :
• « Javel » (~20+ items, périodes 1915-1977). Items années 1930 :
    - 142763, 142772 : « Hall de l'usine Citroën quai de Javel, banquet
      d'inauguration » 08/10/1933, place « Usine de Javel »  -> NON numérisés.
    - 142770 (1915), 142816 (1919)                            -> NON numérisés.
    - 96611 : « L'usine de Javel en 1934 » — Période 01/03/1946-31/03/1946
      (document de 1946 montrant l'usine de 1934)             -> NON numérisé.
    - 60344 « Quai d'embarquement des voitures » 1930 (numérisé) = PEUGEOT
      (« 2. Peugeot / Automobiles Peugeot »), pas Citroën -> hors sujet.
• Items Citroën/Javel NUMÉRISÉS réellement présents : 96272 (« Réfectoire de
  l'usine de Javel », 1941) et 116190 (exposition, 1977) -> HORS fenêtre 1934-37.
• Termes de l'événement, 1930s (0 pertinent numérisé) :
    grève(2, 0 en 30s), grèves(3, 0), manifestation(20, 0), occupation usine(20, 0),
    front populaire(5, 0), Michelin(20, 0), licenciements(0),
    « André Citroën »(20 ; 2 en 30s mais hors sujet : 53239 portrait football
    1934-35, 58287 salle des fêtes 1931).
• NB « Ouvriers assemblant un moteur » 1930-1939 (11024/11027, numérisés) :
    société = « 4. Panhard / Panhard et Levassor » -> PAS Citroën.
=> AUCUNE image numérisée 1934-1937 de l'usine Javel en restructuration, des
   grèves de 1935 ni des licenciements. La source ne peut PAS remplir la phrase.

4. DROITS / CONSENTEMENT (bloquant pour un connecteur non surveillé)
--------------------------------------------------------------------
• /mentions-legales : photos/maquettes/marques protégées ; « toute reproduction,
  représentation, utilisation … [est] interdite » ; copie du site interdite.
  Tous droits réservés, AUCUNE licence libre (cf. terre_blanche_archives.py §RIGHTS).
• Règle du dépôt : un connecteur « html/scrape » est soumis au consentement
  (extra.scraping_consent). E-mail d'autorisation envoyé le 2026-11-25 à
  archives-avpcd@laventureassociation.com ; aucun rebond, aucune réponse au
  2026-11-26 => STATUT EN ATTENTE. Ne PAS ajouter de connecteur « live » avant un « oui ».

5. ALTERNATIVES VÉRIFIÉES (pour mémoire, aucune ne remplit la phrase)
--------------------------------------------------------------------
• La Contemporaine / L'Argonnaute (PUBLIC, Culture Libre, API JSON par doc
  /visualizer/api + images hotlink /images/*.jpg, robots autorise) : possède la
  série « Paris. Usine Citroën. Quai de Javel » MAIS datée ~1915 (Albums Valois,
  usine d'obus PGM) = précisément les « obus 1915 anachroniques » DÉJÀ au
  périmètre. Recherches « Citroën 1935/1936 », « usine Citroën 1935 » => 0. Donc
  n'apporte AUCUNE image 1930s. (cf. la_contemporaine.py)
• Gallica (BnF) SRU : HTTP 403 au UA robot descriptif ; NON contourné (règle
  anti-bot) et déjà source de périmètre -> pas une piste nouvelle.

VERDICT
-------
`citroen_heritage` (Terre Blanche) n'est PAS viable pour la phrase #74, pour DEUX
raisons indépendantes : (1) droits restrictifs + pas de consentement -> ajout
d'un connecteur HTML interdit par la règle ; (2) couverture numérisée 1934-1937
Javel/restructuration = zéro -> la source ne résoudrait pas la phrase même si elle
était ajoutée. Recommandation : NE PAS ajouter ; consigner la phrase #74 comme
« lacune de couverture » connue (aucune image numérisée publique de l'événement
trouvée). La source pourra être (re)considérée plus tard pour ce qu'elle couvre
vraiment (ex. série promo Rosalie 1928-1933, phrase #72) UNIQUEMENT après un
« oui » explicite de l'institution.

Fonction : scan() (lecture seule) reproduit le balayage de couverture et annote
la société de chaque item « Javel » des années 1930 (pour repérer les faux
positifs type Peugeot/Panhard).
"""
from __future__ import annotations

import re

import citroen_heritage as ch  # helper voisin (lecture seule)

# Termes de l'événement « restructuration 1930s » à sonder.
EVENT_QUERIES = [
    "grève", "grèves", "manifestation", "occupation usine", "front populaire",
    "Michelin", "licenciements", "André Citroën",
]
JAVEL_QUERIES = ["Javel", "quai de Javel", "usine Javel"]


def _in_1930s(period: str) -> bool:
    ys = re.findall(r"(19\d{2})", period or "")
    return any(1930 <= int(y) <= 1939 for y in ys)


def scan(group_type: int = 1, annotate: bool = True) -> dict:
    """Balayage lecture seule ; renvoie un résumé factuel des items 1930s."""
    out = {"javel_items_1930s": [], "event_hits_1930s": {}}
    seen = set()
    for q in JAVEL_QUERIES:
        res = ch.search(q, group_type=group_type, max_pages=1)
        for it in (res if isinstance(res, list) else []):
            if _in_1930s(it.get("period")) and it["id"] not in seen:
                seen.add(it["id"])
                soc = None
                if annotate:
                    try:
                        soc = ch.fetch_item(it["id"]).get("society")
                    except Exception:  # noqa: BLE001
                        soc = None
                out["javel_items_1930s"].append({
                    "id": it["id"], "period": it.get("period"),
                    "digitized": bool(it.get("digitized")),
                    "society": soc, "description": it.get("description"),
                })
    for q in EVENT_QUERIES:
        res = ch.search(q, group_type=group_type, max_pages=1)
        hits = [it["id"] for it in (res if isinstance(res, list) else [])
                if _in_1930s(it.get("period")) and it.get("digitized")]
        out["event_hits_1930s"][q] = hits
    return out


if __name__ == "__main__":
    import json
    data = scan()
    print(json.dumps(data, ensure_ascii=False, indent=1))
    print(
        "\nAttendu : côté 'Javel' 1930s, les seuls items Citroën (142763/142772, "
        "banquet 1933 ; 96611 'usine de Javel en 1934', doc. de 1946) sont NON "
        "numérisés ; 60344 (numérisé) est Peugeot. event_hits vides ou hors sujet "
        "=> couverture numérisée 1934-37 de l'événement = NULLE."
    )
