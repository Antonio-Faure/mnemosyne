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
.venv/bin/mnemosyne vault init
.venv/bin/mnemosyne run      # heartbeat
.venv/bin/mnemosyne serve    # API (dans un autre terminal)
```

## 3. Connecter le Gmail de l'agent

Le Chrome du conteneur est exposé en VNC + CDP :

1. Ouvre **http://localhost:6080** (noVNC) dans un navigateur.
2. Va sur `https://mail.google.com` et connecte-toi avec le **compte Gmail dédié**.
   Tu fais cette étape **une fois** : le profil persiste dans
   `data/chrome-profile/` (volume monté).
3. Le heartbeat (P2) réutilisera cette session pour lire les codes de vérification
   et envoyer les mails de demande d'accès. Le même noVNC sert à résoudre un
   captcha/phone-verify à la main quand Telegram t'alerte.

> Le CDP est sur `http://localhost:9222` — c'est là que browser-use se connecte
> (`MNEMOSYNE_CDP_URL`).

## 4. Surveiller & orienter l'agent

| Canal | Usage |
|---|---|
| **Journal** | `mnemosyne journal` ou `journal/YYYY-MM-DD.md` — un fichier par jour, append-only. |
| **Message ponctuel** | `mnemosyne say "priorise Lacq et Pechelbronn"` — déposé dans `control/inbox.md`, lu au tick suivant. |
| **Directives** | `control/directives.md` — consignes permanentes, relues au démarrage. |
| **Statut** | `mnemosyne status` — providers, assets, pression du gouverneur. |
| **Alertes** | Telegram (captcha dur, blocage, source dégradée, échec définitif). |
| **Santé** | `mnemosyne doctor` — config, vault, auth LLM, accessibilité Chrome. |

Le journal contient : démarrages, directives, messages opérateur, harvests,
sources dégradées, erreurs/retries, digests périodiques.

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
