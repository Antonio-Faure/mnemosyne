"""Stirrup chat client for OpenCode Go (Zen).

Stirrup's `ChatCompletionsClient` cannot inject custom HTTP headers, but Zen
requires a clean `User-Agent` and a stable `x-opencode-session`. We subclass it
and rebuild the underlying `AsyncOpenAI` with those headers.
"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from stirrup.clients.chat_completions_client import ChatCompletionsClient

from mnemosyne.config import Config
from mnemosyne.llm.client import USER_AGENT, resolve_api_key
from mnemosyne.logger import get_logger

log = get_logger("llm")


class UsageSink:
    """Accumulates prompt-cache stats that Stirrup itself ignores."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompt = 0
        self.cached = 0
        self.completion = 0

    def record(self, usage: Any) -> None:
        if usage is None:
            return
        self.calls += 1
        self.prompt += getattr(usage, "prompt_tokens", 0) or 0
        self.completion += getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details is not None else 0
        self.cached += cached or 0
        log.info(
            "LLM #%d: prompt=%d cached=%d (%.0f%% cumul)",
            self.calls,
            self.prompt,
            self.cached,
            100.0 * self.cached / max(self.prompt, 1),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt,
            "cached_tokens": self.cached,
            "cached_pct": round(100.0 * self.cached / max(self.prompt, 1), 1),
            "completion_tokens": self.completion,
        }


class _CompletionsProxy:
    def __init__(self, inner: Any, sink: UsageSink) -> None:
        self._inner = inner
        self._sink = sink

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        response = await self._inner.create(*args, **kwargs)
        try:
            self._sink.record(getattr(response, "usage", None))
        except Exception:  # noqa: BLE001 - never break a call over stats
            pass
        return response


class _ChatProxy:
    def __init__(self, inner: Any, sink: UsageSink) -> None:
        self._inner = inner
        self.completions = _CompletionsProxy(inner.completions, sink)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _ClientProxy:
    def __init__(self, inner: Any, sink: UsageSink) -> None:
        self._inner = inner
        self.chat = _ChatProxy(inner.chat, sink)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


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
        self.usage = UsageSink()
        self._client = _ClientProxy(
            AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
                default_headers={
                    "User-Agent": USER_AGENT,
                    "x-opencode-session": session,
                },
            ),
            self.usage,
        )


def build_agent_client(
    config: Config,
    *,
    session: str = "mnemosyne-agent",
    vault_get=None,
    model: str | None = None,
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
        model=model or prov.model or "deepseek-v4.1-flash",
        max_tokens=config.agents.max_tokens,
        context_window_tokens=config.agents.context_window_tokens,
        base_url=prov.base_url,
        api_key=api_key,
        session=session,
    )
