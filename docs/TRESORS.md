# Trésors — *Affiches de la Belle Époque (1890–1914)*

Manifeste source : `/app/data/collections/affiches-belle-epoque.json`
Helper de collecte : `harness/helpers/belle_epoque.py` (PR #6)
Statut : collection livrée, licences libres vérifiées, prête pour l'agrégation.

## 1. Thème et périmètre

Affiches et planches lithographiées de la **Belle Époque** (≈1890–1914) :
réclames, spectacles, expositions, et la série *Les Maîtres de l'Affiche*
(portfolios mensuels de planches réduites publiés par Chaix/Imprimerie Chaix,
1895–1900). Artistes notables couverts par les *seeds* : **Jules Chéret**,
**Alphonse Mucha**, **Eugène Grasset**.

- **Nombre d'items : 30**
- **Sources : 3** (Wikimedia Commons, Internet Archive, Cleveland Museum of Art)
- **Doublons : 0** (aucune `page_url` ni `image_url` répétée)

## 2. Sources et licences exactes

| Source | Items | Licence (texte exact) | URL de licence |
|---|---:|---|---|
| Wikimedia Commons | 15 | Public domain (PD / PDM) | https://commons.wikimedia.org/wiki/Commons:Copyright_tags |
| Internet Archive | 8 | Public Domain Mark 1.0 / CC0 1.0 Universal | https://creativecommons.org/publicdomain/mark/1.0/ |
| Cleveland Museum of Art | 7 | CC0-1.0 (Open Access) | https://creativecommons.org/publicdomain/zero/1.0/ |

Total = 15 + 8 + 7 = **30 items**, toutes en licence libre
(domaine public ou CC0). Aucune œuvre sous droit d'auteur restrictif.

Seeds de (re)collecte déclarés dans `config/sources/` :

- `wikimedia.yaml` — « Les Maîtres de l'Affiche », « Alphonse Mucha poster »,
  « Jules Chéret affiche », « affiche Belle Époque 1900 ».
- `internet_archive.yaml` — « affiche poster 1890-1914 », « Les Maîtres de
  l'Affiche », « Mucha affiche poster ».
- `cleveland.yaml` — source **keyless** ajoutée (REST, CC0) :
  `https://openaccess-api.clevelandart.org/api/artworks/`, seeds « affiche »,
  « poster », « Jules Chéret », « Alphonse Mucha ». Reproductible sans clé.

## 3. Schéma des champs (un item du manifeste)

| Champ | Type | Description |
|---|---|---|
| `title` | string | Titre de l'œuvre / de la planche |
| `creator` | string | Auteur (graveur / illustrateur), éventuellement « variés » |
| `date` | string | Date de création ou de publication (ex. `"1896"`) |
| `source` | string | Fournisseur (`Wikimedia Commons`, `Internet Archive`, `Cleveland Museum of Art`) |
| `page_url` | string (HTTP 200) | Page descriptive pérenne de l'item |
| `image_url` | string (HTTP 200, `image/*`, JPEG) | Fichier image plein format |
| `license` | string | Libellé exact de licence (voir §2) |
| `license_url` | string | URL canonique de la licence (Creative Commons / Commons) |
| `retrieved_at` | string (ISO 8601) | Horodatage de collecte, ex. `2025-01-15T10:00:00Z` |

Le connecteur ne fait jamais fuiter la forme brute d'un fournisseur : à la
frontière il normalise vers l'`Asset` canonique (`src/mnemosyne/models.py`),
le surplus allant dans `Asset.extra`.

## 4. Méthode de collecte et vérification

1. Interrogation *paced* de chaque fournisseur via le helper
   `harness/helpers/belle_epoque.py` (User-Agent descriptif pour Wikimedia,
   User-Agent navigateur pour Gallica, `maxlag=5`, retries espacés).
2. Pour chaque candidat : **vérification HTTP 200** de `page_url` et
   `image_url`, contrôle du `Content-Type` (`image/*`) et de la signature
   binaire (magic bytes JPEG `FF D8 FF`) pour écarter les vignettes HTML.
3. **Déduplication** sur `page_url` **et** `image_url` (aucune URL répétée).
4. **Filtre de licence** : seules les œuvres domaine public / CC0 / PDM sont
   conservées (allowlist). Un `license` + `license_url` canonique est attaché.
5. Horodatage ISO 8601 de la récupération (`retrieved_at`).

## 5. Note sur Gallica et loc.gov (écartés)

- **Gallica (BnF SRU)** était supporté par le helper, mais ses conditions de
  réutilisation ne garantissent pas une licence 100 % libre (restrictions
  commerciales / « réutilisation non commerciale ») : écarté pour garder la
  collection entièrement PD/CC0/PDM.
- **Library of Congress (loc.gov)** : droits mixtes et dépendance à une clé
  d'API — écarté au profit de la Cleveland Open Access API (sans clé, CC0).

## 6. Révision — échange d'un item Internet Archive

Depuis le message précédent, l'item Internet Archive « Cinématographe Lumière »
(image servie par une URL `500` permanente) a été **remplacé** par :

- *Poster for "Elles"* — Henri de Toulouse-Lautrec, 1896,
  IA id `PosterforElles-NGA`, `rights=Public domain`,
  https://archive.org/details/PosterforElles-NGA

La fixture hors-ligne `tests/fixtures/affiches_belle_epoque.json` reflète ce
remplacement (source Internet Archive, licences toujours 100 % libres).

## 7. Tests

- `tests/test_affiches_belle_epoque.py` — vérifie le schéma (9 champs/item),
  l'unicité de `page_url`/`image_url`, l'allowlist de licences et le format
  ISO 8601 de `retrieved_at`. Aucun accès réseau.
- `tests/test_cleveland.py` — descripteur keyless REST + connecteur mocké
  (normalisation vers `Asset`).
