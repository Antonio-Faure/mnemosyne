"""Encrypted credential vault.

Secrets (API keys, logins, session cookies) are stored in a single Fernet-encrypted
blob written atomically. The master key comes from `MNEMOSYNE_VAULT_KEY` or a local
`vault/vault.key` file (0600, git-ignored).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from mnemosyne.util import atomic_write_text, ensure_dir


class VaultError(RuntimeError):
    pass


def resolve_key(vault_path: Path, key: str | None = None) -> bytes:
    if key:
        return key.encode()
    env = os.environ.get("MNEMOSYNE_VAULT_KEY")
    if env:
        return env.encode()
    key_file = vault_path.parent / "vault.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip().encode()
    raise VaultError(
        "No vault key. Set MNEMOSYNE_VAULT_KEY or run `mnemosyne vault init`."
    )


def create_key(vault_path: Path, overwrite: bool = False) -> bytes:
    key_file = vault_path.parent / "vault.key"
    if key_file.exists() and not overwrite:
        return key_file.read_text(encoding="utf-8").strip().encode()
    ensure_dir(key_file.parent)
    key = Fernet.generate_key()
    key_file.write_text(key.decode(), encoding="utf-8")
    os.chmod(key_file, 0o600)
    return key


class Vault:
    def __init__(self, path: str | Path, key: bytes | None = None):
        self.path = Path(path)
        self._fernet = Fernet(key or resolve_key(self.path))
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self._fernet.decrypt(self.path.read_bytes()))
        except InvalidToken as exc:
            raise VaultError("Vault key does not match this vault file.") from exc

    def _flush(self) -> None:
        atomic_write_text(self.path, self._fernet.encrypt(json.dumps(self._data).encode()).decode())

    def flush(self) -> None:
        """Write the (possibly empty) vault to disk."""
        self._flush()

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._flush()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def delete(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._flush()

    def keys(self) -> list[str]:
        return sorted(self._data)


def init_vault(vault_path: str | Path, overwrite: bool = False) -> Path:
    path = Path(vault_path)
    key = create_key(path, overwrite=overwrite)
    vault = Vault(path, key=key)
    vault.flush()  # materialize the empty encrypted vault
    return path
