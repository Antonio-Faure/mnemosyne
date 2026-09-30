import json

from mnemosyne.config import ProviderConfig
from mnemosyne.llm.client import resolve_api_key


def test_resolve_from_env(monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "env-secret")
    key, source = resolve_api_key(ProviderConfig(base_url="https://x", api_key_env="MY_LLM_KEY"))
    assert key == "env-secret"
    assert source == "env:MY_LLM_KEY"


def test_resolve_from_vault():
    key, source = resolve_api_key(
        ProviderConfig(base_url="https://x"),
        vault_get=lambda k: "vault-secret" if k == "opencode_api_key" else None,
    )
    assert key == "vault-secret"
    assert source == "vault:opencode_api_key"


def test_resolve_from_opencode_auth(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"opencode-go": {"type": "api", "key": "cached-token"}}))
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(auth))
    provider = ProviderConfig(base_url="https://opencode.ai/zen/go/v1", auth_provider="opencode-go")
    key, source = resolve_api_key(provider)
    assert key == "cached-token"
    assert "auth.json" in source


def test_missing_key():
    key, source = resolve_api_key(ProviderConfig(base_url="https://x"))
    assert key is None
    assert source is None
