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

- **Gauche** : sessions groupées par jour, colorées par type, **repliables**
  (bouton de l'en-tête ou chevron, état mémorisé). Deux warmups distincts :
  **`système`** (run du job planificateur, gris — aucun LLM) et
  **`navigateur`** (la tâche d'agent postée par ce job, turquoise — compte
  Gmail/navigation, coût LLM). Badges `système` / `navigateur` / `codeur`.
- **Centre** : canvas type Make — **Agency** (le moteur de la file, toujours
  affiché au-dessus), Orchestrateur (le superviseur), Navigateur, Mailbox,
  Codeur (+ nœud Job pour les sessions système hors Agency). Les liens actifs
  animent une **bille** qui circule dans le tuyau : **un seul lien à la fois**
  — orchestrateur → destinataire à l'envoi, destinataire → orchestrateur au
  retour (bille remontante). La mailbox n'allume que les segments réellement
  traversés par le message. Pas de panneau LLM flottant sur le canvas : les
  appels/tokens restent des événements de l'étape en cours.
- **Droite** : panneau **flottant** au-dessus du canvas et **repliable**
  (bouton de l'en-tête, état mémorisé). Il montre **uniquement l'étape en
  cours** (pas d'onglets) : il suit l'événement de la timeline (Orchestrateur,
  Navigateur, Codeur, Mailbox, Job). Les événements sont rendus comme un
  **transcript lisible** : bloc *Mission* (objectif complet), messages
  *Navigateur/Codeur* (markdown), cartes *Outil* (arguments rendus en champs
  structurés — code, url… — jamais en JSON brut) et *Résultat* (JSON structuré
  quand il est valide, sinon texte ; un JSON brut reste **replié par défaut**),
  *Message* mailbox, *Fin d'activation* (tours, durée, bilan), puis
  *Retour à l'orchestrateur* (la tâche repasse au superviseur — c'est l'étape
  finale de la timeline). Les captures d'écran référencées par un outil sont
  copiées dans `data/obs-artifacts/` et affichées en vignette (clic = plein
  écran). Les appels navigateur sont **traduits en actions** (aller à l'URL,
  attendre, remplir un champ, boucle `for`, `scroll`, imports…), avec le code
  source replié. Les tours sans texte et l'appel `finish` sont masqués. Chaque
  bloc est dépliable pour le JSON brut et l'horodatage complet. Cliquer un nœud épingle une étape ;
  « suivre » revient au mode auto.
- **Bas** : replay — lecture/pause, pas à pas, vitesse 0,5 → 4×, scrubbing. En
  direct le curseur suit (badge LIVE) ; un scrub passe en replay.


## Comment ça marche

- Tables `sessions` / `events` dans la même base SQLite (WAL). Chaque événement
  porte `session_id`, `ts`, `kind`, `actor`, `payload` JSON.
- Émission **best-effort** (une panne d'observatoire ne casse jamais le
  travail) depuis :
  - `db.enqueue_task` / `db.set_task_status` (cycle de vie des tâches) ;
  - le superviseur (`activation.start` / `activation.end` : objectif, nombre de
    messages, cap de tours, branche, durée, bilan, erreur) ;
  - la mailbox (`mailbox.message` : expéditeur, destinataire, corps complet) ;
  - le proxy LLM de stirrup (`llm.call` : modèle, messages, tokens, cache,
    outils, extrait de réponse ; `tool.call` : nom + arguments ; `tool.result` :
    sortie de l'outil, dédupliquée) ;
  - le scheduler (`job.start` / `job.end` : payload du job, durée, mises à jour ;
    `_activity` devient le titre de la session, les runs sans activité restent
    silencieux).
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

Les tables d'observatoire ont été **remises à zéro le 5/11/2026** : les
sessions antérieures n'avaient pas les détails d'exécution (les événements
structurés n'existaient pas encore). Seules les nouvelles sessions enregistrent
les outils, les tours, les durées et les payloads.

`mnemosyne obs-backfill --days N` existe encore pour réimporter d'anciennes
tâches, mais il ne produit qu'une timeline **minimale** (création + changements
de statut) : à n'utiliser que si l'on veut l'historique « queue » sans détails.

## Limites assumées (v1)

- Lecture seule (pas de « annuler », « répondre » ou « relancer »).
- Le panneau droit montre **l'étape en cours** ; il n'y a plus de vue « tout le
  flux » (c'est le prix de la lisibilité demandée).
- Les captures d'écran sont copiées dans `data/obs-artifacts/` (volume partagé)
  et servies par `/api/obs/artifacts/<fichier>` ; elles ne sont pas purgées
  automatiquement. Une capture n'est disponible que si le fichier existait au
  moment du résultat (les anciennes sessions, elles, ont perdu leur `/tmp`).
- L'historique d'avant le 5/11/2026 n'a pas d'événements fins.
