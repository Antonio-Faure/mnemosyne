# La file de tâches : une tâche = une conversation

> Le modèle qui remplace la boîte à messages globale (décision du 2026-10-02).
> Deux couches, deux règles : la **file** est manipulable, la **boîte** ne
> l'est pas.

## Les deux couches

| | File d'attente (`tasks`) | Boîte de messages (`messages`) |
|---|---|---|
| Qui y touche | l'opérateur (`mnemosyne queue add/list/cancel`) | les agents seuls, dans leur tâche |
| Durée de vie | jusqu'à ce que la tâche meure | **temporaire** : née avec la tâche, jetée avec elle |
| Contenu | départ (agent) + objectif + cap de tours | les allers-retours du ping-pong |
| Mélanges | interdits : un objectif = une tâche | un seul sujet par tâche, donc jamais de mélange |

Un message sans tâche **n'existe pas** — `Mailbox.post(..., task_id=None)`
lève. Operator et warmup postent des **tâches**, jamais des messages.

## Le cycle de vie d'une tâche

```
queue add (départ, objectif, cap?)
   │
   ▼
pending ── tick agency ──► running ── activation session départ
                                │
        l'agent écrit à l'autre? │
        ├─ non ─► finish ─► boîte vide ─► DONE (note = bilan)
        └─ oui ─► boîte non vide ─► l'autre agent s'active (session 2)
                    │
                    ▼ ping-pong illimité
             chaque réponse est injectée dans la session EXISTANTE
             de l'agent (cache stirrup, resume=True) — aucun hop ne
             crée de session ; chaque agent garde tout son contexte
                    │
                    ▼
             une activation finit + boîte vide ─► DONE (ou REVIEW sans finish)
             erreur d'activation ─► FAILED (note = l'erreur)
             les caches des 2 sessions + la boîte sont jetés avec la tâche
```

- **1 session** si l'agent de départ n'écrit jamais à l'autre ; **2 sessions**
  (une par agent) dès que le ping-pong commence ; plus de deux uniquement via
  la **compaction** native de stirrup (`context_summarization_cutoff`).

## Ce que l'autre agent hérite (la règle d'héritage)

Quand la première tête écrit à l'autre, l'agent récepteur reçoit **trois
étages**, jamais moins :

1. **L'objectif ORIGINAL**, tel qu'écrit à la création de la tâche (le texte
   de tâche est figé — jamais de jeu de téléphone, chaque tête le voit verbatim) ;
2. **Le(s) message(s)** de la première tête — le *quoi maintenant*, avec sa
   contextualisation (ce qu'il a fait, ce qui manque, sous quelle forme) ;
3. **Les directives permanentes** de l'opérateur (injectées à chaque
   activation, à côté du texte figé).

Conséquence voulue : si la demande du premier agent contredit l'objectif,
l'agent récepteur **voit la contradiction** (l'objectif est le plancher) et
peut la signaler en retour — le ping-pong illimité rend cette correction
possible. Et aucun hop ne dégrade le contexte : la partie d'un agent est
mise en cache, la réponse de l'autre arrive par-dessus (preuve réelle :
tâche #12 — le codeur, à sa 2e activation, a cité sa demande initiale de
mémoire).

Limite assumée : l'agent récepteur ne voit pas l'historique d'outils de
l'autre tête, seulement son message — les prompts exigent des messages
factuels complets, et le ping-pong permet de demander la précision.
- **Aucune limite de ping-pong** (le `max_handoffs` est mort partout) : le
  contexte persistant fait que chaque agent sait où il en est, et la file est
  le garde-fou (`queue cancel` à tout moment).
- **Crash à tout moment = reprise parfaite** : la tâche reste `running`, le
  cache des sessions est sur le volume data, le tick suivant **réouvre la
  session de départ** — l'agent retrouve exactement où il en était.

## Les sessions persistantes (stirrup cache)

- `session(resume=True, clear_cache_on_success=False)` : l'historique complet
  de la session est sauvé à chaque fin d'activation et restauré à la suivante.
- La clé de cache est dérivée du **texte de tâche figé**
  (`session_task_text` : `[tâche #N — agent X] + objectif`) — le texte ne
  change JAMAIS entre les activations ; les réponses entrantes sont injectées
  dans l'historique en cache (`inject_reply`), pas dans le texte.
- Le cache vit dans `data/stirrup-cache/` (volume) → il survit aux rebuilds.
- À la fermeture de la tâche : les deux caches de session sont supprimés
  (`drop_session_cache`) — la boîte temporaire et les sessions meurent ensemble.

## Le cycle automatique (warmup ↔ connexion)

Le job `warmup` du heartbeat ne poste plus de messages : il poste des **tâches**
en alternance (`mission_cycle` en kv) :

1. **cycle pair** → une tâche `MISSION WARMUP` (lecture seule, sites pondérés,
   cap `warmup_max_turns`) ;
2. **cycle impair** → une tâche `MISSION CONNEXION DE SOURCE` si un candidat
   existe (source avec auth, sans clé au vault, sans tâche ouverte) ; sinon
   fallback warmup.

Le quota quotidien (1–2/jour) s'applique aux jambes warmup ; les connexions
n'en consomment pas (c'est du travail, pas de la chauffe). La connexion
demande explicitement : compte archivist, clé récupérée → `remember(...)`,
message au codeur pour brancher le connecteur.

## Ce qui a disparu avec l'ancien modèle

- La boîte globale et ses batches de ≤5 messages mélangés.
- Le protocole in-band `[[tour: N]]` (regex dans le corps du message) — le cap
  est un champ de la tâche.
- `max_handoffs` (le budget de handoffs) — ping-pong illimité.
- Le claim atomique des messages + `recover_stale_messages` : le verrou est
  désormais la tâche (`running`) et les leases ; une activation crashée se
  REPREND (session resume), elle ne libère pas des messages.
- Les messages "operator→agent" : l'opérateur écrit dans la file.

## Les commandes

```bash
mnemosyne queue add "objectif de la tâche" [--agent coder|browser] [--cap N]
mnemosyne queue list [--status pending|running|done|failed|review]
mnemosyne queue cancel <id>
mnemosyne agency "<tâche>" [--to ...]     # enqueue + drain interactif
mnemosyne messages                        # historique (audit)
```

La file est vidée par le job `agency` du heartbeat (une activation ~toutes les
2 min) ; `queue add` ne bloque jamais.
