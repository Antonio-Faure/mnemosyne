# Musée du Pétrole — Pechelbronn : blocage droits & source désactivée

Mémo de blocage (tâche #189). Source : `musee_petrole_pechelbronn`
(photothèque du Musée français du Pétrole, Merkwiller-Pechelbronn, Bas-Rhin).

## Pourquoi cette source

Demandée par le résolveur adversarial (phrase
`yt_la_france_a_du_petrole_mais_elle_la_oublie_20260925_113`) : le catalogue n'a
aucune image de pétrole **français** (Gallica / Europeana / ANMT renvoient zéro
sur « pétrole »). Pechelbronn est le plus ancien champ pétrolifère exploité
d'Europe ; ses archives (puits, chevalements/derricks, forages, raffineries,
torchères, cartes postales, figures) illustreraient la phrase « partout où on
extrait du pétrole ».

## Accès technique (programmatique — pas de scraping)

Le site expose une API REST WordPress **ouverte et sans clé** :
`https://www.musee-du-petrole.com/wp-json/wp/v2/media` (JSON ; ~1109 médias ;
`per_page` plafonné à 100 ; filtrage image côté client car `mime_type` n'est pas
filtré côté serveur). Métadonnées **minces** : titres dérivés des noms de
fichiers, `caption`/`alt` souvent vides, pas de photographe, pas de date
d'origine (le champ `date` REST n'est que l'horodatage de téléversement CMS → non
promu en `Asset.year`). Le connecteur `src/mnemosyne/sources/musee_petrole_pechelbronn.py`
normalise cette forme vers `Asset` à la frontière.

Le portail catalogue WebMuseo (`/app/collection/*`) renvoie HTTP 403 (mur
anti-bot) et **n'expose pas d'OAI-PMH** : il n'offre pas d'accès programmatique
exploitable et on **ne le scrape pas**.

## Blocage droits (raison de la désactivation)

- Surface **« tous droits réservés »** : mentions légales « © Musée du Pétrole »
  sur musee-du-petrole.com ; portail WebMuseo du Parc naturel régional des
  Vosges du Nord : reproduction / représentation **interdite**.
- **Aucune licence libre** (ni CC, ni domaine public). Pas de réutilisation ni de
  ré-hébergement sans **autorisation écrite** du musée.
- **Le musée est fermé** : décision opérateur du 2026-11-08 — attendre.

Conséquence : le descripteur porte `license: all-rights-reserved` et
**`enabled: false`**. Tant qu'il est désactivé, `Engine.search` ne l'interroge
jamais et le planificateur de moissonnage l'ignore : **aucune image n'est
ré-hébergée**. Le descripteur est maintenu dans la section *Sources désactivées*
de `docs/SOURCES.md` (gardé par `tests/test_sources_inventory.py`).

## Contact — suivi délégué (aucun e-mail depuis cette tâche)

Le suivi du contact est pris en charge par la **tâche #197** (message corrigé,
adresse vivante du Parc, signature anonyme, demande de rendez-vous). **Cette
tâche n'envoie aucun e-mail.** Adresses mortes à **ne pas réutiliser** :

| adresse | état |
|---|---|
| `museedupetrole@wanadoo.fr` | HTTP/SMTP 550 « destinataire invalide » (mort) |
| `musee.petrole@musees-vosges-nord.org` | domaine mail cassé (mort) |
| `contact@parc-vosges-nord.fr` | vivante, seule adresse délivrée (suivi #197) |

## Réactivation (conditions + changement d'une ligne)

Réactiver **uniquement** quand (a) le musée a rouvert et (b) une **autorisation
écrite** + licence de réutilisation (CC BY / CC BY-SA 4.0 **ou** domaine public)
ont été accordées. L'activation est alors un changement d'une ligne dans
`config/sources/musee_petrole_pechelbronn.yaml` :

```yaml
enabled: true
license: "CC BY-SA 4.0"   # ou CC BY 4.0 / domaine public, selon l'accord écrit
```

puis déplacer la ligne de la section *désactivées* vers la section *actives* de
`docs/SOURCES.md` (les compteurs sont suivis par
`tests/test_sources_inventory.py`).

## Références

- Descripteur : `config/sources/musee_petrole_pechelbronn.yaml` (`enabled: false`)
- Connecteur : `src/mnemosyne/sources/musee_petrole_pechelbronn.py`
- Tests (hors-ligne) : `tests/test_musee_petrole_pechelbronn.py`
- Inventaire : `docs/SOURCES.md` (Sources désactivées)
