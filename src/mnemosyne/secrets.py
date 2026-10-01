"""Bridge vault-held credentials to the environment variables connectors read.

The browser agent stores a provider key in the vault under a lowercased name
(`europeana_api_key`); the descriptor declares `key_env: EUROPEANA_API_KEY` and
the connector reads `os.environ`. This module closes that loop: at Engine
startup, every vault secret named after a descriptor's `key_env` is exported.

Operator-provided environment variables always win (never overridden).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from mnemosyne.logger import get_logger
from mnemosyne.vault import Vault

log = get_logger("secrets")


def export_vault_secrets(
    vault_path: str | Path, descriptors: Iterable[object]
) -> list[str]:
    """Export vault secrets as env vars named by each descriptor's `key_env`.

    Returns the list of env var names actually set. Safe to call repeatedly.
    """
    names = {
        str(getattr(d, "key_env", "") or "").strip()
        for d in descriptors
    }
    names.discard("")
    if not names:
        return []
    vault_path = Path(vault_path)
    if not vault_path.exists():
        return []
    try:
        vault = Vault(vault_path)
    except Exception as exc:  # noqa: BLE001 - a bad vault must not kill startup
        log.warning("vault unavailable (%s); source keys not loaded", exc)
        return []

    exported: list[str] = []
    for name in sorted(names):
        if os.environ.get(name, "").strip():
            continue
        value = vault.get(name.lower())
        if not isinstance(value, str) or not value.strip():
            value = vault.get(name)
        if isinstance(value, str) and value.strip():
            os.environ[name] = value.strip()
            exported.append(name)
    if exported:
        log.info("loaded source credentials from vault: %s", ", ".join(exported))
    return exported
