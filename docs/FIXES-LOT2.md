# Lot 2 — robustesse, code mort, refactors (octobre 2026)

Suite du **Lot 1** (`docs/FIXES-LOT1.md`). Trois familles : (A) robustesse du
service et des agents, (B) suppression de code mort, (C) refactors sûrs.
Chaque correctif est couvert par un test ; **344 tests verts, ruff OK**.

## A. Robustesse

1. **YAML cassé → plus de crash-loop** (`catalog/registry.py`,
   `heartbeat/scheduler.py`). `yaml.safe_load` est protégé fichier par fichier ;
   `bootstrap()` est enveloppé (log + alerte Telegram) : une config invalide
   écrite par l'agent lui-même ne tue plus le heartbeat en boucle de restart.
2. **Warmups non empilables + quota outbound réel** (`heartbeat/jobs.py`).
   `handle_warmup` refuse de poster une 2ᵉ session tant qu'une warmup est
   ouverte (report 1800 s). La patte « connexion » (inscription = action
   sortante) est refusée tant que `governor.allowed("outbound")` est faux, et
   comptée via `record("outbound")` : les phases de warmup (« 0 sortant les 3
   premiers jours ») sont enfin appliquées au lieu d'être décoratives.
3. **Gouverneur** (`reputation/governor.py`, `engine.py`).
   `account_created_at` avec offset ISO est converti (avant, `.replace(tzinfo=UTC)`
   faussait l'âge du compte — jour 0 lu comme −1). `rate_limit_per_s` des
   descripteurs (44 YAML, jamais lu jusqu'ici) est appliqué par domaine :
   plancher `max(domain_min_interval_s, 1/rate) × pression` — ANMT 0,2/s ⇒ 5 s
   entre requêtes, etc.
4. **Journal** (`journal.py`). Index de la boîte opérateur **recadré** : un
   `inbox.md` tronqué/réécrit ne bloque plus le canal à vie. Horodatages et nom
   de fichier passés en **UTC** (cohérent avec la DB, le soak log, le monitor).
5. **Vault** (`vault/store.py`). `set`/`delete` = relecture + écriture atomique
   sous **flock inter-processus** : un `vault set` (CLI) et un `remember`
   (navigateur) ne s'écrasent plus (perte de mise à jour).
6. **SQL** (`db.py`). `has_open_job`/`has_open_task` échappent `_`/`%` des ids
   de sources (fini les faux positifs de type `bsb_collection` ↔ `bsbXcollection`).
7. **Watchdog** (`monitor.py`). Tous les agents en patinage sont rapportés
   (un marqueur navigateur ne masque plus un marqueur codeur).
8. **Telegram** (`operator/telegram.py`). L'offset n'avance qu'**après**
   traitement de chaque update : un crash en plein lot ne consomme plus des
   réponses jamais routées ; une update « poison » est loguée sans bloquer le
   canal.
9. **Superviseur** (`agents/supervisor.py`). Le statut `running` n'est posé
   qu'après acquisition du bail navigateur (plus de statut mensonger quand le
   bail est refusé) ; `git rev-list` sous timeout (plus de gel du tick).
10. **Worktree codeur** (`dev/worktree.py`, `dev/agent.py`, `supervisor.py`).
    Une activation tuée laisse son worktree ; l'activation suivante de la
    **même** tâche le **réutilise** (marqueur `*.task` à côté du worktree, donc
    aucun fichier non suivi dans `git status`) au lieu de détruire le travail
    non commité que la session croit avoir écrit. Le worktree est conservé sur
    échec, supprimé sur succès ; commandes git sous timeout.
11. **Clients LLM fermés** (`browser/stirrup_client.py` + runners).
    `ZenChatClient.close()` ferme les deux pools httpx (celui de stirrup,
    remplacé sans être fermé, + le nôtre) ; appelé en `finally` par les deux
    runners — plus une fuite de sockets par activation dans un process 24/7.
12. **Clé de cache de session = texte réellement exécuté**
    (`agents/session_cache.py`). `session_base_text()` = texte figé + directives
    permanentes : c'est la clé réelle (stirrup hache les messages envoyés). Les
    réponses restent injectées dans l'historique. Corrige le cas « directives
    définies → session neuve à chaque réponse + caches orphelins que
    `drop_session_cache` ne supprimait jamais ». Limite documentée : une réponse
    arrivant à la toute première activation reste intégrée au texte
    (comportement historique, testé).
13. **Garde anti-double-clic persistant** (`agents/browser_agent.py`). Le
    harness tourne en **processus neuf par snippet** : la liste des clics
    récents était réinitialisée à chaque appel, donc un re-clic au même endroit
    « au pas suivant » passait. L'état est désormais aussi écrit dans
    `data/agent-workspace/clicks.json` (`MNEMOSYNE_CLICK_STATE`), avec repli
    mémoire pour les clics d'un même snippet.

## B. Code mort supprimé

- `sources/pop.py` : endpoints jamais câblés (`manifest_image_services`,
  `_service_ids`, `facet_buckets`, `facets`, `get_notice`, `fetch_manifest`,
  `image_services`) + tests associés (~150 lignes ; récupérables dans l'historique).
- `normalize/dedup.py` : branche pHash jamais alimentée (`image_bytes` toujours
  `None`) ; `imagehash` retiré de l'extra `media` ; flag `dedup` (inerte) retiré
  d'`Engine.search`.
- `supervisor.outcome_status_note` (+ son test) : jamais branché, logique
  divergente du code réel (fausse couverture).
- `warmup_schedule.goal_weights` (test réécrit sur `WARMUP_GOALS`).
- Références périmées : `docs/VISION-BIAGENT.md` (`warmup.py` supprimé),
  `tests/test_dev_guard.py` (chemin mort) ; `.pyc` orphelins nettoyés.

## C. Refactors

- `connectors/base.py` : `Connector.api_key(default_env)` — 3 copies identiques
  supprimées (smithsonian, dpla, europeana).
- `sources/iiif_common.py` : `label()` / `metadata()` partagés entre `iiif.py`
  et `anmt.py` (deux copies verbatim de 31 lignes supprimées).
- Les helpers de coercition divergents (`_first` récursif de DPLA, `_as_str`
  d'Internet Archive…) sont **laissés en place** : leurs sémantiques diffèrent,
  une fusion à l'aveugle serait risquée.

## État

- `main` : 344 tests verts, ruff OK.
- Conteneur rebuildé et vérifié (boot + fix actif).
