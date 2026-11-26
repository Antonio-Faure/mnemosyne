# Source Citroën Heritage — restructuration des années 1930 (phrase `yt_01grGKLcVOc_74`) : trou de couverture confirmé

Statut : **abandon documenté pour cette demande — trou de couverture confirmé
et accès sous droits réservés sans consentement tracé.** Pas de fichier
descripteur au registre des sources, pas de connecteur, pas de test. Cette note
documente la mission de source #558 (demande du Résolveur adversarial, phrase
`yt_01grGKLcVOc_74` : l'usine du quai de Javel et la restructuration Citroën des
années 1930 — plan Michelin, grandes grèves de 1935, licenciements —, que le
périmètre actuel ne couvre pas).

Source visée : **`citroen_heritage`** — Citroën Heritage / L'Aventure Peugeot
Citroën DS (niveau 1 de la carte des sources). Adresse fournie par la demande :
`https://www.laventurepeugeotcitroends.fr`.

## L'institution

L'Aventure Peugeot Citroën DS — association patrimoniale du constructeur. Son
fonds numérisé est exposé par le **Centre d'Archives de Terre Blanche**
(`https://www.archives-terreblanche.fr/`). C'est la même institution déjà suivie
pour les missions #544 (Rosalie, `docs/SOURCE-CITROEN-HERITAGE.md`) et #553
(ouvriers/usines du quai de Javel, `docs/SOURCE-AVENTURE-CITROEN.md`).

Chaîne d'URL constatée : `laventurepeugeotcitroends.fr` → 301 →
`laventure-association.com` ; le lien « Rechercher une archive » pointe sur
`archives-laventurepeugeotcitroends.com/fr/…` qui redirige vers
`archives-terreblanche.fr/fr/…` = **404** (lien périmé).

## Deux blocages indépendants (vérifiés par l'agent navigateur, 2026-11-26)

### 1. Droits / consentement (rédhibitoire)

| Canal | Constat |
|---|---|
| `/mentions-legales` | tous droits réservés ; reproduction, utilisation et copie **interdites** ; aucune licence libre |
| `robots.txt`, `sitemap.xml` | 404 |
| accès programmatique (`/api`, `/iiif`, `/oai`, `/graphql`, `/search`) | 404 sur tout — **aucun accès programmatique** ; uniquement du HTML rendu côté serveur |
| autorisation de lecture automatique des pages publiques | e-mail envoyé le 2026-11-25 à `archives-avpcd@laventureassociation.com` : **aucun rebond, aucune réponse** au 2026-11-26 |

Sans **autorisation reçue par e-mail** (référence `extra.scraping_consent`), la
lecture automatique des pages publiques est interdite (règle dure « Accès aux
images — pas de scraping »). Le seul canal technique étant le HTML, **aucun
connecteur `html` n'est possible** tant que le « oui » n'est pas arrivé. Aucun
contournement d'anti-bot n'a été tenté (règle dure).

### 2. Couverture 1934-1937 = zéro (numérisée)

Même en ignorant les droits, la source ne remplirait pas la phrase. Seuls items
Citroën / Javel des années 1930 présents : **non numérisés** ou hors fenêtre.

| Réf. | Titre | Période | État |
|---|---|---|---|
| 142763 | Hall de l'usine Citroën quai de Javel — banquet 08/10/1933 | 1933 | non numérisé (métadonnée seule) |
| 142772 | Hall de l'usine Citroën quai de Javel — banquet | 1933 | non numérisé |
| 96611 | « L'usine de Javel en 1934 » | document daté **1946** | non numérisé, et pas de 1934 |
| 96272 | Réfectoire de l'usine de Javel | **1941** | numérisé, hors fenêtre |
| 1977 | (Javel) | hors fenêtre | numérisé, hors fenêtre |

Termes de l'événement en 1930s — **grève / grèves / manifestation / occupation
d'usine / Front populaire / Michelin / licenciements = 0 item**.

Faux positifs écartés : « Ouvriers assemblant un moteur » 1930-1939 (11024,
11027) = **Panhard**, pas Citroën ; « 60344 Quai d'embarquement » = **Peugeot**.

## Alternatives vérifiées (aucune ne comble le trou)

- **La Contemporaine / L'Argonnaute** (université Paris Nanterre ; accès
  programmatique JSON `/visualizer/api` + affichage direct) : possède une série
  « Usine Citroën Quai de Javel », mais datée **~1915** (Albums Valois, usine
  d'obus) = exactement les vues « obus 1915 » déjà au périmètre et
  anachroniques. « Citroën 1935/1936 » → 0. Suivie séparément dans
  `docs/SOURCE-LA-CONTEMPORAINE.md`.
- **Gallica** (SRU) → 403 au robot descriptif (non contourné ; Gallica est déjà
  une source du registre).

## Décision (politique d'accès aux images)

- **Pas d'accès programmatique** ⇒ le seul canal serait la lecture automatique
  des pages publiques, permise seulement après autorisation tracée par e-mail ;
  aucune autorisation n'est reçue ⇒ **pas de lecture automatique, pas de
  connecteur**.
- **Contenu sous droits réservés** (marques Citroën / Peugeot / DS ; le site
  vend des reproductions) ⇒ aucune licence libre.
- **Couverture 1934-1937 nulle** ⇒ même autorisée, la source ne fournirait pas
  l'image de l'événement.

## Conséquence

La source `citroen_heritage` **n'est pas ajoutée** au registre des sources pour
cette demande : aucun fichier descripteur
(`config/sources/citroen_heritage.yaml`), aucun connecteur, aucun test. Issue
Atelier correspondante : **Sans source** (aucune source exploitable trouvée) —
et **trou de couverture** confirmé côté Résolveur pour l'événement
« usine du quai de Javel / restructuration 1934-1937 ».

**Ne pas relancer l'ajout de cette source pour cette demande** : la phrase
`yt_01grGKLcVOc_74` est un **trou de couverture connu** (aucune image numérisée
publique de l'événement trouvée).

## Si un jour on connecte cette institution

Ce ne serait **pas** pour combler 1934-1937 (rien de numérisé), mais comme
**source patrimoniale générale Citroën / Peugeot** (ce qu'elle couvre vraiment :
par ex. promotion Rosalie 1928-1933, déjà demandée par la phrase
`yt_01grGKLcVOc_30` — mission #544), et **seulement après le « oui » explicite
de l'institution** (accès officiel, ou autorisation de lecture automatique des
pages publiques tracée par e-mail). Unifier alors le slug : la demande de la
tâche parle de `citroen_heritage`, la note #553 réserve `aventure_citroen` — un
seul identifiant pour l'institution.

## Note de recherche reproductible

Une note de recherche et un utilitaire reproductible (`scan()`) ont été
produits par l'agent navigateur (PR GitHub `#186`, helper
`citroen_javel_1930s_research.py`).
