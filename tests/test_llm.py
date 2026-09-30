import json

import pytest

from mnemosyne.config import ProviderConfig
from mnemosyne.llm.client import LlmClient, resolve_api_key


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeAsyncClient:
    last: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(
            {"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 7}}
        )


def _config_with_zen(config):
    config.llm.default = "zen"
    config.llm.providers["zen"] = ProviderConfig(
        base_url="https://opencode.ai/zen/go/v1", model="deepseek-v4.1-flash"
    )
    return config


@pytest.mark.asyncio
async def test_chat_omits_max_tokens_and_captures_usage(config, monkeypatch):
    cfg = _config_with_zen(config)
    client = LlmClient(cfg, session="t")
    client.api_key = "fake"
    monkeypatch.setattr("mnemosyne.llm.client.httpx.AsyncClient", _FakeAsyncClient)

    out = await client.chat([{"role": "user", "content": "hi"}])

    assert out == "OK"
    payload = _FakeAsyncClient.last["json"]
    assert "max_tokens" not in payload
    assert _FakeAsyncClient.last["headers"]["x-opencode-session"] == "t"
    assert client.last_usage["total_tokens"] == 7


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
