# Source Conservatoire Citroën (Aulnay-sous-Bois) — état de l'accès et pertinence

Statut : **alias du Centre d'Archives de Terre Blanche — consentement en attente,
pas de connecteur, pas de doublon.**

Cette note documente la mission de source #556 (demande du Résolveur, phrase
`yt_01grGKLcVOc_73` : la crise financière d'André Citroën et le passage sous
contrôle de Michelin en 1934-1935, Pierre Michelin). Le Résolveur visait le
« Conservatoire Citroën » (patrimoine / archives Citroën, Aulnay-sous-Bois).

## 1. Le Conservatoire Citroën n'est pas une source distincte

Le « Conservatoire Citroën & DS » (Aulnay-sous-Bois) est la collection de
**véhicules** (~300 autos) portée par l'association **L'Aventure Peugeot
Citroën DS**. Il n'a **ni photothèque ni API propres**. Ses archives
photographiques sont le **Centre d'Archives de Terre Blanche**
(`https://archives-terreblanche.fr`, Hérimoncourt) — le **même** catalogue déjà
suivi par les missions de source #544 (`citroen_heritage`, phrase `…_30`) et #553
(`aventure_citroen`, phrase `…_72`), cf. `docs/SOURCE-CITROEN-HERITAGE.md` et
`docs/SOURCE-AVENTURE-CITROEN.md`.

→ **Décision d'alias** : `conservatoire_citroen` **ne reçoit pas de descripteur
propre**. C'est un alias du **même** hôte que `citroen_heritage` / `aventure_citroen` ;
créer un troisième descripteur dupliquerait une source (garde anti-doublon : un
hôte déjà couvert = une seule source, cf. `docs/INTEGRATION-SOURCES.md`). Un
**seul** connecteur, une fois autorisé, servira les phrases `…_30`, `…_72`
et `…_73`.

## 2. Accès : aucun accès programmatique (vérifié 2026-11-26)

Relevé par l'agent navigateur : **API REST, IIIF, OAI-PMH, SRU, JSON, sitemap et
robots.txt = HTTP 404** sur tout. Le site est un Symfony + Varnish à rendu
serveur ; les fichiers JPEG sont sous `/upload/documents/`. La « Médiathèque
Citroën » Stellantis (`medialibrary.stellantis.com/citroen`) est réservée aux
professionnels de la communication → non ouverte. Le **seul** canal automatisable
est le **scraper HTML**, donc soumis à `extra.scraping_consent`.

## 3. Consentement : EN ATTENTE (ce n'est pas une autorisation)

L'agent navigateur a envoyé le **2026-11-25 22:45** un e-mail de demande d'accès
programmatique à `archives-avpcd@laventureassociation.com`. Vérifié le
2026-11-26 : le fil ne contient que **1 message sortant, aucune réponse** →
statut **PENDING**. L'approbation de l'opérateur a porté sur l'**envoi** de la
demande, **pas** sur un droit de lire les pages. Aucun
`extra.scraping_consent` n'est donc tracé.

→ Conformément à la règle d'accès aux images (pas de scraping sans autorisation
écrite), **aucun descripteur `protocol: html` ni connecteur HTML n'est committé**
tant que l'autorisation écrite n'est pas reçue. Gardes appliquées par
`tests/test_sources_inventory.py` (`test_html_sources_carry_scraping_consent`,
`test_connectors_do_not_scrape_html_without_consent`).

## 4. Pertinence pour la phrase `…_73` : limite dure du catalogue

Le catalogue **ne contient aucune photographie numérisée** de la faillite
1934-35 ni de l'accord / prise de contrôle de 1935. En l'état, les seules notices
liées à Michelin sont :

| Notice | Titre | Période | Référence (cote) | Numérisée |
|---|---|---|---|---|
| 97389 | Portrait de Mr Pierre Michelin | 01/12/1950 | `DOS2017FIG-01045` | **oui** (703×960) — seule image numérique liée à Michelin, et Pierre Michelin est la personne nommée dans la phrase |
| 96582 | Messieurs Citroën & Michelin | 01/11/1944 | `DOS2017FIG-00496` | **non** (métadonnée seule, aucune image en ligne) |

Recherche iconographique « Michelin » = 43 items / 3 pages ; le seul
Citroën + Michelin **pré-1945** est 96582 (non numérisé), tout le reste = années
1990 (pneus Xantia, rallye). Filtre 1934-1936 « Citroën » = Traction / Rosalie
seulement, rien sur Michelin.

→ Même **une fois le consentement obtenu**, cette source **ne pourra pas**
fournir une image de l'accord Citroën-Michelin de 1935 : au mieux le **portrait
numérisé de Pierre Michelin (notice 97389)**, seule image réelle liée à la
personne citée par la phrase.

## 5. Droits

Toutes les notices : **« Tous droits réservés. Reproduction interdite sans
autorisation. »** (droits d'auteur + marques Citroën / Peugeot / DS ; le site
vend d'ailleurs des reproductions). **Aucune licence libre.** Conséquence :
affichage des **métadonnées + lien vers la notice** uniquement, **aucune copie /
réhébergement** ; une URL d'image (`/upload/documents/…`, en **affichage direct**)
n'est exposée que pour les fiches réellement numérisées.

## Décision et prochaines étapes

1. **Rien de « live » committé maintenant** : consentement en attente → pas de
   descripteur `protocol: html`, pas de connecteur de scraping (règle dure + tests).
2. **À réception d'une autorisation écrite** (référence « e-mail de <expéditeur>
   du <date> ») : construire **un seul** descripteur (`config/sources/…`,
   `protocol: html` + `extra.scraping_consent`), le connecteur
   (`src/mnemosyne/sources/…` : `/recherche` → `/archive/{id}` ; ne conserver que
   les fiches numérisées ; ne **pas** sur-filtrer par société ; prioriser 97389
   pour les requêtes Michelin-Citroën), un test mocké, l'enregistrement dans
   `src/mnemosyne/sources/__init__.py` et la mise à jour de `docs/SOURCES.md`.
   Plan détaillé : `docs/SOURCE-CITROEN-HERITAGE.md`.
3. **Refus** ou silence prolongé : abandon documenté (cette note fait foi).

**Signal au Résolveur** : la phrase `…_73` ne peut pas être illustrée par une
source du catalogue ; le Conservatoire Citroën ne détient pas de photo numérisée
de l'accord de 1935. Ne pas re-demander cette source sous un nouveau slug : c'est,
comme `citroen_heritage` (#544) et `aventure_citroen` (#553), le **même** catalogue
bloqué par consentement.
