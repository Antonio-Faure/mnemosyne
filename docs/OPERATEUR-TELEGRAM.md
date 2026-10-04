# Canal opérateur — questions des agents via Telegram

> Validé le 2026-10-04. Les agents posent des **questions à choix** à
> l'opérateur (toi) ; la tâche se gare, ta réponse la réveille. Le canal vit
> dans la **boîte de la tâche**, jamais dans la file.

## Le principe

- **Un troisième correspondant** dans la boîte : `operator`. Les agents
  écrivent `agent → operator` (une question), l'opérateur répond
  `operator → agent`. La question vit et meurt avec la tâche.
- **« Attendre » n'est jamais bloquant** : l'agent pose sa question puis
  **arrête son tour**. La tâche reste `running` mais **garée** — le superviseur
  la saute, elle ne coûte rien et ne bloque pas la file.
- **La réponse réveille la tâche** : elle atterrit dans la boîte, le tick
  suivant (~2 min) réactive l'agent **avec tout son contexte** (session
  persistante), exactement où il s'était arrêté.

## Ordonnancement (les tâches garées libèrent la place)

1. La tâche travaillée le plus récemment continue (sa session est chaude).
2. Sinon, les tâches qui ont une **réponse/agent-message en attente**
   (réponse de l'opérateur, reprise après crash) reprennent, la plus ancienne
   d'abord.
3. Sinon, la plus ancienne tâche **nouvelle** (FIFO).
4. Les tâches garées (question sans réponse) sont **sautées** — ta réponse ne
   coupe jamais une tâche en cours : elle fait passer la tâche concernée en
   tête de la prochaine place libre.

## Telegram : deux bots, des boutons

- **Un bot par agent** (`coder`, `browser`) : tu sais toujours qui parle.
- La question part avec des **boutons inline** (2 à 6 options) + un bouton
  **✏️ Autre réponse** (tu réponds au message, texte libre, max 500 caractères).
- Seul **ton chat** est écouté ; tout autre expéditeur est ignoré.
- Après ta réponse, le message Telegram est édité pour montrer le choix.
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

1. **Créer deux bots** chez [@BotFather](https://t.me/BotFather) :
   `/newbot` → ex. `mnemosyne_coder_bot` et `mnemosyne_browser_bot`.
2. **Déposer les tokens au vault** :
   ```bash
   mnemosyne vault set mnemosyne_coder_bot_token <token coder>
   mnemosyne vault set mnemosyne_browser_bot_token <token browser>
   ```
3. **Ouvrir chaque bot et appuyer sur /start** (un bot ne peut pas écrire le
   premier). Récupérer ton chat id : `mnemosyne telegram updates`.
4. **Renseigner `config/config.yaml`** :
   ```yaml
   operator:
     enabled: true
     coder:   { bot_token_env: MNEMOSYNE_CODER_BOT_TOKEN,   chat_id: "123456789" }
     browser: { bot_token_env: MNEMOSYNE_BROWSER_BOT_TOKEN, chat_id: "123456789" }
   ```
5. Redémarrer le conteneur (`docker compose up -d`) — le job `telegram`
   (toutes les 30 s) apparaît dans le heartbeat.

## Commandes

```bash
mnemosyne queue list                 # les tâches garées montrent « ⏳ attend ta réponse »
mnemosyne answer <task_id> "texte"   # répondre sans Telegram (fallback CLI)
```

Le chien de garde alerte si une question attend depuis plus de 2 h.

## Où c'est dans le code

- `src/mnemosyne/operator/telegram.py` — rendu des questions, polling,
  routage des réponses (`handle_update` est testable sans réseau).
- `src/mnemosyne/operator/models.py` — schéma de l'outil (`question`,
  2-6 `options` label+description).
- `src/mnemosyne/db.py` — table `operator_asks` + `next_task()` (tâches
  garées sautées, reprise prioritaire).
- `src/mnemosyne/agents/mailbox.py` — `operator` comme correspondant.
- `src/mnemosyne/agents/supervisor.py` — injection de la réponse
  (`--- réponse de l'opérateur ---`), destinataires filtrés aux agents.
- `dev/tools.py` + `agents/browser_agent.py` — l'outil `ask_operator`.
- `agents/coder.md` / `agents/browser.md` — les règles de questionnement.
- `src/mnemosyne/heartbeat/jobs.py` — job `telegram` (30 s).
- `src/mnemosyne/monitor.py` — alerte « attend une réponse » (> 2 h).
