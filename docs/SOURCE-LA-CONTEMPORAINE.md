# Source La Contemporaine (ex-BDIC) — état de l'accès

Statut : **accès à demander** — pas encore de connecteur. Cette note documente
la recherche d'accès pour la mission de source #540 (demande du Résolveur,
phrase `yt_01grGKLcVOc_13` : fonds photographiques 1914-1918 — front, arrière,
industrie de guerre, munitionnettes ; complète l'ECPAD pour 1914-1918 en France).

## L'institution

La Contemporaine (ex-BDIC), Université Paris Nanterre — bibliothèque, archives
et musée d'histoire contemporaine. Ses documents numérisés sont dans
**L'Argonnaute**, la bibliothèque numérique de l'institution
(`https://argonnaute.parisnanterre.fr/`, plus de 200 000 documents : imprimés,
archives, dessins, photographies, affiches).

## Accès constatés (2026-11-25, vérifiés au `fetch_url`)

| Canal | Constat | Usage |
|---|---|---|
| Site `lacontemporaine.fr` | WordPress ; pages descriptives des collections et des catalogues | pas de recherche d'images |
| **L'Argonnaute** (recherche du site) | plateforme de type Nakalona ; le front HTML porte un anti-bot **hCaptcha** (`data-captcha="hcaptcha"`) | **non lisible** par programme (contournement interdit) |
| **OAI-PMH** `argonnaute.parisnanterre.fr/oai-pmh` | répond ; entrepôt « OAI BDIC » ; formats `oai_dc` et `ead` ; **pas de sets** ; `ListRecords` (oai_dc) = **131 notices minimales** (identifiant seul) ; **pas de recherche par mot-clé** | accès programmatique mais **inexploitable** pour une recherche d'images |
| Calames `calames.abes.fr` | catalogue national d'archives ; descriptions de fonds (niveau inventaire) | piste à explorer (API / OAI / SRU à confirmer) |

## Conséquence (politique d'accès aux images)

- La recherche d'images au niveau pièce n'existe pas de façon programmatique
  exploitable : l'OAI-PMH est trop pauvre, et la recherche du site est protégée
  par un anti-bot.
- La Contemporaine n'est **pas** une « petite structure sans aucun accès
  programmatique » : la lecture automatique des pages publiques n'est donc
  **pas** le bon canal, et aucun contournement d'anti-bot (hCaptcha) n'est
  envisagé — règle dure.
- Décision de l'opérateur (2026-11-25) : **demander un accord par e-mail**.

## Action en cours

Demande adressée à **l'agent navigateur** pour envoyer à La Contemporaine
l'e-mail de prise de contact (référence `docs/OUTREACH.md`) posant l'unique
question : un **accès programmatique** au catalogue (API, IIIF, export, ou un
OAI-PMH enrichi donnant accès à la recherche au niveau pièce) est-il possible ;
à défaut, autorisation de lire automatiquement les pages publiques. La réponse
(expéditeur + date) servira soit à construire le connecteur sur l'accès
officiel, soit à tracer `extra.scraping_consent`.

## Prochaines étapes

1. Réponse de l'institution (via l'agent navigateur, `mailwatch`).
2. Si accès officiel : descripteur `config/sources/la_contemporaine.yaml` +
   connecteur `src/mnemosyne/sources/la_contemporaine.py` + test mocké +
   enregistrement dans `src/mnemosyne/sources/__init__.py` + doc + PR.
3. Si refus : abandon documenté (`finish`).
