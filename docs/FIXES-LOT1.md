# Lot 1 — bugs critiques (audit multi-agents, octobre 2026)

Quatre sous-agents ont audité le dépôt (code mort, bugs cœur, sources,
refactor) : ~60 constats. Ce lot corrige les **6 bugs critiques vérifiés**
(lecture du code + exécution des cas) et durcit les garde-fous de tests.

## 1. `http.py` — le 403 n'atteignait jamais le gouverneur

**Problème** : `RETRY_STATUS = {429, 500, 502, 503, 504}` ne contient pas 403,
donc le test `status_code in (403, 429)` était mort : `governor.report_block()`
n'était appelé que pour un 429. Le RUNBOOK promettait pourtant un cooldown
après 403/429 — l'anti-ban documenté était inopérant (WAF NGA/Hammer, F5
Leiden…).

**Correctif** : le rapport au gouverneur est fait **avant** la branche de
retry ; un 403 n'est pas réessayé (un refus explicite n'est pas transitoire) et
`raise_for_status()` remonte l'erreur au connecteur. Tests : `tests/test_http.py`
(nouveau, le module n'avait aucun test) — 403 rapporté sans retry, 429 rapporté
puis réessayé, 404 invisible au gouverneur.

## 2. `engine.harvest()` / CLI — `enabled: false` ignoré

**Problème** : `Engine.search()` filtre `descriptor.enabled`, mais
`Engine.harvest()` (et `mnemosyne harvest <id>`) ne vérifiaient rien : on
pouvait ingérer `musee_orsay`, `pop`, `mai_saint_etienne`… malgré leur
désactivation.

**Correctif** : garde dans `Engine.harvest()` (+ message CLI). Test :
`test_harvest_refuses_disabled_source` (le connecteur n'est jamais construit).

## 3. `db.save_assets()` — comptait les doublons comme des nouveaux

**Problème** : `INSERT … ON CONFLICT(id) DO NOTHING` + `return len(assets)`
→ une source déjà ingérée était re-comptée comme « nouvelle » et repassait en
`CONNECTED` à chaque re-run.

**Correctif** : comptage réel via `cursor.rowcount`. Test :
`tests/test_db_assets.py` (nouveau).

## 4. Connecteur IIIF — pagination `next` ignorée + taille v3 invalide

**Problème A** : `_manifest_urls()` ne lisait que la première page d'une
collection ; le `next` (v2/v3) n'était jamais suivi. `bsb_collection`
(3,2 M d'objets) plafonnait aux 40 premiers manifestes.
**Problème B** : l'URL image était toujours `…/full/full/0/default.jpg` ; en
Image API 3.0 la taille pleine s'écrit `max` (`full` est v2). Hammer, Orsay,
Princeton, Leiden, Wellesley, SMK… étaient concernés.

**Correctif** : boucle de pagination par collection (`next`, plafond
`_MAX_COLLECTION_PAGES=10` par sécurité, dédoublonnage des pages) ;
`_image_service()` renvoie la taille pleine (`max` si `ImageService3` ou
profil `image/3`, `full` sinon). Tests : pagination exercée dans
`tests/test_iiif.py` et `tests/test_bsb_collection.py` (le `next` du fixture
est désormais suivi, le 2ᵉ manifeste vit page 2) ; attentes v3 passées à `max`.

## 5. ANMT — scraping HTML supprimé (politique « pas de scraping »)

**Problème** : `_discover_arks()` fetchait la page HTML de recherche
(`accept="text/html"`) sans `extra.scraping_consent` — violation de la
politique sur une source **active**. Le garde-test était aveugle
(`text/html` absent des marqueurs).

**Correctif** : suppression du chemin HTML (`_discover_arks`, `_extract_arks`,
`_is_anubis`, `search_url`/`crawl_delay` du YAML) — le connecteur ne sert plus
que les `seeds` via les manifestes IIIF programmatiques. Les marqueurs
`text/html`/`<html` sont ajoutés au garde-test
`test_connectors_do_not_scrape_html_without_consent`. **Pour réactiver la
découverte HTML il faudra un consentement écrit tracé dans
`extra.scraping_consent`.**

## 6. POP — CC BY-NC / BY-ND classées « libres »

**Problème** : les marqueurs libres (`cc by`, `creative commons`) étaient
testés avant les restrictifs : `« Licence CC BY-NC 4.0 »` → `False`
(vérifié en live), donc image republiable à tort si `pop` est réactivée.

**Correctif** : détection des négations (`\bnc\b`, `\bnd\b`,
`non[- ]?commercial`) **avant** les marqueurs libres. Tests paramétrés
étendus (NC/ND → restrictif, CC BY → libre). Le garde-fou
`test_restricted_licenses_are_not_enabled` couvre désormais les 10 sources
restrictives désactivées (belvedere, cudl, ecodices, irht, mai_saint_etienne,
musee_orsay, musei_vaticani, vam, vatican, wellcome).

## État

- `main` : 340 tests verts, ruff OK.
- Commits : `245f720`, `6c8f513`, `8c0db6d`, `cb1bad9`, `3fb9d45`, `d7bdd5b`.
- Lots suivants (audit) : bugs de robustesse service (bootstrap non protégé,
offset Telegram, clé de cache de session, worktree recréé, statut avant bail,
clients LLM non fermés), code mort (`pop.py` test-only, `outcome_status_note`,
branche pHash…), refactors (`conftest.py` FakeHttp, helpers
`connectors/base.py`, `test_http.py`).
