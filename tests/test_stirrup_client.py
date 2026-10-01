"""Turn tip: nudge a long-running agent so it stops and reports instead of grinding."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("stirrup")
pytest.importorskip("openai")

from mnemosyne.browser.stirrup_client import (  # noqa: E402
    TURN_TIP,
    UsageSink,
    _CompletionsProxy,
)


class FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return type("Response", (), {"usage": None})()


def _run_turns(proxy: _CompletionsProxy, n: int) -> list[list[dict[str, Any]]]:
    sent: list[list[dict[str, Any]]] = []
    for _ in range(n):
        payload = [{"role": "user", "content": "go"}]
        asyncio.run(proxy.create(messages=payload))
        sent.append(payload)  # the caller's list must never be mutated
    return sent


def test_tip_is_injected_at_threshold_then_every_step():
    inner = FakeCompletions()
    proxy = _CompletionsProxy(inner, UsageSink(), tip_at=3, tip_every=2)
    sent = _run_turns(proxy, 6)

    tip_turns = [
        i + 1
        for i, call in enumerate(inner.calls)
        if any(str(m.get("content", "")).startswith("Tip :") for m in call["messages"])
    ]
    assert tip_turns == [3, 5]
    first_tip = inner.calls[2]["messages"][-1]["content"]
    assert "3 tours" in first_tip and "Master" in first_tip
    assert "5 tours" in inner.calls[4]["messages"][-1]["content"]
    # caller payloads stay untouched (no leak into Stirrup's own list)
    assert all(len(p) == 1 for p in sent)


def test_no_tip_without_threshold():
    inner = FakeCompletions()
    proxy = _CompletionsProxy(inner, UsageSink())
    _run_turns(proxy, 5)
    assert all(len(c["messages"]) == 1 for c in inner.calls)


def test_tip_text_is_the_operator_wording():
    assert "ne t'acharne pas" in TURN_TIP
    assert "bilan" in TURN_TIP
