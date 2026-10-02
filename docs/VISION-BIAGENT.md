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

### 2.3 Communication : la file de tâches et la boîte temporaire

- **Deux couches séparées** :
  - **La file d'attente des tâches** (table `tasks`) est la couche
    *manipulable* : l'opérateur y ajoute, y voit, y annule
    (`mnemosyne queue add|list|cancel`). Chaque tâche = **qui commence**
    (l'agent qui reçoit le premier message) + **l'objectif** (+ cap de tours
    optionnel). Une tâche = **un objectif** : warmup et connexion de source
    sont DEUX entrées de file, jamais mélangées.
  - **La boîte de messages** est la couche *interne* : **temporaire**, propre
    à une tâche, intouchable par l'opérateur, jetée à la fin de la tâche. Un
    message sans tâche n'existe pas.
- **Sessions persistantes** : chaque tâche ouvre au plus **une session par
  agent**. Si l'agent de départ n'écrit pas à l'autre → 1 session ; s'il écrit
  → la session de l'autre agent s'ouvre (2 sessions). **Le ping-pong est
  illimité** : chaque réponse est injectée dans la session EXISTANTE de
  l'agent concerné (cache stirrup, `resume=True`,
  `clear_cache_on_success=False`, sur le volume data) — chaque agent garde le
  contexte complet de sa partie de la tâche. Plus de deux sessions :
  uniquement la compaction native de stirrup (`context_summarization_cutoff`).
- **Fin de tâche** : une activation se termine ET la boîte de la tâche est
  vide → la tâche se ferme (`done` si `finish` avec bilan, `review` sans
  `finish`, `failed` sur erreur). Les caches des deux sessions et la boîte
  sont jetés avec la tâche.
- **Crash** : la reprise est parfaite à tout moment — la tâche reste
  `running`, le tick suivant **réouvre la session** de départ (cache stirrup),
  sans perdre le travail déjà fait.
- **Superviseur déterministe** (le heartbeat, PAS un LLM) : il draine la file,
  UNE activation à la fois, séquentiellement (les deux têtes partagent Chrome
  et le worktree git). Les agents ne se lancent **jamais** eux-mêmes.
- **Secrets via le vault, jamais dans les messages** : l'agent navigateur
  stocke la clé (`remember("europeana_api_key", …)`, réservé aux clés non
  critiques) et envoie une **référence** ; le moteur l'exporte en variable
  d'environnement au démarrage (`docs/CREDENTIALS.md`).
- **Canal opérateur désactivé** (stationné) : l'opérateur écrit dans la FILE
  (`queue add`), pas dans la boîte. Les blocages se terminent par un résumé
  factuel (`finish`) et l'opérateur regarde la file et le journal.
- **Aucune limite de ping-pong** : volontaire — le contexte persistant fait
  que chaque agent sait où il en est ; l'interventionnabilité de la file
  (annuler une tâche) est le garde-fou.
- **Routage au lancement** : selon l'intention, `pick_agent` choisit l'agent
  de départ (heuristique), `--agent` force le choix.

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
- Warmup auto (1–2/jour, sites pondérés) : **une mission « lecture seule » postée au navigateur** (plafonnée en tours), vault, Telegram, journal.

**Bi-agent (fait) :**
1. **File de tâches + boîte temporaire par tâche** : table `tasks` + messages
   rattachés à une tâche (`src/mnemosyne/db.py`) + `mailbox.py` (enveloppe).
2. **Superviseur déterministe** : `src/mnemosyne/agents/supervisor.py`
   (`run_agency` / `drain_queue` / `run_pending_once`) — une activation à la
   fois, sessions persistantes par (tâche, agent), ping-pong illimité.
3. **Fin de session native** : c'est l'outil `finish` de Stirrup qui termine
   une activation (bilan dans `reason`, fichiers touchés dans `paths`). Aucun
   `task_done` maison (l'agent le rappelait dix fois de suite).
4. **`send_message`** dans la boîte de la tâche, côté codeur et côté navigateur.
5. **Agent navigateur** : `src/mnemosyne/agents/browser_agent.py` (Stirrup) —
   outil `browser(code)` qui exécute browser-harness, édition **allowlist
   helpers** (`data/agent-workspace/helpers-worktree/`), `send_message`.
6. **CLI** : `mnemosyne queue add|list|cancel`, `mnemosyne agency "<tâche>"
   [--to coder|browser]`, `mnemosyne messages`.
7. Le **codeur** tourne aussi dans le conteneur (dépôt monté sur `/repo`,
   `MNEMOSYNE_DEV_REPO=/repo`, worktree isolé) → `agency` fait tourner les deux.

**Bi-agent — suite (fait) :**
- **Autonomie heartbeat** : job `agency` (toutes les 2 min, coût nul s'il n'y a
  rien) → `supervisor.run_pending_once()` exécute **une** activation (la tâche
  en cours d'abord, sinon la plus ancienne en file). Vérifié : un crash au
  milieu d'une activation se reprend à la session exacte.
- **Cycle de missions** : le job `warmup` alterne **1 warmup → 1 connexion de
  source** (candidat = source auth sans clé au vault ; sans candidat, fallback
  warmup). Chaque jambe est une tâche distincte de la file.
- **Git des helpers** : l'agent navigateur écrit dans
  `harness/helpers/` via un **worktree git dédié**
  (`data/agent-workspace/helpers-worktree`) et `publish_helpers(summary)`
  commit + push + PR (scopé `harness/helpers/` uniquement).
- **Skills du harness** : vendored dans `harness/skills/*.md` (extraits de
  `browser-use/browser-harness`, MIT) et injectés dans le prompt de l'agent
  navigateur.

**Durcissement (fait) :**
- Une seule tâche à la fois (`lease:agency` par **activation**) ; la tâche en
  cours d'exécution passe avant les nouvelles (séquentiel, pas de course) ;
  `stop_reason` honnête.
  - Un seul pilote Chrome : **bail inter-processus** (`lease:browser`) tenu par
    les activations navigateur (et reporté si le warmup tourne).
  - Le superviseur est un **sérialiseur**, pas un filtre : le `--to` ne choisit
    que l'agent de départ (les handoffs restent possibles, illimités).
  - Legacy mono-agent **supprimé** (onboarding/outreach/browse/develop, job
    `onboard` auto) ; `connect-next` passe par le superviseur.
  - Cycle de vie d'une découverte : `new` → `connecting` → `connected` /
    `failed`. **`connected` = une branche avec commits existe, pas une source qui
    marche** : le codeur passe au superviseur, l'humain relit la PR. Une PR peut
    donc être fermée après `connected` (exemple réel : `adore_ugent`, Omeka S dont
    `/api` renvoie du HTML et qui n'expose ni `/iiif/3/search` ni manifeste de
    collection — le connecteur générique IIIF ne peut pas y travailler ; il
    faudrait un connecteur dédié `omeka_s`). `failed` = pas de branche, donc
    rejouable ; `new` = jamais tenté.
- Directives permanentes (`control/directives.md`) **injectées** dans chaque
  activation (le texte de tâche est figé, les directives voyagent à côté).
- Mémoire morte supprimée ; plafond de sortie Stirrup gardé haut (32k) ;
  environnement filtré pour `browser-harness` ; lectures du dépôt encadrées.
- Sessions navigateur : **400 tours** max (cap de la tâche) ; le détecteur de
  patinage injecte une note neutre dans la session : l'agent peut écrire son
  problème dans ses **output tokens** (bilan final) — l'opérateur le lira et
  corrigera ; disjoncteur des jobs mécaniques 1 h.
  - **Aucun plafond de temps.** Une mission longue doit aller au bout : on ne
    juge pas sur l'horloge mais sur le **progrès**. J'avais d'abord mis une
    limite de 45 min (l'agent de la vidéo Europeana avait mis 30 min, un tour
    « batterie » 51 min) — c'était une erreur : cela coupait indistinctement le
    travail en cours. Remplacé par `agents/progress.py` (`ProgressWatch`) :
    chaque appel d'outil est horodaté et fingerprinté ; **une action jamais
    vue = progrès**. L'agent n'est pressé que s'il **patine** — aucune action
    distincte depuis `stall_after_s` (15 min) ou `stall_repeat` (6) appels
    identiques d'affilée — et la note dit explicitement « si tu es bloqué, fais
    ton bilan ; si tu avances, continue, tu n'as aucune limite de temps ». Le
    chien de garde alerte (information, pas arrêt) : un job mécanique hangé
    (disonjoncteur 1 h), une tâche ouverte que plus personne ne travaille, un
    bail tenu par un processus disparu.
- **Échanges = relations d'intérêt** : un agent n'écrit à l'autre que s'il a
  besoin de quelque chose ou pour signaler un vrai problème. Pas de rapport
  obligatoire, pas d'accusé de réception — le bilan de fin de tâche est le
  `finish` (note de la tâche), pas un message.

**Reste :**
- Exemple de référence de l'identité : **archivist** = l'archiviste **à deux
  têtes** — le bi-agent ENTIER est le personnage ; `identity.agent_email`
  (`archivist.mnemosyne@gmail.com`) est sa carte d'identité partagée, utilisée
  par la tête navigateur quand elle touche le web. Voir aussi
  `docs/CHOIX-ARCHI-NAVIGATEUR.md`.
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
