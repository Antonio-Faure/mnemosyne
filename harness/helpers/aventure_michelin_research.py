"""Dossier de recherche — source « L'Aventure Michelin » (musée Michelin,
Clermont-Ferrand). Agent navigateur, tâche #555.

Résolveur adversarial : phrase yt_01grGKLcVOc_73 — prise de contrôle de Citroën
par Michelin (1934-1935), Pierre Michelin, Édouard Michelin.

Ce module est une NOTE DE RECHERCHE versionnée (données statiques + URLs).
Il n'exécute AUCUNE requête réseau et ne copie / n'héberge aucune image.

STATUT (2026-11-26) : AUCUN accès programmatique public. Prise de contact
envoyée (e-mail) au service du patrimoine historique Michelin — cf. EMAIL_SENT
ci-dessous. En attente de réponse. NE PAS committer de connecteur « live »
tant que l'accès n'est pas accordé.
--------------------------------------------------------------------
1. INSTITUTION
   Nom (slug)  : aventure_michelin — « L'Aventure Michelin »
   Type        : musée d'entreprise (GLAM, groupe Michelin), ouvert en 2009.
   Adresse     : 32 rue du Clos Four, 63100 Clermont-Ferrand, France
   Tél / Fax   : +33 (0)4 73 98 60 60 / +33 (0)4 73 98 60 69

2. DOMAINES / URLS (vérifiés 2026-11-26)
   Site officiel (visite) : https://laventure.michelin.com          [200]
   Version EN              : https://laventure.michelin.com/en/
   Billetterie             : https://billetterie.laventure.michelin.com
   Boutique                : https://boutique.laventure.michelin.com
   ⚠ www.laventuremichelin.com (sans point) = NXDOMAIN — NE PAS utiliser.
   Sous-domaines patrimoine./heritage./archives./collection.michelin.com
   = NXDOMAIN. Pas de portail patrimoine séparé. www.michelin.com = corporate
   (marketing), sans archives.

3. ACCÈS PROGRAMMATIQUE AUX IMAGES : INEXISTANT (vérifié 2026-11-26)
   - Pas d'API, pas de IIIF, pas d'OAI-PMH, pas de JSON de collections.
   - robots.txt : « User-agent: * / Disallow: » (vide) → crawl autorisé, mais
     aucune image d'archive indexable (seulement pages visite/presse/scolaires).
   - Sitemaps Yoast : page-, news-, download_document(-category)-,
     document_tags-sitemap.xml → pages visite + PDF pédagogiques (dossiers
     scolaires) + PDF presse. AUCUNE image d'archive.
   - WordPress REST : /wp-json/ répond, MAIS /wp-json/wp/v2/media → 401
     « Kadence/iThemes Security: REST API access restricted ». Endpoints
     posts/pages/media non publics ⇒ pas de surface média exploitable.
     (Ne pas contourner — règle anti-bypass.)
   - Recherche interne du site (?s=Pierre+Michelin) : aucun résultat pertinent.
   - Aucun catalogue/photothèque en ligne : la recherche web ne renvoie que la
     boutique (visuels issus des archives, vendus), du stock commercial
     (Alamy/Shutterstock/Getty) et Wikimedia Commons (photos du musée visité,
     PAS les portraits d'archive).

4. FONDS & DROITS
   Les portraits d'Édouard et Pierre Michelin et les photos de la reprise
   Citroën (1934-1935) sont détenus par le « service du patrimoine historique
   Michelin » (interne au groupe). Reproduction payante via la boutique.
   Tous droits réservés (droits d'auteur + marques Michelin/Bibendum). Aucune
   licence libre ⇒ afficher métadonnées + lien uniquement ; aucune copie.

5. CONTACT OFFICIEL (vérifié sur le site officiel)
   E-mail général : contact@laventure.michelin.com   (seule adresse publiée)
   Formulaire     : https://laventure.michelin.com/contact/
                    → « Objet de la demande » contient une entrée dédiée
                      « Contacter le service patrimoine historique Michelin ».
   C'est le SEUL canal vers le patrimoine historique (pas d'e-mail dédié).

6. MARCHE À SUIVRE : PRISE DE CONTACT — FAITE le 2026-11-26
   Aucun accès public ⇒ e-mail envoyé à contact@laventure.michelin.com (à
   l'attention du service du patrimoine historique) pour demander un accès
   programmatique au catalogue (API/IIIF/OAI/export) ; à défaut, l'autorisation
   de lire les pages publiques (mais il n'y a PAS de pages d'archive publiques).
   Réponse « non » ⇒ ne pas ajouter la source. Réponse « oui » ⇒ le CODER
   implémente descripteur + connecteur, tests, doc, PR (l'agent navigateur
   n'écrit que des helpers, jamais le code produit).

7. DÉCISION DE FIN DE TÂCHE (agent navigateur, 2026-11-26)
   - La source NE peut PAS être ajoutée comme connecteur « live » : aucun
     accès programmatique public aux images.
   - E-mail de demande d'accès envoyé (validé par l'opérateur) et vérifié dans
     le dossier « Messages envoyés » ; aucun rebond 550 à ce jour.
   - Statut = OUTREACH_SENT : en attente de la réponse de Michelin.
   - Codeur informé (message #548) : ne pas committer de connecteur live.
--------------------------------------------------------------------
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Données structurées (factuelles, vérifiées 2026-11-26)
# ---------------------------------------------------------------------------

INSTITUTION = {
    "slug": "aventure_michelin",
    "name": "L'Aventure Michelin (musée Michelin, Clermont-Ferrand)",
    "type": "museum",
    "operator": "Manufacture Française des Pneumatiques Michelin",
    "opened": 2009,
    "address": "32 rue du Clos Four, 63100 Clermont-Ferrand, France",
    "phone": "+33 (0)4 73 98 60 60",
    "fax": "+33 (0)4 73 98 60 69",
}

SITE = {
    "homepage": "https://laventure.michelin.com",
    "homepage_en": "https://laventure.michelin.com/en/",
    "ticketing": "https://billetterie.laventure.michelin.com",
    "shop": "https://boutique.laventure.michelin.com",
    "contact_page": "https://laventure.michelin.com/contact/",
    "corporate": "https://www.michelin.com",
    # À NE PAS utiliser : ancien domaine sans point = NXDOMAIN.
    "do_not_use": ["www.laventuremichelin.com"],
}

CONTACT = {
    "email": "contact@laventure.michelin.com",  # seule adresse publiée
    "is_sole_published_address": True,
    "form_url": "https://laventure.michelin.com/contact/",
    "form_patrimoine_option": (
        "Objet de la demande : « Contacter le service patrimoine historique "
        "Michelin »"
    ),
    "note": (
        "Le patrimoine historique Michelin est interne au groupe ; aucun e-mail "
        "dédié publié. Le seul canal est l'e-mail général ou le formulaire."
    ),
}

RIGHTS_TEXT = (
    "Tous droits réservés — droits d'auteur + marques Michelin/Bibendum. "
    "Aucune licence libre. Accès payant via la boutique pour la reproduction. "
    "Mnemosyne affiche métadonnées + lien uniquement, aucune copie."
)

# Résultat de l'enquête d'accès programmatique.
ACCESS = {
    "status": "OUTREACH_SENT",
    "public_programmatic_access": False,
    "api": None,
    "iiif": None,
    "oai_pmh": None,
    "json_collections": None,
    "wordpress_rest": {
        "root": "https://laventure.michelin.com/wp-json/",
        "media_endpoint_status": 401,
        "media_endpoint_note": (
            "Kadence/iThemes Security: REST API access restricted — "
            "non public, NE PAS contourner."
        ),
    },
    "robots_txt": "User-agent: * / Disallow: (vide — crawl autorisé)",
    "sitemaps_indexable_archive_images": False,
    "online_catalog_exists": False,
    "holdings_location": "service du patrimoine historique Michelin (interne)",
    "verified_on": "2026-11-26",
    "note": (
        "Aucune API/IIIF/OAI/JSON ; aucune photothèque en ligne. Les portraits "
        "d'Édouard/Pierre Michelin et les photos de la reprise Citroën (1934-35) "
        "existent mais restent internes, droits réservés."
    ),
}

# Journal de l'e-mail de prise de contact (envoyé et vérifié).
EMAIL_SENT = {
    "status": "SENT_VERIFIED",
    "date_local": "2026-11-26 13:37",
    "from": "archivist.mnemosyne@gmail.com",
    "to": ["contact@laventure.michelin.com"],
    "cc": [],
    "attachments": [],
    "subject": (
        "Mnemosyne — ajouter les images d'archives du musée Michelin "
        "(L'Aventure Michelin) à un moteur de recherche"
    ),
    "operator_validated": True,
    "verified_in_sent_folder": True,
    "bounce_550": False,
    "body_examples": [
        "portraits d'Édouard et Pierre Michelin",
        "usine Michelin de Clermont-Ferrand",
        "affiches et Bibendum des années 1930",
    ],
    "body_note": (
        "Modèle Archivist standard (4 paragraphes : qui / pourquoi / question "
        "accès programmatique / transparence). Exemples de requêtes adaptés aux "
        "collections Michelin (ci-dessus). Une seule question ; mentions "
        "« aucune copie, aucun hébergement, aucune redistribution, aucune "
        "revente » + lien docs/POUR-LES-INSTITUTIONS.md + Antonio Faure."
    ),
    "note": "Aucun brouillon resté ouvert ; à surveiller pour un éventuel rebond.",
}

# Informations pour un éventuel descripteur (à implémenter côté CODER si accès
# accordé — NE PAS committer de connecteur live maintenant).
DESCRIPTOR = {
    "slug": "aventure_michelin",
    "name": "L'Aventure Michelin (musée Michelin, Clermont-Ferrand)",
    "type": "museum",
    "homepage": "https://laventure.michelin.com",
    "protocol": None,          # pas d'accès public
    "rights": RIGHTS_TEXT,
    "status": "OUTREACH_SENT",  # en attente de réponse institutionnelle
}


# ---------------------------------------------------------------------------
# API du module (helpers réutilisables, sans réseau)
# ---------------------------------------------------------------------------

def contact_info() -> dict:
    """Retourne les canaux de contact officiels (e-mail + formulaire)."""
    return dict(CONTACT)


def descriptor() -> dict:
    """Retourne un descripteur de source proposé (statut OUTREACH_SENT).

    Ne PAS enregistrer comme connecteur live : aucun accès programmatique
    public n'a été accordé à ce jour (2026-11-26).
    """
    return dict(DESCRIPTOR)


def summary() -> dict:
    """Vue d'ensemble compacte de l'état de la source."""
    return {
        "slug": INSTITUTION["slug"],
        "access_status": ACCESS["status"],
        "public_programmatic_access": ACCESS["public_programmatic_access"],
        "email_status": EMAIL_SENT["status"],
        "email_to": EMAIL_SENT["to"],
        "email_date": EMAIL_SENT["date_local"],
        "verified_on": ACCESS["verified_on"],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
