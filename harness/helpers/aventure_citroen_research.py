"""Dossier de recherche — source « L'Aventure Citroën / Citroën Heritage »
(patrimoine photographique). Agent navigateur, tâche #553.

Résolveur adversarial : phrase yt_01grGKLcVOc_72
(« ouvriers / usines Citroën, quai de Javel, années 1930 »).

Ce module est une NOTE DE RECHERCHE versionnée (données statiques + URLs).
Il n'exécute AUCUNE requête réseau et ne copie / n'héberge aucune image.

--------------------------------------------------------------------
1. OÙ SONT VRAIMENT LES PHOTOS
--------------------------------------------------------------------
Les photographies d'usine Citroën (Javel, chaînes, ateliers, ouvriers) ne sont
PAS sur un site Citroën dédié. Elles sont conservées par le Centre d'archives de
Terre Blanche, qui dépend de l'association « L'Aventure » (Peugeot + Citroën +
DS). C'est la vraie cible du « patrimoine photographique Citroën Heritage ».

2. URLS / ORGANISMES (vérifiés 2026-11-26)
--------------------------------------------------------------------
   Association L'Aventure :
       https://laventure-association.com
   Conservatoire Citroën & DS (véhicules) :
       https://laventure-association.com/laventure-citroen/
       le-conservatoire-de-laventure-citroen-ds/
   Centre d'archives de Terre Blanche :
       https://www.archives-terreblanche.fr
   Ancien domaine :
       archives-laventurepeugeotcitroends.com (redirige vers Terre Blanche)
   Hébergeur des fonds :
       Fonds de dotation Peugeot pour la mémoire de l'histoire industrielle
       (utilité publique 2024), 1 rue du Stade, 25310 Hérimoncourt.
   Contact archives : archives-avpcd@laventureassociation.com
   Contact général  : contact-avpcd@laventureassociation.com

3. ACCÈS PROGRAMMATIQUE : INEXISTANT (vérifié 2026-11-26)
--------------------------------------------------------------------
   Pas d'API, pas de IIIF, pas d'OAI-PMH, pas de JSON, pas de sitemap,
   pas de robots.txt (tous en 404). Stack Symfony + Varnish, HTML rendu serveur.
   Seul accès = scraping HTML + fichiers JPEG.

4. RECHERCHE EN LIGNE (HTML, formulaire GET)
--------------------------------------------------------------------
   GET https://www.archives-terreblanche.fr/recherche
       ?search[search]=<mot>
       &search[groupTypeElement]=<1..5>   (1 = iconographiques / photos)
       &search[societe]=<libellé exact>
       &search[dateDebut][from]=.. &search[dateDebut][to]=..
       &search[dateFin][from]=..   &search[dateFin][to]=..

5. FICHE / MÉTADONNÉES
--------------------------------------------------------------------
   https://www.archives-terreblanche.fr/archive/{id}
   Champs : Description, Période, Type de document, Thème, Société, Lieux,
            Référence du document (cote stable, ex DOS2017FIG-01128).
   Images : /upload/documents/{n}-{hash}.jpg (~1280 px, plusieurs par fiche).
   ATTENTION : nombreuses fiches « Cette archive n'a pas encore été numérisée ! »
   → métadonnée seule, pas d'image en ligne.

6. RÉUTILISATION
--------------------------------------------------------------------
   Tout est sous droits (droits d'auteur + marques), reproduction interdite sans
   autorisation, AUCUNE licence libre ; boutique de reproductions payantes.
   => accès / lecture programmatique = AUTORISATION OBLIGATOIRE.

7. PRISE DE CONTACT (Terre Blanche)
--------------------------------------------------------------------
   E-mail déjà envoyé le 2026-11-25 22:45
   à archives-avpcd@laventureassociation.com
   (question d'accès programmatique, exemples Citroën usine). Aucun rebond,
   aucune réponse au 2026-11-26.
   => STATUT : EN ATTENTE. Ne PAS ajouter la source ni committer de connecteur
      « live » tant que la réponse n'est pas « oui ».

8. ALTERNATIVE « PUBLIQUE » : La Contemporaine / L'Argonnaute
--------------------------------------------------------------------
   La Contemporaine (bibliothèque publique, Univ. Paris Nanterre) — via sa
   bibliothèque numérique L'Argonnaute — possède une série numérisée
   « Paris. Usine Citroën. Quai de Javel » avec ouvriers
   (ex. ark:/14707/1qxwblpsgtjh, « L'infirmerie. Infirmière pansant un blessé »).
   MAIS ce n'est PAS librement moissonnable (vérifié 2026-11-26) :
   - robots.txt bloque les crawlers IA (GPTBot, OAI-SearchBot, ChatGPT-User…)
     et interdit /oai-pmh ; un endpoint OAI-PMH existe donc mais est Disallow ;
   - CGU : simple licence de navigation, aucun droit d'exploitation
     commerciale ; reproduction et « extraction substantielle » = accord
     préalable et écrit obligatoire.
   => Comme Terre Blanche : autorisation écrite nécessaire, pas d'ajout auto.
      Contact : contact@lacontemporaine.fr (mentions légales).

9. STATUT GLOBAL (à la clôture de la recherche)
--------------------------------------------------------------------
   Source demandée (Terre Blanche) identifiée et localisée, MAIS aucun accès
   programmatique public + tout sous droits → ajout au catalogue BLOQUÉ
   jusqu'à autorisation écrite. Prise de contact en attente. L'alternative
   « publique » (L'Argonnaute) est elle aussi soumise à autorisation.
   Hand-off au codeur via la messagerie de tâche (descripteur NON committé).
"""

# --- Identifiants techniques de la source ---------------------------------

BASE_URL = "https://www.archives-terreblanche.fr"
SEARCH_PATH = "/recherche"
ITEM_URL_TEMPLATE = BASE_URL + "/archive/{id}"

# Paramètre search[groupTypeElement] : 1 = documents iconographiques/photos.
# Les valeurs 2..5 existent mais n'ont pas été cataloguées ici.
GROUP_TYPES = {
    1: "Documents iconographiques / photographies",
}

# Libellés exacts du filtre Société pour l'historique Citroën.
SOCIETE_CITROEN_ANDRE_SA = "3. Citroën / André Citroën SA"
SOCIETE_CITROEN_AUTOMOBILES = "3. Citroën / Automobiles Citroën"

# Champs affichés sur une fiche d'archive.
METADATA_FIELDS = [
    "Description",
    "Période",
    "Type de document",
    "Thème",
    "Société",
    "Lieux",
    "Référence du document",
]

# Volumétrie constatée via la recherche filtrée (2026-11-26).
VOLUMETRIE = {
    "documents_iconographiques_andre_citroen_sa": 3048,
    "note": "approximatif, dépend des facettes du moteur de recherche",
}

# Exemples NUMÉRISÉS vérifiés (image réellement servie ~1280 px).
EXAMPLE_ITEMS = [
    {
        "id": "96272",
        "titre": "Réfectoire de l'usine de Javel",
        "periode": "1941",
        "cote": "DOS2017FIG-00446",
        "lieu": "Javel (Paris)",
        "images": 3,
        "taille_px": "1280x846",
    },
    {
        "id": "96235",
        "titre": "Chaîne de châssis",
        "periode": "09/1940",
        "cote": "DOS2017FIG-00392",
        "taille_px": "1280x939",
    },
    {
        "id": "97455",
        "titre": "Usine.- La chaîne",
        "periode": "06/1951",
        "cote": "DOS2017FIG-01128",
        "taille_px": "1280x924",
    },
    {
        "id": "96653",
        "titre": "Usine de Slough",
        "periode": "1947",
        "cote": "DOS2017FIG-00585",
    },
    {
        "id": "96655",
        "titre": "Usine d'Amsterdam",
        "periode": "1947",
        "cote": "DOS2017FIG-00587",
    },
    {
        "id": "97422",
        "titre": "Vue de la chaîne de B14",
        "periode": "02/1951",
        "cote": "DOS2017FIG-01085",
        "taille_px": "678x960",
    },
    {
        "id": "99856",
        "titre": "Chaîne de montage DS",
        "periode": "1955",
        "cote": "DOS2017FIG-05575",
        "images": 4,
    },
]

# Fiches Javel années 1930 présentes en MÉTADONNÉE mais NON numérisées.
NOT_DIGITIZED_JAVEL_1930s = [
    {"id": "96611", "titre": "L'usine de Javel en 1934", "periode": "1934"},
    {
        "id": "142770",
        "titre": "Usine Citroën Quai de Javel, vue des terrains avant construction",
        "periode": "1915",
    },
    {"id": "142763", "titre": "Banquet d'inauguration", "periode": "08/10/1933"},
]

CONDITIONS_REUTILISATION = (
    "Sous droits (droits d'auteur + marques). Reproduction interdite sans "
    "autorisation écrite. Aucune licence libre. Boutique de reproductions "
    "payantes. => accès/lecture programmatique = autorisation obligatoire. "
    "Ne jamais copier ni réhéberger les images ; on affiche métadonnées + lien."
)

PRISE_DE_CONTACT = {
    "destinataire": "archives-avpcd@laventureassociation.com",
    "destinataire_alt": "contact-avpcd@laventureassociation.com",
    "envoye_le": "2026-11-25T22:45",
    "objet": (
        "Mnemosyne — ajouter les images d'archives du Centre d'Archives de "
        "Terre Blanche (L'Aventure Peugeot Citroën DS)"
    ),
    "statut": "EN ATTENTE (aucun rebond, aucune réponse au 2026-11-26)",
}

# Note sur le connecteur : à ne PAS committer en mode « live » avant le « oui ».
CONNECTEUR_RECOMMANDE = {
    "mode": "HTML (scraping) — aucune API/IIIF/OAI disponible",
    "recherche": (
        BASE_URL + SEARCH_PATH + "?search[search]={q}"
        "&search[societe]=" + SOCIETE_CITROEN_ANDRE_SA
    ),
    "fiche": ITEM_URL_TEMPLATE,
    "garde_fou": "ne PAS committer live tant que l'autorisation n'est pas reçue",
    "images": "afficher métadonnées + lien ; ne pas copier le JPEG",
}

# Source « publique » distincte — PAS librement moissonnable (voir section 8).
ALTERNATIVE_PUBLIQUE = {
    "nom": "La Contemporaine / L'Argonnaute",
    "organisation": "Bibliothèque publique, Université Paris Nanterre",
    "url": "https://argonnaute.parisnanterre.fr",
    "cgu_url": "https://argonnaute.parisnanterre.fr/page/"
               "conditions-generales-d-utilisation",
    "contact": "contact@lacontemporaine.fr",
    "adresse": "184 cours Nicole Dreyfus, 92001 Nanterre",
    "serie": "Paris. Usine Citroën. Quai de Javel (ouvriers)",
    "exemple_ark": "ark:/14707/1qxwblpsgtjh",
    "exemple_titre": "L'infirmerie. Infirmière pansant un ouvrier blessé",
    "oai_pmh": "endpoint existe mais robots.txt Disallow /oai-pmh",
    "robots": "bloque GPTBot/OAI-SearchBot/ChatGPT-User ; IA interdite",
    "cgu": "licence navigation seule ; reproduction = accord écrit préalable",
    "statut": "PAS librement addable -> autorisation écrite nécessaire",
}
