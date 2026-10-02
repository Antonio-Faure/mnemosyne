# Nettoyage bi-agent — chien de garde, patinage, purge, plafond

> Série de commits du 2026-10-02 (a57c1d1 → cf0c204). Objectif : aligner le
> code sur la vision bi-agentique et éliminer le slop, en quatre chantiers
> éprouvés par la suite de tests (170) et la batterie.

## 1. Plus aucun plafond de temps sur les agents (a57c1d1)

`Heartbeat._run_job` enveloppait TOUS les handlers dans
`wait_for(job_timeout_s=4h)` : une mission d'agent longue mais qui avance
était coupée à 4 h — exactement le défaut que la vision interdit
(« aucun plafond de temps », déjà raté une fois avec le 45 min).

- **`kind=agency` : jamais cancellable par un timer.** Une mission est jugée
  sur le marqueur de patinage (`stall:<agent>`, écrit par l'agent lui-même),
  pas sur l'horloge.
- **Jobs mécaniques** (verify/harvest/discover/warmup/watchdog/journal) : le
  `wait_for` reste, car il protège la **vivacité de la boucle** — un handler
  mécanique hangé gèlerait `_tick` pour toujours (plus de watchdog, plus
  d'agency, plus de récupération de messages). Ce n'est pas une limite de
  mission, c'est un disjoncteur.
- Test : une mission agency qui dépasse le timeout finit DONE ; un job
  mécanique hangé est cancellé et replanifié.

## 2. Chien de garde honnête (c34560a)

- monitor.py ne tape plus `db._conn` : lectures via l'API `Database`
  (`running_messages`, `pending_messages`, `running_jobs`,
  `review_message_count`, `lease_exists`, `lease_holder_dead_pid`) — le SQL
  vit une fois, dans db.py.
- **Une seule définition de « processus disparu »** : le watchdog utilise la
  même vérification d'incarnation (`_holder_is_gone`, host étranger / pid mort
  / pid recyclé) que la récupération de bail — plus de fausse alerte sur un
  pid recyclé (l'ancien `os.kill(pid, 0)` du watchdog se trompait).
- Un job **agency** running depuis 60 min n'alerte PAS (jugé au patinage) ; un
  job mécanique si.
- `handle_watchdog` retourne `None` : le log est le contrat — la base ne
  grossit plus d'un payload ré-enregistré toutes les 5 min sans lecteur.
- `clear_stall` fait un vrai DELETE (plus de lignes `stall:* = "null"`).
- Code mort sorti : `_iso_minus`, commentaire « 3 min » aligné sur la
  constante (2 min), ligne de test morte.

## 3. Un seul détecteur de patinage (b3a66ac)

Le navigateur avait une copie manuelle (`_watched`) qui ne surveillait que
3 outils sur 7 — l'agent pouvait patiner sans être vu.

- `watch_provider` (la version complète du codeur) est appliqué **une fois** au
  provider entier dans `run_browser_agent` : les 7 outils passent tous,
  `send_message` inclus (action distincte légitime).
- La copie manuelle est supprimée : une seule implémentation du cerveau.
- Une seule connexion DB par tour : le provider réutilise `mailbox.db`
  (fermée par le superviseur), le codeur ferme sa watch_db en `finally`.
- Logger via `mnemosyne.logger` (progress), cohérent avec le projet.
- Test : les 7 outils enregistrent tous un progrès via l'entonnoir.

## 4. Purge du mort et de la duplication (2ae5f87)

- `DoneParam` (dev) + `DoneParams` (browser) : reliques du `task_done` maison,
  battu par le `finish` natif stirrup (concurrence tranchée — le natif gagne).
- `DevOutcome` + `AgentOutcome` fusionnées en une seule dataclass (`turns` en
  champ direct, compatible `_turns_of`).
- `Mailbox.next_for/claim_for/pending_count`, `Database.claim_next_message`,
  `archive_pending_messages` : vivants seulement par les tests — supprimés,
  tests réécrits sur les chemins réels (`claim_all_for`/`claim_messages`).
- kv `warmup_last` : écrit, jamais lu — sorti.
- La fenêtre stale des messages (18000 = 5 h) vit une seule fois :
  `Database.STALE_MESSAGE_S`. Le TTL du bail navigateur reste sa constante
  dédiée (concept différent : TTL d'un bail ≠ fenêtre de reprise).

## Impact

- **-~250 lignes** de code mort/dupliqué, une seule définition pour chaque
  invariant (« processus disparu », « fenêtre stale », « détecteur de
  patinage »).
- Le chien de garde ne dit plus « ça dure » mais « ça patine, avec la cause » —
  et une mission qui avance, quelle que soit sa durée, ne déclenche rien.
- La vision deepseek est rebranchée de bout en bout (détail dans
  VISION-DEEPSEEK.md) avec sa sonde batterie.
