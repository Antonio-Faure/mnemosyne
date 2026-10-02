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

Conteneur unique :
- `mnemosyne` — heartbeat + API (`http://localhost:8080`), Chrome headful
  (Xvfb) + browser-harness + CDP 9222, tout en uid 1000.

Le conteneur `mnemosyne` lit aussi le token OpenCode caché (montage lecture seule
de `~/.local/share/opencode` → `/opencode-auth`).

### Mode local (dev)

```bash
make install
.venv/bin/pip install -e '.[browser]'   # Stirrup + browser-harness
.venv/bin/mnemosyne vault init
.venv/bin/mnemosyne run      # heartbeat
.venv/bin/mnemosyne serve    # API (dans un autre terminal)
```

Les agents navigateur nécessitent un Chrome joignable en CDP :
`docker compose up -d mnemosyne` (ou un Chrome local avec
`--remote-debugging-port`) et règle `MNEMOSYNE_CDP_URL`.

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
> `127.0.0.1` **dans le conteneur**. L'app y accède en `127.0.0.1:9222`
> (`MNEMOSYNE_CDP_URL`). Pour vérifier : `make cdp`.

### Si Chrome affiche « Chrome n'est pas stable » / « stability and security will suffer »

Ce message venait de `--no-sandbox` (Chrome refusait le sandbox car lancé en root)
et d'arrêts non propres. Corrigé :
- Chrome tourne désormais en **uid 1000 non-root, sandbox activé** — plus de
  `--no-sandbox`, plus de message d'avertissement ;
- l'infobar déclenchée par `--disable-blink-features=AutomationControlled` (gardé
  pour l'anti-détection) est coupée par `--test-type` ;
- pour cela le conteneur relâche le **seccomp** de Docker
  (`security_opt: seccomp=unconfined`) : sans ça le sandbox Chrome ne peut pas
  créer ses namespaces. Trade-off assumé : réseau exposé en loopback uniquement
  (CDP/noVNC), et le sandbox Chrome reste actif ;
- nettoyage des verrous (`Singleton*`, verrou X) et
  `--hide-crash-restore-bubble` / `--disable-session-crashed-bubble` ;
- arrêt SIGTERM propre, `--disable-gpu`, `--disable-dev-shm-usage`.

Pour repartir d'un profil vierge (efface la connexion Google) : `make chrome-reset`,
puis reconnecte via `make vnc`.

> **Attention worktrees** : l'arbre de travail des helpers du navigateur
> (`data/agent-workspace/helpers-worktree`) est enregistré depuis le conteneur
> (chemin absolu `/app/...`). Depuis l'hôte, `git worktree list` le affiche
> « prunable » — c'est normal. Ne lance pas `git worktree prune` sur l'hôte :
> ça casserait le worktree de l'agent (il se recrée tout seul au prochain tour,
> mais les helpers non publiés seraient perdus).

## 3bis. Transparence & mémoire

- **Transparence** : tout mail / formulaire inclut une phrase d'identité + l'URL du
  repo, construite depuis `config.identity` (`src/mnemosyne/identity.py`). Exemple :
  « Je suis mnemosyne, un agent logiciel autonome qui développe un projet de
  recherche ouvert… Open source : https://github.com/Antonio-Faure/mnemosyne ».
- **Contexte borné** : un tour d'agent est une session Stirrup bornée
  (`agents.max_turns`), les sorties d'outils sont tronquées, et les tours passent
  par la boîte aux lettres durable au lieu de rejouer tout l'historique.
- **Plafond de sortie** : Stirrup exige un plafond explicite (`agents.max_tokens`,
  gardé haut à 32k) pour ne jamais tronquer le raisonnement en `content` vide.
  L'`usage` (tokens) est capturé à chaque appel pour suivre le coût.

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

## 4quater. Découverte autonome (P3)

L'agent trouve **tout seul** de nouveaux fournisseurs d'images d'archives.
Première source : **Wikidata** (propriété `P6108` = manifeste IIIF). On regroupe
les 300 000+ manifestes par **hôte** → ça révèle les vrais fournisseurs qui
servent du IIIF (bibliothèques nationales, musées, universités) sans aucune clé.

- Job heartbeat `discover` : **1×/jour** (`config.discovery.interval_s`), dédup
  automatique contre les hôtes déjà présents au catalogue, résumé Telegram.
- Stockage : table `discoveries` (`db.count_discoveries()` / `list_discoveries()`).
- Lancement manuel : `mnemosyne discover --limit 100 --top 20`.

Candidats trouvés (extrait du 1er run) : `www.nga.gov` (127 942 manifestes),
`nationalmuseumse.iiifhosting.com`, `manifests.collections.yale.edu`,
`iiif.harvardartmuseums.org`, `iiif.musee-orsay.fr`, `iiif.bodleian.ox.ac.uk`…

Suite (P4) : l'agent dev transforme un candidat en descripteur + connecteur et
ouvre une PR (`docs/P2-AGENTS.md`).

## 4bisbis. Warmup automatique (« nourrir » le compte)

Le heartbeat planifie **1 à 2 sessions/jour**, à des heures humaines aléatoires
(fenêtre 8h–23h), avec 20% de chance de sauter (irrégularité humaine). Chaque
session **choisit une cible** et se balade lentement comme une personne, puis
quitte. Le tirage est **pondéré** (réaliste) : sites généralistes fréquents,
archives profondes rares.

Poids (extrait, `warmup_schedule.py`) : Google 20, Wikipédia 16, Gmail 12,
presse 8, Gallica 6, INA 5, Commons 5, archive.org 4, Europeana 3,
Wikidata/RetroNews/Flickr Commons/LoC 2, Open Library/David Rumsey/Persée 1.

Uniquement des sites **texte/image** : l'agent est un LLM, il ne peut pas
« regarder » une vidéo. Pas de YouTube/Twitch (ça ne sert qu'à garer un onglet).

Comportement : lecture, **scroll humain**, recherches plausibles, clics, skip
d'un mur. **Aucun outbound** (pas de compte, pas de mail). C'est ce qui construit
l'historique/cohérence du compte Google sans te solliciter.

Réglages `config.agents` : `warmup_per_day_min/max`, `warmup_window_start/end`,
`warmup_session_min/max` (minutes), `warmup_skip_probability`, `warmup_sites`,
`warmup_max_turns`. Le disjoncteur anti-freeze des jobs mécaniques est
`heartbeat.job_timeout_s` (1h) ; les sessions d'agent (agency) n'ont **jamais**
de plafond de temps (jugées sur le marqueur de patinage).

Enregistrer l'écran de l'agent (vidéo) : `make record SECONDS=120` (ffmpeg
`x11grab` dans le conteneur Chrome) → `data/agent-recording.mp4`. Lance une
session (warmup/onboarding) pendant l'enregistrement.

Lancer **manuellement** une session (debug) : `mnemosyne warmup --minutes 8`
(ou `make`-style dans le conteneur). Les sessions auto se voient dans le journal
(`warmup « <cible> » ~N min (session i/total)`) et dans les logs (avec le
`cached_pct`).

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
mnemosyne agency "Add the Europeana connector"      # ou : make agency TASK="..."
```

**Coût** — le dev agent renvoie tout son transcript à chaque étape, donc le coût
croît de façon quasi quadratique avec le nombre d'étapes et la taille des sorties
d'outils (un run « Europeana » a coûté ~960k tokens). Réglages dans `config.dev` :
`max_turns` (défaut 18), `read_max_chars`, `list_max_entries`, `grep_max_chars`,
`fetch_max_chars`, et `model` (modèle moins cher optionnel). Le prompt du dev agent
lui impose aussi de lire a minima. (`grep` exclut `.venv/.git/data`.)

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

> `deepseek-v4.1-flash` est un modèle à raisonnement : garder un plafond de
> sortie généreux (`agents.max_tokens`, 32k par défaut), sinon le `content`
> peut être vide.

## 6. Dépannage

- `chrome cdp: unreachable` → `docker compose restart mnemosyne` puis attendre ~5 s.
- `No LLM API key` → vérifie `OPENCODE_AUTH_PATH` (montage) ou `mnemosyne vault set`.
- Heartbeat qui boucle sur une source → regarder `mnemosyne status`, le gouverneur
  met la source en cooldown après un 403/429.
