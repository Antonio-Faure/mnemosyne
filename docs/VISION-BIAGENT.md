# Vision — mnemosyne, bi-agent autonome

> Document de référence (validé). À lire **avant toute reprise** du chantier
> agent, notamment après une compaction de session : il contient la vision
> complète et l'état exact de l'implémentation.

## 0. Mission

Trouver les **meilleures images d'archives historiques** pour une requête.
Le goulot n'est pas la recherche mais **l'accès aux sources** (des centaines de
fournisseurs hétérogènes). On délègue ce travail à un agent autonome, qui doit
savoir **à la fois utiliser un navigateur ET écrire du code**.

## 1. Architecture d'exécution — « Version A » (faite)

**Un seul conteneur** (`mnemosyne`), pas de conteneur Chrome séparé. Dedans :
l'appli, un **vrai Chrome** (headful sous Xvfb + noVNC + CDP `127.0.0.1:9222`),
`browser-harness`, `ffmpeg`, `git`.

Règles :
- tout tourne en **uid 1000** → sandbox Chrome **activé** (jamais `--no-sandbox`),
  chemins et permissions identiques entre l'agent, le navigateur et les fichiers ;
- **un seul propriétaire du CDP** : une seule chose pilote Chrome à la fois
  (sinon conflits — c'est l'erreur qui a motivé cette refonte) ;
- `security_opt: seccomp=unconfined` (le sandbox Chrome a besoin des namespaces) ;
- ports en **loopback** uniquement (6080 VNC, 9222 CDP, 8080 API) ;
- le réseau sort par l'IP résidentielle, **jamais par Tailscale**
  (`scripts/check-egress.sh`, `make egress`).

Fichiers : `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`.
Commandes : `make up|down|logs`, `make cdp`, `make vnc|record`, `make egress`.

## 2. Le bi-agent (vision validée)

**Deux sessions Stirrup distinctes**, même provider (OpenCode Go / Zen,
`deepseek-v4.1-flash`), **un seul agent actif à la fois**.

Chaque agent a son **fichier de consignes** (prompt système), chargé au runtime
depuis le repo (monté) — donc modifiable à chaud, sans rebuild :
`agents/coder.md` et `agents/browser.md`. (Ne pas confondre avec `AGENTS.md`, qui
s'adresse à un agent codeur travaillant **sur** ce dépôt.)

### 2.1 Agent CODEUR (le produit)

Rôle : faire **le produit final** — l'API d'agrégation et ses connecteurs.

Outils/permissions :
- éditer le code du produit, tests, `git` (commit/push/PR) avec le **token
  GitHub** (vault) ;
- **recherche doc** : webfetch (`fetch_url`, pour lire une doc ou un dépôt
  GitHub) — **mais PAS le navigateur** ;
- **il ne fait pas** de helpers pour l'agent navigateur, ni de navigation.

Implémentation actuelle : `src/mnemosyne/dev/agent.py` (`run_dev_agent`),
`src/mnemosyne/dev/tools.py`, lancé par `mnemosyne agency --to coder` /
`connect-next` (plus de commande `develop` séparée).
Il travaille dans un **worktree git jetable** (`data/agent-worktree`) pour ne
jamais changer la branche du dépôt principal.

### 2.2 Agent NAVIGATEUR (le harness)

Rôle : tout ce qui est **navigateur** — warmup, recherche précise nécessitant
de naviguer, envoi de mails, remplissage de formulaires, obtention d'accès/clés,
**et** l'amélioration de son propre harness (helpers) et **le film**.

Outils/permissions :
- **browser-harness** : helpers (`goto_url`, `scroll`, `type_text`, `click_at_xy`,
  `upload_file`, `new_tab`, `switch_tab`, `capture_screenshot`, …), enregistrement
  et **export vidéo** ; il ajoute des **helpers au fil de l'eau** ;
- édition **limitée aux helpers** (allowlist : dossier des helpers), + `git`
  (token GitHub) pour pousser les helpers ;
- **il n'édite pas** le code du produit.

### 2.3 Communication entre les deux agents

- **Boîte aux lettres durable** : chaque message = `de`, `à`, `corps`, statut
  (`pending`/`running`/`handled`/`review`/`failed`), horodatage. Le **claim est
  atomique** (un seul écrivain par message) et un message resté `running` après
  un crash est repris automatiquement. Un outil `send_message` sur **chaque**
  agent écrit dedans.
- **Superviseur déterministe** (le heartbeat, PAS un LLM) : il lit la boîte,
  **lance l'agent destinataire quand l'émetteur s'est arrêté**, puis rend la
  main. Les agents ne se lancent **jamais** eux-mêmes.
- **Un seul agent à la fois** (turn-taking) → un seul pilote Chrome.
- **Secrets via le vault, jamais dans les messages** : l'agent navigateur
  stocke la clé (`remember("europeana_api_key", …)`, réservé aux clés non
  critiques) et envoie une **référence** ; le moteur l'exporte en variable
  d'environnement au démarrage (`docs/CREDENTIALS.md`).
- **Canal opérateur désactivé** (stationné) : les agents ne s'écrivent qu'entre
  eux ; un message adressé à `operator` est refusé. Les blocages se terminent par
  un résumé factuel (`task_done`) et l'opérateur regarde le journal.
- **Bornes anti-boucle** : nombre max d'échanges (`max_handoffs`) ; « note du
  jour » alimentée par chaque agent (journal).
- **Routage au lancement** : selon l'intention, on lance `agent codeur` (produit)
  ou `agent navigateur` (web). L'opérateur peut aussi déposer un message dans la
  boîte et laisser le superviseur router.

### 2.4 Exemple de référence (Europeana)

1. Opérateur : « lance l'agent codeur pour avoir accès à Europeana ».
2. **Codeur** : recherche la doc, explore le produit, écrit le connecteur ;
   constate qu'il manque la **clé API** → `send_message(à="navigateur",
   corps="j'ai besoin de la clé API Europeana")` → commit/push de ce qu'il a
   fait → note du jour → **s'arrête**.
3. **Superviseur** : lance l'**agent navigateur**.
4. **Navigateur** : comprend le besoin, va sur Europeana, (crée un helper si
   besoin), crée un **compte**, remplit l'e-mail, génère un **mot de passe
   robuste** (gestionnaire de mots de passe de Chrome), confirme l'adresse via
   **Gmail dans un autre onglet**, navigue jusqu'à la création de **clé API**,
   la **stocke dans le vault** → `send_message(à="codeur", corps="clé dispo :
   vault:europeana_api_key")` → commit/push des helpers → note du jour →
   **s'arrête**.
5. **Superviseur** : relance l'**agent codeur** ; la clé est exportée depuis le
   vault en variable d'environnement (`EUROPEANA_API_KEY`) au démarrage du
   moteur : il teste, corrige, commit/push, note du jour, s'arrête.

## 3. Navigateur & vidéo (browser-harness)

- Le **même Chrome** sert de moteur de rendu pour l'export vidéo : la page
  `video.html` est ouverte dans le Chrome attaché, elle exporte un `.webm`
  (téléchargement via CDP), puis `ffmpeg` produit le `.mp4`.
- Pipeline : `start_recording()` → actions → `stop_recording()` →
  `browser-harness video init <dir>` → écrire `edit-brief.json` →
  `video review` → `video export --reviewed`.
- Contraintes du brief (validateur) : `plan` **2–5** items, `privacy.reviewedFrames`
  obligatoire, **narration « collante »** (ne la mettre que lorsqu'elle change).
- Variable d'env : `BU_CDP_URL=http://127.0.0.1:9222`, `BH_HOME=/app/data/browser-harness`
  (les enregistrements persistent dans `data/`).
- Un seul stack navigateur : **browser-harness** via l'agent navigateur du
  bi-agent (plus d'agent browser-use générique).

## 4. Ce qui existe / ce qui reste

**Existe (fait) :**
- Version A (conteneur unique, Chrome sandboxé uid 1000, un seul CDP).
- `browser-harness` opérationnel (record + export vidéo OK).
- Agent codeur via `agency` / `connect-next` (Stirrup, PR, worktree isolé).
- Générateur de connecteurs IIIF générique (`src/mnemosyne/sources/iiif.py`) +
  découverte (`src/mnemosyne/discovery/`) + 1 connexion/jour (timer).
- Warmup auto (1–2/jour, sites pondérés), vault, Telegram, journal.

**Bi-agent (fait) :**
1. **Boîte aux lettres** durable : table `messages` (`src/mnemosyne/db.py`) +
   `src/mnemosyne/agents/mailbox.py`.
2. **Superviseur** déterministe : `src/mnemosyne/agents/supervisor.py`
   (`run_agency`) — un agent à la fois, hand-offs bornés, routage auto.
3. **`send_message`** côté codeur (`DevToolProvider`) et côté navigateur.
4. **Agent navigateur** : `src/mnemosyne/agents/browser_agent.py` (Stirrup) —
   outil `browser(code)` qui exécute browser-harness, édition **allowlist
   helpers** (`data/agent-workspace/helpers/`), `send_message`, `task_done`.
5. **CLI** : `mnemosyne agency "<tâche>" [--to coder|browser] [--max N]` et
   `mnemosyne messages`.
6. Le **codeur** tourne aussi dans le conteneur (dépôt monté sur `/repo`,
   `MNEMOSYNE_DEV_REPO=/repo`, worktree isolé) → `agency` fait tourner les deux.

**Bi-agent — suite (fait) :**
- **Autonomie heartbeat** : job `agency` (toutes les 2 min, coût nul s'il n'y a
  rien) → `supervisor.run_pending_once()` exécute **un** message en attente
  (codeur ou navigateur), turn-taking. Vérifié : un message posté est traité
  seul par le heartbeat.
- **Git des helpers** : l'agent navigateur écrit dans
  `harness/helpers/` via un **worktree git dédié**
  (`data/agent-workspace/helpers-worktree`) et `publish_helpers(summary)`
  commit + push + PR (scopé `harness/helpers/` uniquement).
- **Skills du harness** : vendored dans `harness/skills/*.md` (extraits de
  `browser-use/browser-harness`, MIT) et injectés dans le prompt de l'agent
  navigateur.

**Durcissement (fait) :**
- Claim **atomique** des messages + reprise des `running` orphelins ; statut
  `review` quand l'agent n'a pas dit `task_done` ; `stop_reason` honnête
  (`failed` > `busy`/`max_handoffs` > `no_pending`).
- Un seul pilote Chrome : **bail inter-processus** (`lease:browser`) tenu par le
  tour navigateur et par le warmup (qui est reporté si le bi-agent tourne).
- Legacy mono-agent **supprimé** (onboarding/outreach/browse/develop, job
  `onboard` auto) ; `connect-next` passe par le superviseur.
- Directives permanentes (`control/directives.md`) **injectées** dans chaque tour.
- Mémoire morte supprimée ; plafond de sortie Stirrup gardé haut (32k) ;
  environnement filtré pour `browser-harness` ; lectures du dépôt encadrées.
- Sessions navigateur : **200 tours** max ; à **75 tours** (puis tous les 50) un
  **tip anti-acharnement** est injecté dans le contexte : l'agent peut écrire son
  problème dans ses **output tokens** (bilan final) — le Master (l'humain ou une
  autre IA) le lira et corrigera ; timeouts alignés (job heartbeat 2 h, bail
  navigateur 3 h, reprise des messages 3 h).

**Reste :**
- **Canal opérateur** : désactivé pour l'instant (l'opérateur réfléchit à une
  nouvelle stratégie). L'ancien design « notification Telegram des messages →
  `operator` » est stationné ; les anciens messages #2/#8 sont archivés.
- Éventuellement : d'autres sources de skills, et l'enrichissement du vocabulaire
  de routage (`pick_agent`).

## 5. Conventions & garde-fous à respecter

- **LLM** : Zen exige `User-Agent` propre + `x-opencode-session` (cache).
  Stirrup exige un plafond de sortie : il reste **haut**
  (`agents.max_tokens`, 32k) pour ne jamais tronquer le raisonnement.
- **Vision** : `deepseek-v4.1-flash` a la vision native — les captures sont
  envoyées à l'agent navigateur (`config.agents.force_vision`).
- **Vault** pour tous les secrets (`github_token`, clés API, logins).
- **Token GitHub** fine-grained : `Contents` RW + `Pull requests` RW, un seul
  repo, pas d'Admin. Branches `agent/*`, PR, jamais de force-push/rm.
- **Écritures atomiques** `.tmp → os.replace`.
- **Un seul pilote Chrome à la fois** ; agents sourds aux secrets en clair.
- Le mode « chauffe » (warmup) plafonne les actions outbound les premiers jours.

## 6. Cartographie rapide

- `src/mnemosyne/heartbeat/` — superviseur (jobs durables) ; y ajouter le job agent.
- `src/mnemosyne/dev/` — agent codeur + garde-fous + git.
- `src/mnemosyne/agents/browser_agent.py` — agent navigateur (browser-harness).
- `src/mnemosyne/agents/warmup.py` / `warmup_schedule.py` — warmup.
- `src/mnemosyne/discovery/` — découverte de fournisseurs (P3).
- `src/mnemosyne/sources/iiif.py` — connecteur IIIF générique (P4).
- `src/mnemosyne/identity.py` — transparence (phrase + repo) pour mails/formulaires.
- `src/mnemosyne/vault/` — coffre chiffré.
- `docs/RUNBOOK.md`, `AGENTS.md` — exploitation et règles.
