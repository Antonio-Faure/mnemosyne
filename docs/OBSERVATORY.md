# Observatoire (backend + frontend, lecture seule)

Poste de contrôle **local** de mnemosyne : on voit les sessions en direct, et on
rejoue celles qui sont finies. **Aucune action n'est possible depuis l'UI** :
l'observatoire lit la base et relaie les événements, il ne pilote pas les agents
et ne lance aucune session.

## Le modèle de session

Une **session** = une unité de travail de premier niveau, visible dans la
panneau des sessions :

1. une **tâche de la file** (`tasks`) — rodage, intégration, mission… ;
2. **une exécution de job système** (`jobs`) — agency, verify, discover,
   warmup, journal, watchdog. `job:<id>` = une exécution (la ligne de job est
   unique par exécution).

À l'intérieur d'une session, les **activations d'agents sont des événements**,
pas des sessions : une passation navigateur → codeur, une reprise après crash, etc.
restent dans la même session. Le panneau des sessions ne liste donc **jamais** les passations.

Les sessions sont **des points de navigation sur la chronologie globale** : elles
se suivent chronologiquement (boutons « Précédente / Suivante »), et la relecture
déroule la chronologie interne de la session sélectionnée.

Les exécutions **`agency`** et **`warmup`** du planificateur sont des **enveloppes** :
leur trace réelle est la session `task` (activation, outils, transcript). Elles
restent donc **silencieuses par défaut** (visibles via « inclure les exécutions
silencieuses ») : le panneau des sessions montre une session par vraie mission, pas trois.
Les jobs système **sans activité** (verify OK, watchdog)
restent aussi silencieux ; seules les exécutions qui produisent quelque chose
(« verify … → OK », source dégradée) apparaissent.

## L'écran

- **Gauche** : sessions groupées par jour, colorées par type, **dockées à
  partir de 980 px** et en **tiroir** en dessous. Lignes compactes : titre sur
  deux lignes, heure · durée · événements, état. Filtres Tout / Tâches /
  Jobs, et bascule des exécutions silencieuses. Les enveloppes `agency`/`warmup` et
  les jobs vides restent silencieux.
- **Centre** : graphe — **Moteur de file** (le moteur de la file, toujours
  affiché au-dessus, et **étape d'ouverture** : c'est lui qui met la mission
  en file), **Superviseur**, Navigateur, **Boîte aux lettres**,
  Codeur (+ nœud **Job système** pour les sessions système hors Moteur de file). Le flux d'une
  tâche est **Moteur de file (session ouverte / mission en file) → Superviseur
  (statut) → Navigateur (Mission, 1re étape de l'agent)**. **Un seul nœud
  tourne à la fois** : celui qui possède l'événement courant (Navigateur quand
  il travaille, Superviseur sur ses statuts, etc.). Les étapes de
  **transmission** allument en plus un lien, avec une **bille** qui circule
  dans le tuyau et **un seul lien à la fois** : mission (superviseur →
  agent), fin d'activation (agent → superviseur, bille remontante), statuts
  (selon `pending→running` / statut final). La boîte aux lettres n'allume que les
  segments réellement traversés. Pas de panneau LLM flottant sur le canvas.
  Le graphe est **cadré automatiquement** (ouverture, repli du panneau,
  redimensionnement) pour qu'aucun nœud ni lien ne reste hors champ ; les
  tailles de nœuds et les handles ont un fallback avant mesure DOM.
- **Droite** : panneau de l'étape **docké/flottant à partir de 1500 px**,
  **tiroir** en dessous (le canvas garde toute sa largeur). Il montre
  **uniquement l'étape en cours** (pas d'onglets) : il suit l'événement de la
  chronologie (Moteur de file, Résolveur, Superviseur, Navigateur, Boîte aux lettres, Codeur, Job système). **Un seul bloc est actif**
  (contour tournant) : celui de l'événement courant. Les événements sont rendus
  comme un **transcript lisible** : bloc *Session ouverte / mission en file*
  (titre de la mission), bloc *Mission* (objectif complet), messages
  *Navigateur/Codeur* (markdown), cartes *Outil* (arguments rendus en champs
  structurés — code, url… — jamais en JSON brut) et *Résultat* (JSON structuré
  quand il est valide, sinon texte ; un JSON brut reste **replié par défaut**),
  *Message* (boîte aux lettres), *Fin d'activation* (tours, durée, bilan), *Statut*
  (le superviseur ferme la tâche **après** la fin d'activation), puis
  *Retour au superviseur* (`done · retour browser` — pendant de *Session
  ouverte*). Les captures d'écran référencées par un outil sont
  copiées dans `data/obs-artifacts/` et affichées en vignette (clic = plein
  écran). Les appels navigateur sont **traduits en actions** (aller à l'URL,
  attendre, remplir un champ, boucle `for`, `scroll`, onglets, JavaScript
  résumé par intention…), avec le code source replié. Les sorties sont
  **rendues**, pas dumpées : les dicts Python de `page_info()` deviennent une
  carte page (titre, URL, fenêtre, scroll, hauteur de page), les listes
  deviennent des pastilles/lignes compactes, les dicts des champs étiquetés,
  les erreurs un résumé + trace dépliable, et les listes tronquées sont
  récupérées item par item. Les tours sans texte et l'échange `finish` sont
  **retirés de la chronologie** (pas seulement masqués) : une étape = un bloc,
  sans doublons. Chaque bloc est dépliable pour le JSON brut et l'horodatage
  complet (« valeur brute »). Cliquer un nœud épingle une étape ; « suivre »
  revient au mode auto.
- **Bas** : relecture — lecture/pause, pas à pas, navigation. La **molette sur le
  badge de vitesse** règle la vitesse (0,25× → 32×) ; ailleurs elle garde son
  usage natif (scroll des panneaux, zoom/pan du canvas). **1× = temps réel**,
  les délais entre étapes sont calculés depuis leurs horodatages. **Chaque
  étape reste affichée au moins 1 s** : ce plancher s'applique même à 32× et
  même si l'écart réel est plus court (il prime sur le multiplicateur). Le
  **délai de file** (`session.created` → premier statut) est ramené à **1 s** :
  c'est l'attente dans la file, pas le temps de travail. En
  direct le curseur suit (badge DIRECT) ; un déplacement manuel passe en relecture. À
  l'intérieur d'une même seconde, l'ordre logique est rétabli (**fin
  d'activation → statut → retour**), y compris pour les sessions historiques.


## Comment ça marche

- Tables `sessions` / `events` dans la même base SQLite (WAL). Chaque événement
  porte `session_id`, `ts`, `kind`, `actor`, `payload` JSON.
- Émission **best-effort** (une panne d'observatoire ne casse jamais le
  travail) depuis :
  - `db.enqueue_task` / `db.set_task_status` (cycle de vie des tâches) ;
  - le superviseur (`activation.start` / `activation.end` : objectif, nombre de
    messages, cap de tours, branche, durée, bilan, erreur) ;
  - la boîte aux lettres (`mailbox.message` : expéditeur, destinataire, corps complet) ;
  - le proxy LLM de stirrup (`llm.call` : modèle, messages, tokens, cache,
    outils, extrait de réponse ; `tool.call` : nom + arguments ; `tool.result` :
    sortie de l'outil, dédupliquée) ;
  - le scheduler (`job.start` / `job.end` : payload du job, durée, mises à jour ;
    `_activity` devient le titre de la session, les exécutions sans activité restent
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
tâches, mais il ne produit qu'une chronologie **minimale** (création + changements
de statut) : à n'utiliser que si l'on veut l'historique de la file sans détails.

## Limites assumées (v1)

- Lecture seule (pas de « annuler », « répondre » ou « relancer »).
- Le panneau droit montre **l'étape en cours** ; il n'y a plus de vue « tout le
  flux » (c'est le prix de la lisibilité demandée).
- Les captures d'écran sont copiées dans `data/obs-artifacts/` (volume partagé)
  et servies par `/api/obs/artifacts/<fichier>` ; elles ne sont pas purgées
  automatiquement. Une capture n'est disponible que si le fichier existait au
  moment du résultat (les anciennes sessions, elles, ont perdu leur `/tmp`).
- L'historique d'avant le 5/11/2026 n'a pas d'événements fins.
