# Source Roger-Viollet — aucune API exploitable (source non connectée)

Statut : **abandon documenté — aucune API exploitable, accès bloqué (ban d'IP)**.
Pas de descripteur au registre des sources, pas de connecteur. Cette note
documente **deux demandes du Résolveur** :

- **#545** — phrase `yt_01grGKLcVOc_30` (Citroën Rosalie 1932 et record
  d'endurance de Montlhéry 1933) ;
- **#560** — phrase `yt_01grGKLcVOc_84` (faillite de Citroën 1934-35,
  assignation au tribunal de commerce de Paris, André Citroën ; besoin d'une
  vue in-époque du tribunal meilleure que la carte postale 400 px).

Trou de couverture commun : « presse photographique française des années 1930 ».

## L'institution

Roger-Viollet — agence photographique de presse française (« Agence photo
depuis 1938 »). Banque d'images **commerciale** : les droits affichés sont
« Droits gérés » (Conditions Générales de Cession), le portail est protégé par
PicRights, l'agence est membre de la FFAP et d'un groupe (Photononstop,
GraphicObsession, Biosphoto, Biosmotion, Galerie RV). Restriction affichée :
une autorisation de l'agence est requise pour tout usage publicitaire et produits
dérivés.

## Accès constatés par l'agent navigateur (2026-11-25)

| Canal | Constat | Usage |
|---|---|---|
| `robots.txt` | 200 ; autorise le crawl général (bloque seulement des robots SEO nommés : SemrushBot, AhrefsBot, PetalBot, Bytespider…) | — |
| API / IIIF / OAI / open-data | `/sitemap.xml` → 404 ; `/iiif/manifest` → 404 ; `/api`, `/api/v1`, `/swagger`, `/openapi.json`, `/iiif`, `/iiif/2/{id}/manifest`, `/manifest/{id}` → **403** | **aucune API** |
| Pages publiques | pas de JSON-LD, pas de lien de manifeste, `og:image` générique ; recherche = `POST /recherche.php` (champ `s`) → résultats `GET /recherche/{slug}/{id}` ; fiches `/image-photo/{slug}-{inventory_id}` ; vignettes `…-{width}-{hash}.jpg` | lecture des pages publiques seulement |
| WAF / anti-bot | le WAF a répondu 403 puis **banni l'IP** (« Your IP address has been banned »), ban persistant ; aucun contournement tenté | — |

Aucune documentation d'API publique n'est publiée.

## Exemples d'images (le fonds d'époque existe — mais non connectable)

Recherche « Citroën Montlhéry » → 6 images, dont :

- Réf **1494337** — « La petite Rosalie 8 CV sur la piste de l'autodrome de
  Montlhéry suite à son record d'endurance le 27 juillet 1933. » (1933-07-27 ;
  mention « Archives Terre Blanche / Roger-Viollet » ; droits « Droits gérés »).
  C'est le **sujet exact** de la phrase `yt_01grGKLcVOc_30`.
- Réf 1494336 — même sujet, sans la mention du record.
- Réf 1398548 — affiche publicitaire du record battu à Montlhéry.

Ce fonds confirmerait le trou de couverture, mais il n'est atteignable ni
légalement ni techniquement (voir la décision ci-dessous).

## Décision (politique d'accès aux images)

- **Pas d'accès programmatique** ⇒ le seul canal serait la lecture automatique
  des pages publiques, mais elle n'est permise que pour une **petite structure
  sans aucun accès programmatique** et **après autorisation tracée** par e-mail
  (`extra.scraping_consent`). Roger-Viollet est une banque d'images commerciale
  et aucune autorisation de ce type n'est tracée ⇒ **pas de lecture
  automatique**.
- **Contenu commercial « Droits gérés »** : tout usage exige une cession
  payante / une autorisation de l'agence ⇒ règle dure « jamais d'abonnement,
  jamais de paiement » ⇒ **abandon**.
- **WAF hostile (ban d'IP)** : aucun contournement (ni proxy, ni miroir, ni
  navigateur furtif) ⇒ **abandon**.

## Conséquence

La source `roger_viollet` **n'est pas ajoutée** au registre des sources : aucun
descripteur (`config/sources/roger_viollet.yaml`), aucun connecteur, aucun test.
La meta à retenir côté Résolveur est **« aucune API exploitable »** : ne pas
relancer l'ajout de cette source pour ces demandes.

## Piste pour le même imagier (déjà au registre)

**Paris Musées** (Ville de Paris / Bibliothèque historique de la Ville de Paris,
BHVP) est **déjà une source** du registre (`config/sources/paris_musees.yaml` :
accès IIIF sans clé, majorité du domaine public). Plusieurs clichés
Roger-Viollet sont crédités « BHVP / Roger-Viollet » : l'imagerie Paris /
Citroën de la période est probablement atteignable là, légalement. Le Résolveur
peut retester la phrase contre `paris_musees` et `gallica_agences_photos`
(déjà connectés) plutôt que d'attendre Roger-Viollet.

## Mise à jour — demande #560 (phrase `yt_01grGKLcVOc_84`, 2026-11-26)

Le Résolveur a redemandé cette source pour une autre phrase (faillite Citroën
1934-35, assignation au tribunal de commerce de Paris ; besoin d'une vue du
tribunal meilleure que la carte postale 400 px). Nouvelle vérification le
**2026-11-26** :

- `https://www.roger-viollet.fr/` → redirection `/home.php` → **HTTP 403**
  (« Your IP address has been banned (…). If you think this is a mistake,
  please contact the administrator : info (at) roger-viollet.fr »). C'est un
  **ban d'IP au niveau de notre egress** (pas un captcha transitoire).
  Confirmé deux fois : par l'agent navigateur puis par un `fetch_url` direct de
  l'agent codeur (même 403 sur `/home.php`).
- Le domaine apex `https://roger-viollet.fr/` renvoie une erreur de certificat
  (`ERR_CERT_COMMON_NAME_INVALID`) — ce n'est pas le bon hôte.
- Aucun contournement tenté (ni proxy, ni miroir, ni navigateur furtif) :
  politique anti-bot.

Conclusion **inchangée — source non ajoutée** : contenu « Droits gérés »
(commercial, cession payante) ⇒ règle « jamais de paiement » ⇒ abandon ; 403 /
WAF ⇒ pas de contournement ⇒ abandon ; pas d'API ⇒ pas de lecture automatique
sans autorisation tracée. Le déblocage de l'IP ou un accord d'accès officiel
(API/IIIF) relève d'une **décision humaine** (écrire à info@roger-viollet.fr),
hors du périmètre de l'agent codeur, et sans paiement possible de notre côté.

Pour l'image d'époque du sujet (Paris / Citroën / années 1930), réessayer via
les sources **déjà au registre** : `paris_musees` (BHVP, IIIF sans clé) et
`gallica_agences_photos`.
