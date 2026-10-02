"""Wall-clock budget of a turn: the turn cap alone does not bound the time.

400 fast turns last ~20 min, but 40 slow ones (stalled page, rate-limited API)
can hold the `agency` lease for hours and starve every other mission. Past the
deadline the agent is urged (every `deadline_tip_every` turns) to finish with a
factual report.
"""

from __future__ import annotations

import pytest

from mnemosyne.browser.stirrup_client import DEADLINE_TIP, TURN_TIP, UsageSink, _CompletionsProxy


class _FakeInner:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return getattr(self, name, None)

    async def create(self, *args, **kwargs):
        self.calls.append(kwargs)
        return type("R", (), {"usage": None})()


@pytest.mark.asyncio
async def _create(proxy, **kwargs):
    return await proxy.create(model="m", messages=[{"role": "user", "content": "go"}], **kwargs)


async def test_no_tip_before_deadline():
    proxy = _CompletionsProxy(_FakeInner(), UsageSink(), deadline_s=3600)
    for _ in range(3):
        await _create(proxy)
    assert all(len(c["messages"]) == 1 for c in proxy._inner.calls)


async def test_tip_after_deadline_then_every_n_turns():
    inner = _FakeInner()
    proxy = _CompletionsProxy(inner, UsageSink(), deadline_s=0.001, deadline_tip_every=3)
    import time

    time.sleep(0.01)
    for _ in range(7):
        await _create(proxy)
    nudged = [c for c in inner.calls if len(c["messages"]) == 2]
    assert len(nudged) == 3, "relance au dépassement (tour 1), puis toutes les 3 tours : 1, 4, 7"
    content = nudged[0]["messages"][-1]["content"]
    assert content == DEADLINE_TIP.format(minutes=0)
    assert "finish(reason=" in content


async def test_deadline_disabled_by_default():
    inner = _FakeInner()
    proxy = _CompletionsProxy(inner, UsageSink())
    import time

    proxy._started = time.monotonic() - 10_000
    for _ in range(4):
        await _create(proxy)
    assert all(len(c["messages"]) == 1 for c in inner.calls)


async def test_turn_tip_still_wins_before_deadline():
    inner = _FakeInner()
    proxy = _CompletionsProxy(inner, UsageSink(), tip_at=2, tip_every=2, deadline_s=3600)
    for _ in range(4):
        await _create(proxy)
    contents = [c["messages"][-1]["content"] for c in inner.calls if len(c["messages"]) == 2]
    assert contents and all("Cela fait" in c for c in contents)
    assert TURN_TIP.format(turns=2).split(".")[0] in contents[0]


def test_deadline_is_wired_from_config_to_the_completions_proxy():
    """Regression: the kwargs must reach the proxy through the three wrappers.

    Found in a real run: ZenChatClient passed deadline_s to _ClientProxy, which
    did not accept it, and every mission failed with a TypeError.
    """
    from mnemosyne.browser.stirrup_client import build_agent_client
    from mnemosyne.config import get_config

    cfg = get_config()
    cfg.agents.turn_deadline_s = 1234
    cfg.agents.deadline_tip_every = 3
    client = build_agent_client(cfg, vault_get=lambda _k: "sk-test")
    proxy = client._client.chat.completions
    assert proxy._deadline_s == 1234
    assert proxy._deadline_tip_every == 3
