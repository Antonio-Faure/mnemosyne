# Runbook — lancer, connecter Gmail, surveiller

## 1. Prérequis

- Docker + Docker Compose (pour le mode 24/7), ou Python 3.11+ pour le mode local.
- Ton compte **OpenCode Go** déjà connecté dans opencode (le token est caché dans
  `~/.local/share/opencode/auth.json`, entrée `opencode-go`).
- Un **compte Gmail dédié** à l'agent (à créer par toi, une seule fois).

## 2. Lancer

### Mode Docker (recommandé, tourne 24/7)

```bash
cp .env.example .env          # renseigne au moins MNEMOSYNE_CONTACT et Telegram
docker compose up -d --build
```

Conteneurs :
- `mnemosyne` — heartbeat + API (`http://localhost:8080`).
- `chrome` — Chrome dédié headful (Xvfb), profil persistant.

Le conteneur `mnemosyne` lit aussi le token OpenCode caché (montage lecture seule
de `~/.local/share/opencode` → `/opencode-auth`).

### Mode local (dev)

```bash
make install
.venv/bin/pip install -e '.[browser]'   # P2 : Stirrup + browser-use
.venv/bin/mnemosyne vault init
.venv/bin/mnemosyne run      # heartbeat
.venv/bin/mnemosyne serve    # API (dans un autre terminal)
```

Les agents navigateur (P2) nécessitent un Chrome joignable en CDP : lance
`docker compose up -d chrome` (ou un Chrome local avec `--remote-debugging-port`)
et règle `MNEMOSYNE_CDP_URL`.

## 3. Connecter le Chrome à Google (Gmail + gestionnaire de mots de passe)

Le Chrome du conteneur est exposé en VNC + CDP :

1. Ouvre **http://localhost:6080** (noVNC) dans un navigateur.
2. **Connecte-toi à Chrome** (pas seulement Gmail) avec le **compte Google dédié** :
   icône profil en haut à droite → « Se connecter à Chrome ». C'est cette étape qui
   lie le profil au compte : Chrome gère alors l'**ouverture de session Gmail
   automatique** et le **gestionnaire de mots de passe**.
3. Dans `chrome://settings/passwords`, active « Proposer d'enregistrer les mots de
   passe » et « Connexion automatique ». Chrome pourra ainsi **créer et stocker
   des mots de passe** de façon automatisée côté navigateur.
4. Tu fais tout ça **une seule fois** : le profil persiste dans
   `data/chrome-profile/` (volume monté), et le flag `--password-store=basic` garde
   les mots de passe dans le profil (pas de keyring OS dans le conteneur).

Le heartbeat (P2) réutilise cette session pour lire les codes de vérification et
envoyer les mails de demande d'accès. Le même noVNC sert à résoudre un
captcha/phone-verify à la main quand Telegram t'alerte.

> Le CDP (9222) n'est **pas** exposé à l'hôte : Chrome 154 n'écoute que sur
> `127.0.0.1` dans son conteneur. Le conteneur `mnemosyne` **partage son namespace
> réseau** et joint le CDP en `127.0.0.1:9222` (`MNEMOSYNE_CDP_URL`). Pour
> vérifier : `make cdp`.

### Si Chrome affiche « Chrome n'est pas stable » / « stability and security will suffer »

Ce message venait de `--no-sandbox` (Chrome refusait le sandbox car lancé en root)
et d'arrêts non propres. Corrigé :
- Chrome tourne désormais en **utilisateur non-root `chrome`, sandbox activé** —
  plus de `--no-sandbox`, plus de message d'avertissement ;
- l'infobar déclenchée par `--disable-blink-features=AutomationControlled` (gardé
  pour l'anti-détection) est coupée par `--test-type` ;
- pour cela, le conteneur dédié relâche le **seccomp** de Docker
  (`security_opt: seccomp=unconfined`) : sans ça le sandbox Chrome ne peut pas
  créer ses namespaces. Trade-off assumé : conteneur dédié, sans réseau exposé
  (CDP/nonVNC en loopback), et le sandbox Chrome reste actif ;
- nettoyage des verrous (`Singleton*`, verrou X) et
  `--hide-crash-restore-bubble` / `--disable-session-crashed-bubble` ;
- arrêt SIGTERM propre, `--disable-gpu`, `--disable-dev-shm-usage`.

Pour repartir d'un profil vierge (efface la connexion Google) : `make chrome-reset`,
puis reconnecte via `make vnc`.

## 3bis. Transparence & mémoire

- **Transparence** : tout mail / formulaire inclut une phrase d'identité + l'URL du
  repo, construite depuis `config.identity` (`src/mnemosyne/identity.py`). Exemple :
  « Je suis mnemosyne, un agent logiciel autonome qui développe un projet de
  recherche ouvert… Open source : https://github.com/Antonio-Faure/mnemosyne ».
- **Mémoire bornée** : l'agent ne renvoie jamais tout son historique au modèle
  ($$$). `src/mnemosyne/memory.py` conserve les N derniers messages + un **résumé
  roulant** ; au-delà d'un seuil, les anciens messages sont résumés par le LLM puis
  supprimés de la base (compaction). Réglages dans `config.memory`.
- **Pas de `max_tokens`** : les appels n'imposent pas de plafond de sortie (laisse
  le provider décider), ce qui évite les `content` vides des modèles à
  raisonnement. L'`usage` (tokens) est capturé à chaque appel pour suivre le coût.

## 3quater. Accès depuis ton portable (config actuelle : tout via Tailscale)

Toi = Lenovo Yoga (opencode desktop) connecté au serveur opencode sur `yggdrasil`.
Le « Chrome de l'agent » tourne **sur yggdrasil** ; on le voit via **noVNC**.

Rappel : les commandes serveur (`docker …`, `make …`, `mnemosyne …`) se lancent
**sur yggdrasil** — tu peux simplement **les demander à l'agent** dans opencode.

Pour la fenêtre du navigateur, trois voies (au choix) :

1. **Remote access (le plus simple, déjà utilisé)** : ouvre ton accès distant à
   `yggdrasil`, lance **Firefox sur yggdrasil**, va sur
   `http://127.0.0.1:6080/vnc.html?autoconnect=1`.
2. **Tunnel SSH depuis ton Lenovo** :
   `ssh -L 6080:127.0.0.1:6080 odin@100.110.3.72` puis, sur le Lenovo,
   `http://127.0.0.1:6080/vnc.html?autoconnect=1`.
3. **Tailscale Serve** (URL privée directe, nécessite un `sudo` sur yggdrasil) :
   `sudo tailscale serve --bg 6080` puis ouvre l'URL `https://yggdrasil.<tailnet>.ts.net/`
   depuis ton Lenovo (réseau tailnet uniquement, rien sur le LAN).

Dans la fenêtre Chrome : connexion Chrome → compte Gmail, puis
`chrome://settings/passwords`.

## 3ter. Ne PAS passer par Tailscale

L'agent doit naviguer avec l'**IP résidentielle réelle** de la machine. Tailscale
reste OK pour l'admin (SSH), mais un **exit node** ou l'acceptation de routes
ferait transiter tout le trafic par le tailnet (mauvaise réputation Google/IP).

Mesures en place :
- Aucun exit node par défaut ; les conteneurs forcent leur **DNS** sur
  `1.1.1.1`/`9.9.9.9` avec `dns_search: localdomain` → plus de domaine de recherche
  `tail*.ts.net` (vérifié : `ExtServers: [1.1.1.1 9.9.9.9]`, `search localdomain`).
- Le sous-réseau compose est fixé (`172.28.0.0/16`) pour permettre une politique
  de routage hôte si besoin.
- Vérification : `make egress` (compare l'IP de sortie hôte ↔ conteneur et lit
  les préférences Tailscale). Sortie attendue : *egress is on the physical
  network, not Tailscale*.

Si tu veux à tout moment désactiver un exit node :
```bash
sudo tailscale set --exit-node=
sudo tailscale set --accept-routes=false
```

## 4bis. Telegram — dialogue avec l'agent (obligatoire)

Canal d'alerte **et** de dialogue : l'agent peut toujours poser une question à
l'opérateur quand il est bloqué (captcha, phone verify, refus, action risquée).

Configuration (`.env`) :
- `MNEMOSYNE_TELEGRAM_BOT_TOKEN` — token du bot (BotFather) ;
- `MNEMOSYNE_TELEGRAM_CHAT_ID` — **ton** id (destinataire).

Mise en service (une fois) : ouvre la conversation du bot dans Telegram et envoie
`/start`. Sans ça, Telegram refuse que le bot écrive le premier (« chat not found »).

Deux sens :
- **agent → toi** : alertes, questions (`Notifier.ask`) ;
- **toi → agent** : tu **réponds au bot** ; le heartbeat lit tes messages à chaque
  tick et les verse dans `control/inbox.md` + journal (traités comme `mnemosyne say`).

Vérifs :
```bash
mnemosyne telegram test      # envoie un message de test
mnemosyne telegram updates   # messages reçus + chat_id
mnemosyne doctor             # ligne "telegram: enabled=… bot=@…"
```

## 4. Surveiller & orienter l'agent

| Canal | Usage |
|---|---|
| **Journal quotidien** | `mnemosyne journal` ou `journal/YYYY-MM-DD.md` — un fichier par jour, append-only. |
| **Journal par service** | `mnemosyne journal --service <id>` ou `journal/services/<id>.md` — un md par fournisseur auquel l'agent veut accéder, avec **dates complètes** de chaque action. Lister : `mnemosyne journal --services`. |
| **Message ponctuel** | `mnemosyne say "priorise Lacq et Pechelbronn"` — déposé dans `control/inbox.md`, lu au tick suivant. |
| **Directives** | `control/directives.md` — consignes permanentes, relues au démarrage. |
| **Statut** | `mnemosyne status` — providers, assets, pression du gouverneur. |
| **Alertes** | Telegram (captcha dur, blocage, source dégradée, échec définitif). |
| **Santé** | `mnemosyne doctor` — config, vault, auth LLM, accessibilité Chrome. |

Le journal contient : démarrages, directives, messages opérateur, harvests,
sources dégradées, erreurs/retries, digests périodiques.

## 4ter. Auto-extension (l'agent code ses propres connecteurs)

L'agent peut ajouter un fournisseur **lui-même** : descripteur + connecteur +
test, puis lint/tests, commit sur une branche `agent/*`, push et **PR**. Tu relis
et merges.

**Jeton GitHub (une fois)** — fine-grained PAT :
GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token
- **Repository access** → *Only select repositories* → `Antonio-Faure/mnemosyne`
- **Permissions** → *Repository permissions* → cocher **exactement** :
  - **Contents** → **Read and write**  (`git push` : blobs/trees/commits/refs)
  - **Pull requests** → **Read and write**  (`POST /repos/{owner}/{repo}/pulls`)
- **Metadata** → *Read-only* : déjà requis/imposé, laissé tel quel.
- Rien d'autre : pas d'*Administration*, pas de *Workflows*, pas de delete.
- *Expiration* : au choix (60–90 j recommandé).

> Les autres permissions (Issues, Actions, Webhooks…) ne sont **pas** nécessaires.
> L'agent travaille sur une branche `agent/*` : `Contents: write` y suffit, et
> `Pull requests: write` ouvre la PR vers `main`.

Puis, depuis le dossier du repo sur `yggdrasil` (l'exécutable est `.venv/bin/mnemosyne`, pas dans le PATH) :
```bash
make token        # saisie masquée, pas d'historique shell
# équivalent :
.venv/bin/mnemosyne vault set github_token <token>
```
(ou exporte `GITHUB_TOKEN=…` pour un usage ponctuel.)

**Lancer une extension :**
```bash
mnemosyne develop "Add the Europeana connector"     # ou : make develop TASK="..."
```

Garde-fous (dans le code, pas seulement le prompt) :
- écriture **uniquement** sous `config/sources/`, `src/mnemosyne/sources/`,
  `tests/`, `docs/` ;
- **interdit** : `.env`, `vault/`, `data/`, `heartbeat/`, `reputation/`,
  `agents/`, `dev/`, `AGENTS.md`, `pyproject.toml`… (l'agent ne peut pas modifier
  ses propres permissions) ;
- **pas** de `--force` / `reset` / `clean` / `rm` / delete de branche ;
- `ruff` + `pytest` doivent passer avant tout commit.

## 5. OpenCode Go (abo)

L'agent utilise ton abonnement **sans clé séparée** : il lit le token mis en cache
par opencode.

Ordre de résolution de la clé :
1. `OPENCODE_API_KEY` (env) ;
2. vault mnemosyne (`mnemosyne vault set opencode_api_key <clé>`) ;
3. **auth opencode** (`~/.local/share/opencode/auth.json` → `opencode-go`).

Vérifier :

```bash
mnemosyne doctor        # montre auth_source
mnemosyne llm test      # un aller-retour ; doit répondre "OK"
```

> `deepseek-v4.1-flash` est un modèle à raisonnement : prévoir `max_tokens >= 1024`,
> sinon le `content` peut être vide.

## 6. Dépannage

- `chrome cdp: unreachable` → `docker compose up -d chrome` puis attendre ~5 s.
- `No LLM API key` → vérifie `OPENCODE_AUTH_PATH` (montage) ou `mnemosyne vault set`.
- Heartbeat qui boucle sur une source → regarder `mnemosyne status`, le gouverneur
  met la source en cooldown après un 403/429.
