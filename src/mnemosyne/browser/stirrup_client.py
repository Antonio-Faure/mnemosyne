"""Stirrup chat client for OpenCode Go (Zen).

Stirrup's `ChatCompletionsClient` cannot inject custom HTTP headers, but Zen
requires a clean `User-Agent` and a stable `x-opencode-session`. We subclass it
and rebuild the underlying `AsyncOpenAI` with those headers, exactly like
`research/histoire_industrie/zen_client.py` in the sibling repo.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from stirrup.clients.chat_completions_client import ChatCompletionsClient

from mnemosyne.config import Config
from mnemosyne.llm.client import USER_AGENT, resolve_api_key


class ZenChatClient(ChatCompletionsClient):
    def __init__(
        self,
        model: str,
        max_tokens: int,
        *,
        context_window_tokens: int,
        base_url: str,
        api_key: str,
        session: str,
        timeout: float = 180.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            model,
            max_tokens,
            context_window_tokens=context_window_tokens,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers={
                "User-Agent": USER_AGENT,
                "x-opencode-session": session,
            },
        )


def build_agent_client(
    config: Config, *, session: str = "mnemosyne-agent", vault_get=None
) -> ZenChatClient:
    prov = config.llm.providers.get(config.llm.default)
    if prov is None:
        raise RuntimeError(f"LLM provider '{config.llm.default}' is not configured")
    api_key, source = resolve_api_key(prov, vault_get)
    if not api_key:
        raise RuntimeError(
            "No LLM API key for the agent. Set OPENCODE_API_KEY, store it in the "
            "vault, or log in to OpenCode Go so the cached token is available."
        )
    return ZenChatClient(
        model=prov.model or "deepseek-v4.1-flash",
        max_tokens=config.agents.max_tokens,
        context_window_tokens=config.agents.context_window_tokens,
        base_url=prov.base_url,
        api_key=api_key,
        session=session,
    )
