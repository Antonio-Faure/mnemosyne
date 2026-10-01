"""Vault -> env bridge for source credentials."""

from __future__ import annotations

import os

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.secrets import export_vault_secrets
from mnemosyne.vault import Vault, init_vault


def _descriptor(key_env: str | None = "EUROPEANA_API_KEY") -> SourceDescriptor:
    return SourceDescriptor(
        id="europeana",
        name="Europeana",
        protocol=Protocol.REST,
        base_url="https://example.org",
        auth="api_key",
        key_env=key_env,
    )


def test_exports_lowercased_vault_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEMOSYNE_VAULT_KEY", raising=False)
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    path = init_vault(tmp_path / "vault.enc")
    Vault(path).set("europeana_api_key", "secret")

    try:
        exported = export_vault_secrets(path, [_descriptor()])
        assert exported == ["EUROPEANA_API_KEY"]
        assert os.environ["EUROPEANA_API_KEY"] == "secret"
    finally:
        os.environ.pop("EUROPEANA_API_KEY", None)


def test_operator_env_wins_over_vault(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEMOSYNE_VAULT_KEY", raising=False)
    monkeypatch.setenv("EUROPEANA_API_KEY", "from-env")
    path = init_vault(tmp_path / "vault.enc")
    Vault(path).set("europeana_api_key", "from-vault")

    assert export_vault_secrets(path, [_descriptor()]) == []
    assert os.environ["EUROPEANA_API_KEY"] == "from-env"


def test_missing_vault_is_silent(tmp_path):
    assert export_vault_secrets(tmp_path / "nope.enc", [_descriptor()]) == []


def test_descriptor_without_key_env_is_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEMOSYNE_VAULT_KEY", raising=False)
    path = init_vault(tmp_path / "vault.enc")
    Vault(path).set("anything", "secret")

    assert export_vault_secrets(path, [_descriptor(key_env=None)]) == []
