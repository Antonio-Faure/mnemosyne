# Canal opérateur — questions des agents via Telegram

> Validé le 2026-10-04 ; `ask_operator` est devenu **synchrone** : l'agent
> attend ta réponse et la reçoit dans le même tour. Le canal vit dans la
> **boîte de la tâche**, jamais dans la file.

## Quand déranger l'opérateur (politique)

L'opérateur humain **n'est pas un valideur de routine**. Il a 24 h dans une
journée ; chaque sollicitation doit être justifiée.

**Déclencheurs légitimes :**

1. **doute réel sur la marche à suivre** — pas sur l'exécution d'une action
   déjà prévue et encadrée par un document ;
2. un **humain demande un contact humain** (institution, correspondant,
   demande d'appel ou de visio) ;
3. **décision de politique** : licence restrictive, argent/paiement, éthique,
   données personnelles, accès non public ;
4. **blocage humain** : captcha, vérification SMS/identité, signature,
   appel téléphonique.

**Jamais pour :** envoyer un e-mail conforme à `docs/OUTREACH.md`, créer ou
annuler une tâche, ouvrir une PR, lancer un test, choisir une source,
réessayer une requête, demander une clé ou un compte (c'est le travail du
navigateur), ou faire valider une action de routine.

**Règle d'arbitrage :** en cas d'hésitation entre agir et demander, agis
conformément aux règles écrites. Ne demande que si l'action est **irréversible
ET sort du cadre écrit**.

## Le principe

- **Un troisième correspondant** dans la boîte : `operator`. Les agents
  écrivent `agent → operator` (une question), l'opérateur répond
  `operator → agent`. La question vit et meurt avec la tâche.
- **`ask_operator` est synchrone** : l'agent appelle le tool, **attend la
  réponse dans le même tour**, et reçoit le libellé choisi. La tâche reste
  `running` ; l'activation est bloquée sur le tool, mais la file et le canal
  Telegram ne le sont pas — les autres workers continuent.
- **La réponse est rendue au tool** : le listener Telegram (long poll permanent)
  écrit la réponse dans `operator_asks` et la boîte ; le tool la consomme et
  marque le message comme traité, pour que le superviseur ne la réinjecte pas
  au tick suivant.
- **Aucune expiration** : le tool attend jusqu'à la réponse. Une question sans
  réponse garde un worker et la place dans la file « une question à la fois » ;
  il faut répondre (Telegram ou `mnemosyne answer`) ou annuler la tâche.

## Ordonnancement

1. La tâche travaillée le plus récemment continue (sa session est chaude).
2. Sinon, les tâches qui ont une **réponse/agent-message en attente**
   (reprise après crash, ancien mode asynchrone) reprennent, la plus ancienne
   d'abord.
3. Sinon, la plus ancienne tâche **nouvelle** (FIFO).
4. Une activation bloquée sur `ask_operator` occupe un worker mais pas le
   canal : les autres tâches avancent. Les éventuelles tâches garées par
   l'ancien mode asynchrone restent sautées.

## Telegram : trois bots, une question à la fois

- **Un bot par agent** (`coder`, `browser`, `resolver`) : tu sais toujours qui
  parle, et les agents ne peuvent pas te poser une question en même temps.
- **Une seule question à la fois** : la file d'attente est globale. Tant que la
  question envoyée n'a pas de réponse, aucune autre n'est expédiée — quel que
  soit l'agent ou la tâche. Dès que tu réponds, la suivante part.
- La question part avec des **boutons inline** (2 à 6 options) + un bouton
  **✏️ Autre réponse** (tu réponds au message, texte libre, max 500 caractères).
- Seul **ton chat** est écouté ; tout autre expéditeur est ignoré.
- Après ta réponse, le message Telegram est édité pour montrer le choix. Un
  bouton ancien reste utilisable : l'acquittement du clic peut expirer, la
  carte est éditée quand même (et un message de confirmation est posté si
  l'édition échoue).

## Pourquoi un long poll (et pas un job toutes les 30 s)

Le bridge suit l'architecture du gateway Hermes : un **processus persistant**
qui long-poll `getUpdates` par bot, au lieu d'un job périodique. Telegram garde
la requête jusqu'à 25 s et la rend dès qu'un clic ou un message arrive :
l'acquittement et l'édition de la carte partent dans la seconde, et la réponse
réveille la tâche immédiatement. Chaque bot a sa boucle indépendante ; une
erreur réseau fait un backoff puis reprend, sans bloquer les autres bots.
- Un seul lecteur d'updates : le conteneur (Telegram n'autorise qu'un lecteur
  par bot).

## Quand les agents ont le droit de demander

Uniquement ce qu'**aucun agent** ne peut faire :

- vérification humaine : captcha, SMS, pièce d'identité ;
- décision de politique : activer une source à licence restrictive ;
- action impossible autrement.

**Jamais** pour obtenir une clé/un compte (c'est le travail du navigateur via
`send_message`), ni pour un choix technique, ni pour du confort. **Jamais
d'abonnement payant, jamais de paiement** : si un accès exige de payer,
l'agent abandonne et le dit dans son `finish`. Jamais de secret dans une
question.

## Mise en place (une fois)

1. **Créer trois bots** chez [@BotFather](https://t.me/BotFather) :
   `/newbot` → ex. `mnemosyne_coder_bot`, `mnemosyne_browser_bot` et
   `mnemosyne_resolver_bot`.
2. **Déposer les tokens dans `.env`** (l'environnement est prioritaire) :
   ```bash
   MNEMOSYNE_CODER_BOT_TOKEN=<token coder>
   MNEMOSYNE_BROWSER_BOT_TOKEN=<token browser>
   MNEMOSYNE_RESOLVER_BOT_TOKEN=<token resolver>
   ```
   Variante vault :
   ```bash
   mnemosyne vault set mnemosyne_coder_bot_token <token coder>
   mnemosyne vault set mnemosyne_browser_bot_token <token browser>
   mnemosyne vault set mnemosyne_resolver_bot_token <token resolver>
   ```
3. **Ouvrir chaque bot et appuyer sur /start** (un bot ne peut pas écrire le
   premier). Ton chat id est le même que pour les alertes
   (`MNEMOSYNE_TELEGRAM_CHAT_ID`) ; `mnemosyne telegram updates` l'affiche.
4. **Renseigner les chat ids dans `.env`** :
   ```bash
   MNEMOSYNE_CODER_CHAT_ID=<ton id>
   MNEMOSYNE_BROWSER_CHAT_ID=<ton id>
   MNEMOSYNE_RESOLVER_CHAT_ID=<ton id>
   ```
   puis **activer le canal** dans `config/config.yaml` :
   ```yaml
   operator:
     enabled: true
     coder:    { bot_token_env: MNEMOSYNE_CODER_BOT_TOKEN,    chat_id_env: MNEMOSYNE_CODER_CHAT_ID }
     browser:  { bot_token_env: MNEMOSYNE_BROWSER_BOT_TOKEN,  chat_id_env: MNEMOSYNE_BROWSER_CHAT_ID }
     resolver: { bot_token_env: MNEMOSYNE_RESOLVER_BOT_TOKEN, chat_id_env: MNEMOSYNE_RESOLVER_CHAT_ID }
   ```
   (`chat_id` direct reste possible et prioritaire sur l'environnement.)
5. Redémarrer le conteneur (`docker compose up -d`). Le listener démarre avec
   le heartbeat : long poll permanent des trois bots, sans job périodique.

## Commandes

```bash
mnemosyne queue list                 # les tâches garées montrent « ⏳ attend ta réponse »
mnemosyne answer <task_id> "texte"   # répondre sans Telegram (fallback CLI)
```

Le chien de garde alerte si une question attend depuis plus de 2 h.

## Où c'est dans le code

- `src/mnemosyne/operator/telegram.py` — rendu des questions, **listener long
  poll** (`listen_forever`, un `getUpdates` par bot), routage des réponses
  (`handle_update` est testable sans réseau).
- `src/mnemosyne/operator/models.py` — schéma de l'outil (`question`,
  2-6 `options` label+description).
- `src/mnemosyne/db.py` — table `operator_asks` + `next_task()` (tâches
  garées sautées, reprise prioritaire).
- `src/mnemosyne/agents/mailbox.py` — `operator` comme correspondant.
- `src/mnemosyne/agents/supervisor.py` — injection de la réponse
  (`--- réponse de l'opérateur ---`), destinataires filtrés aux agents.
- `dev/tools.py` + `agents/browser_agent.py` — l'outil `ask_operator`.
- `agents/coder.md` / `agents/browser.md` / `agents/resolver.md` — les règles
  de questionnement.
- `src/mnemosyne/heartbeat/scheduler.py` — démarrage du listener et réveil
  immédiat de la tâche répondue.
- `src/mnemosyne/heartbeat/jobs.py` — ancien job `telegram`, désormais no-op
  (drainage d'un job en file lors d'une mise à jour).
- `src/mnemosyne/monitor.py` — alerte « attend une réponse » (> 2 h).
