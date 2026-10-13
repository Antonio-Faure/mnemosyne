# Lot 3 — bail multi-hôtes, dédup inter-sources, couverture (octobre 2026)

Troisième et dernier lot de l'audit multi-agents. **466 tests verts, ruff OK.**

## 1. Bail : plus de vol hôte ↔ conteneur, reprise rapide conservée

Le problème : un bail (ou un verrou de job) tenu par un autre hostname était
considéré **mort** — pratique après un rebuild de conteneur, mais l'hôte et le
conteneur se volaient mutuellement leurs baux (le « one pilot at a time » était
violé en mode local).

La solution : **le titulaire renouvelle son bail**, et un hostname étranger
n'est plus « mort » par principe (on ne peut pas sonder /proc à travers un
namespace de pid).

- `db.py` : chaque incarnation de process porte un `instance` id (uuid) dans ses
  baux et ses `locked_by`. `renew_own_lease()`, `release_own_lease()`,
  `renew_own_jobs()`, `renew_own()` — **jamais** un bail étranger touché.
- `LEASE_TTL_S = 300` (5 min) au lieu de 8 h / 5 h : le titulaire renouvelle
  toutes les 60 s (boucle du heartbeat + boucle d'activation), donc un bail
  vivant ne perd jamais sa place et une génération morte libère le pilote en
  ≤ 5 min.
- `heartbeat/scheduler.py` + `cli.py` : SIGTERM/SIGINT → `request_stop()`
  libère **nos** baux immédiatement (le rebuild de conteneur repart aussitôt,
  sans attendre le TTL).
- `stale_lock_s` : 18000 → 600 s — les jobs vivants renouvellent leur verrou,
  un runner mort est repris en 10 min (au lieu de 5 h) ; `job_timeout_s` borne
  toujours les jobs mécaniques.
- Tests : bail étranger vivant respecté puis repris à expiration, renouvellement
  qui ne touche que le nôtre, `release` qui ne libère pas celui d'un autre,
  `renew_own_jobs` sélectif.

## 2. Dédup inter-sources (`engine.search`)

Le problème : la même œuvre servie par Europeana, DPLA et Commons sortait en
trois exemplaires (la dédup par `asset.id` est unique par source).

- `normalize/dedup.py` : `dedup_across_sources()` — clé `(titre normalisé,
  créateur normalisé)`, **seulement** pour un titre spécifique (≥ 8 caractères,
  hors « sans titre »/« untitled »…). Le premier fournisseur (ordre catalogue)
  gagne ; deux notices au titre générique restent distinctes.
- Tests : même œuvre → 1 résultat ; titres génériques → 2 conservés.

## 3. Refactor des tests : une passe paramétrée sur tous les descripteurs

- `tests/test_descriptors.py` (nouveau) : chaque YAML est vérifié (chargement,
  `id` == nom de fichier, connecteur attendu — bespoke ou IIIF générique —,
  `extra.collection_id` pour tout point d'entrée IIIF).
- Les **18 clones** `test_descriptor_uses_generic_iiif_connector` ont été
  supprimés des fichiers par source (≈ 100 lignes, imports morts nettoyés par
  ruff).
- `collection_id` manquant ajouté à `albertina` et `leiden` (les deux seuls
  descripteurs mono-manifeste sans identifiant de provenance).

## 4. Couverture : les 5 connecteurs qui n'avaient aucun test

`tests/test_gallica.py` (SRU/XML, ARK, XML cassé), `test_openverse.py`,
`test_internet_archive.py`, `test_wikimedia.py` (nettoyage HTML, skip sans
image), `test_wikidata.py` (recherche d'entité → SPARQL P18, http→https).

## 5. Interrupteurs morts câblés

- `dev.enabled` (jamais lu) : `false` **parke** les activations du codeur (la
  tâche garde sa place, le watchdog alerte si elle traîne).
- `app.log_level` (jamais appliqué) : appliqué au démarrage du service ; le flag
  `--log-level` reste prioritaire et `MNEMOSYNE_LOG_LEVEL` garde la main.

## État

- `main` : **466 tests verts**, ruff OK ; conteneur rebuildé et vérifié.
- Restent hors périmètre (assumés) : fusion des helpers de coercition
  divergents (sémantiques différentes — DPLA récursif, IA `_as_str`…), découpage
  des grosses closures (`_tools`, `_activate_session`).
