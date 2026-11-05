# Observatoire (backend + frontend, lecture seule)

Poste de contrôle **local** de mnemosyne : on voit les sessions en direct, et on
rejoue celles qui sont finies. **Aucune action n'est possible depuis l'UI** :
l'observatoire lit la base et relaie les événements, il ne pilote pas les agents
et ne lance aucune session.

## Le modèle de session

Une **session** = une unité de travail de premier niveau, visible dans la
sidebar :

1. une **tâche de la queue** (`tasks`) — warmup, connexion, mission… ;
2. **un run de job système** (`jobs`) — agency, harvest, verify, discover,
   warmup, journal, watchdog. `job:<id>` = une exécution (la ligne de job est
   unique par run).

À l'intérieur d'une session, les **activations d'agents sont des événements**,
pas des sessions : un handoff browser → codeur, une reprise après crash, etc.
restent dans la même session. La sidebar ne liste donc **jamais** les handoffs.

Les sessions sont **des points de navigation sur la timeline globale** : elles
se suivent chronologiquement (boutons « Précédente / Suivante »), et le replay
déroule la timeline interne de la session sélectionnée.

## L'écran

- **Gauche** : sessions groupées par jour, colorées par type (warmup, connexion,
  connect, browser, coder, harvest, verify, discover, agency…), avec statut,
  durée et nombre d'événements. Filtres « Tout / Tâches / Système » et
  « inclure les runs silencieux ».
- **Centre** : canvas type Make — Orchestrateur, Navigateur, Mailbox, Codeur,
  LLM (+ nœud Job pour les sessions système). Les liens s'allument et s'animent
  quand un message, un appel LLM ou une activation passe.
- **Droite** : l'activité du nœud sélectionné (ou tout le flux) : statuts,
  activations, messages mailbox, appels LLM, outils, tokens, extraits.
- **Bas** : replay — lecture/pause, pas à pas, vitesse 0,5 → 4×, scrubbing. En
  direct le curseur suit (badge LIVE) ; un scrub passe en replay.

## Comment ça marche

- Tables `sessions` / `events` dans la même base SQLite (WAL). Chaque événement
  porte `session_id`, `ts`, `kind`, `actor`, `payload` JSON.
- Émission **best-effort** (une panne d'observatoire ne casse jamais le
  travail) depuis :
  - `db.enqueue_task` / `db.set_task_status` (cycle de vie des tâches) ;
  - le superviseur (`activation.start` / `activation.end`) ;
  - la mailbox (`mailbox.message`, y compris les handoffs browser → codeur) ;
  - le proxy LLM de stirrup (`llm.call`, `tool.call` : tokens, outils, extraits) ;
  - le scheduler (`job.start` / `job.end` ; `_activity` devient le titre de la
    session, les runs sans activité restent silencieux).
- Le frontend consomme `GET /api/obs/sessions`,
  `/api/obs/sessions/{id}/events` et le flux SSE `GET /api/obs/stream`.
  L'API **taille la table** (toutes les 400 ms) : pas de bus inter-process, et
  la reconnexion reprend via `Last-Event-ID`.
- La SPA buildée est servie par FastAPI à `/` (même origine, local only).

## Lancer

```bash
# 1. construire le frontend (Node 20+)
cd web && npm install && npm run build && cd ..

# 2. démarrer le heartbeat + l'API
docker compose up -d --build

# 3. ouvrir
xdg-open http://127.0.0.1:8090
```

En dev : `cd web && npm run dev` (proxy `/api` → `127.0.0.1:8090`) avec
`mnemosyne api` côté backend. Le service compose `observatory` partage l'image
et les volumes du heartbeat ; il ne lit que la base.

## Historique

Les tables d'observatoire sont apparues le 31/10/2026. Pour voir le passé :

```bash
mnemosyne obs-backfill --days 14
```

Il crée une session par tâche et un run par type de job et par jour
(**idempotent** : une session déjà présente n'est jamais dupliquée). Les
sessions antérieures ont une timeline minimale (création + changements de
statut) ; les événements fins (tours, outils, messages) n'existent que pour les
sessions postérieures.

## Limites assumées (v1)

- Lecture seule (pas de « annuler », « répondre » ou « relancer »).
- Pas de captures d'écran du navigateur dans le panneau (les événements texte,
  oui) — les artefacts pourront être exposés ensuite.
- Le backfill ne reconstitue pas les tool calls passés (ils n'étaient pas
  enregistrés).
