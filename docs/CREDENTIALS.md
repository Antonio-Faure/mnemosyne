# Credentials

All secrets (API keys, logins, sessions) live in the **encrypted vault**
(`vault/`, git-ignored). `.env` only holds runtime settings; `.env.example` names
variables but never carries values. Secrets are **never** put in an agent message
— agents exchange a reference (`vault:<key>`).

## Source API keys: the vault → env bridge

Connectors read their key from the environment variable declared by the
descriptor (`config/sources/<id>.yaml`, field `key_env`, e.g.
`EUROPEANA_API_KEY`). The **browser agent** obtains the key and stores it in the
vault under the **lowercased name**:

```
remember("europeana_api_key", "<value>")     # browser agent tool (real tool)
```

The `remember` tool refuses the reserved keys (`github_token`,
`opencode_api_key`): only the operator sets those.

At startup, `Engine` runs `export_vault_secrets()`
(`src/mnemosyne/secrets.py`): for every descriptor with a `key_env`, the matching
vault secret (`<key_env>.lower()`, or the exact name) is exported to
`os.environ`. Operator-provided env vars always win — a value set in `.env` is
never overridden.

Manual equivalent:

```bash
mnemosyne vault set europeana_api_key "<value>"
```

The bridge runs at every `Engine` construction (CLI, API, heartbeat), so a key
stored by the browser agent is picked up on the next run without rebuilding or
editing `.env`.

## Other secrets

| Vault key          | Used by                          |
|--------------------|----------------------------------|
| `github_token`     | coder agent (push + PR)          |
| `opencode_api_key` | LLM client (fallback)            |
| `<source>_api_key` | connectors (via the bridge)      |

## Rules

- Never log a secret value. `export_vault_secrets()` logs only variable *names*.
- Vault writes go through `Vault.set()` (atomic write).
- If a provider needs an account (email verification, captcha), the browser agent
  asks the operator via Telegram (`request_human`) instead of guessing.
