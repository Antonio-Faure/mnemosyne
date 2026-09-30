"""LLM client for OpenCode Go (Zen) and other OpenAI-compatible providers.

The API key is resolved, in order, from:

1. the provider's ``api_key_env`` environment variable;
2. the encrypted mnemosyne vault (key ``opencode_api_key``);
3. the **opencode auth store** — the same token opencode itself caches after you
   log in to your OpenCode Go subscription (``~/.local/share/opencode/auth.json``,
   entry ``opencode-go``).

OpenCode Go also requires a clean ``User-Agent`` and a stable ``x-opencode-session``
header, both set here.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from mnemosyne.config import Config, ProviderConfig
from mnemosyne.logger import get_logger

log = get_logger("llm")

USER_AGENT = "mnemosyne-agent/0.1 (+https://github.com/Antonio-Faure/mnemosyne)"

AUTH_STORE_CANDIDATES = [
    ("env", lambda: os.environ.get("OPENCODE_AUTH_PATH")),
    ("xdg", lambda: str(Path.home() / ".local" / "share" / "opencode" / "auth.json")),
    ("config", lambda: str(Path.home() / ".config" / "opencode" / "auth.json")),
]


def _read_opencode_auth(provider: str) -> tuple[str | None, str | None]:
    for _label, resolver in AUTH_STORE_CANDIDATES:
        path = resolver()
        if not path:
            continue
        p = Path(path).expanduser()
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry = data.get(provider)
        if isinstance(entry, dict) and entry.get("key"):
            return str(entry["key"]), f"opencode-auth:{p}"
    return None, None


def resolve_api_key(provider: ProviderConfig, vault_get=None) -> tuple[str | None, str | None]:
    """Return (api_key, source_description)."""
    if provider.api_key_env:
        env_key = os.environ.get(provider.api_key_env)
        if env_key:
            return env_key, f"env:{provider.api_key_env}"
    if vault_get is not None:
        stored = vault_get("opencode_api_key")
        if stored:
            return str(stored), "vault:opencode_api_key"
    if provider.auth_provider:
        key, source = _read_opencode_auth(provider.auth_provider)
        if key:
            return key, source
    return None, None


class LlmClient:
    def __init__(
        self,
        config: Config,
        *,
        provider: str | None = None,
        session: str | None = None,
        vault_get=None,
        timeout: float = 120.0,
    ):
        name = provider or config.llm.default
        prov = config.llm.providers.get(name)
        if prov is None:
            raise RuntimeError(f"LLM provider '{name}' is not configured")
        self.config = config
        self.provider_name = name
        self.provider = prov
        self.model = prov.model
        self.api_key, self.auth_source = resolve_api_key(prov, vault_get)
        self.session = session or f"mnemosyne-{uuid.uuid4().hex[:12]}"
        self._timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "base_url": self.provider.base_url,
            "model": self.model,
            "auth_source": self.auth_source,
            "available": self.available,
            "session": self.session,
        }

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "No LLM API key. Set OPENCODE_API_KEY, store it in the vault "
                "(`mnemosyne vault set opencode_api_key <key>`), or log in to "
                "OpenCode Go so the cached token is available."
            )
        url = self.provider.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
            "x-opencode-session": self.session,
        }
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return _extract_content(data)

    async def complete(
        self, prompt: str, *, system: str | None = None, **kwargs: Any
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, **kwargs)


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return content or ""
