"""Stuck detection replaces the wall-clock deadline I had wrongly added.

The rule the user stated: a long mission must run to the end; only an agent that
is *stuck* (patine) has to stop and write a report. So these tests pin both
halves of that rule.
"""

from __future__ import annotations

import pytest
from stirrup.core.models import EmptyParams, ToolResult, ToolUseCountMetadata

from mnemosyne.agents.progress import STALL_NOTE, ProgressWatch


def test_a_new_action_is_progress():
    watch = ProgressWatch(stall_after_s=900)
    assert watch.record("browser", "goto(a)", "page a") is True
    assert watch.record("browser", "goto(b)", "page b") is True
    assert watch.note_for() is None, "mission qui avance : jamais de note"


def test_same_call_with_same_result_is_a_loop():
    watch = ProgressWatch(stall_after_s=10_000, stall_repeat=4)
    watch.record("browser", "click(320,480)", "nothing happened")
    for _ in range(4):
        assert watch.record("browser", "click(320,480)", "nothing happened") is False
    assert watch.is_stuck() is True
    note = watch.note_for()
    assert note is not None
    assert "5 fois la meme action" in note


def test_same_call_with_a_different_result_is_progress():
    """A spinner that eventually loads is not a loop."""
    watch = ProgressWatch(stall_after_s=900, stall_repeat=3)
    watch.record("browser", "read_page(u)", "loading")
    for i in range(4):
        assert watch.record("browser", "read_page(u)", f"content variant {i}") is True
    assert watch.is_stuck() is False


def test_no_new_action_for_too_long_is_a_freeze():
    watch = ProgressWatch(stall_after_s=60)
    watch.record("browser", "goto(a)", "ok")
    assert watch.note_for(now=None) is None
    # 5 minutes later, still nothing new
    note = watch.note_for(now=watch.last_progress_at + 300)
    assert note is not None
    assert "5 min sans action nouvelle" in note


def test_the_note_is_factual_and_states_no_time_limit():
    """The note reports an observation; it neither scolds nor imposes a deadline."""
    watch = ProgressWatch(stall_after_s=60)
    watch.record("browser", "x", "y")
    now = watch.last_progress_at + 600
    note = watch.note_for(now=now)
    assert note == STALL_NOTE.format(mins=10, reason=watch.reason(now))
    assert "Aucune limite de temps" in note
    assert "pas sur la durée" in note
    assert "ce constat est sans effet" in note
    # no moralising, no shouting, no caps-lock orders
    for ugly in ("MAINTENANT", "honnête", "boucle silencieuse", "tu as peut-être"):
        assert ugly not in note


def test_the_note_is_not_repeated_every_call():
    watch = ProgressWatch(stall_after_s=60)
    watch.record("browser", "x", "y")
    now = watch.last_progress_at + 600
    assert watch.note_for(now=now) is not None
    assert watch.note_for(now=now + 10) is None, "une note toutes les 3 min max"
    assert watch.note_for(now=now + 200) is not None


def test_volatilities_do_not_fake_progress():
    watch = ProgressWatch(stall_after_s=900, stall_repeat=3)
    watch.record("browser", "read_page(u)", "took 1200ms /tmp/x1.html title A")
    assert watch.record("browser", "read_page(u)", "took 980ms /tmp/x2.html title A") is False


def test_history_stays_bounded():
    watch = ProgressWatch(stall_after_s=900)
    for i in range(200):
        watch.record("browser", f"call{i}", "result")
    assert len(watch.history) == 40
    assert watch.stats()["distinct_actions"] == 200


@pytest.mark.asyncio
async def test_wrapped_provider_passes_every_tool_through_the_watch():
    """A new coder tool is covered the day it is added, without editing it."""
    from mnemosyne.agents.progress import watch_provider

    class _Inner:
        def __init__(self):
            self.entered = False

        async def __aenter__(self):
            from stirrup.core.models import Tool

            self.entered = True

            async def exec_tool(_params):
                return _ok("same output")

            return [Tool(name="noop", description="d", parameters=EmptyParams, executor=exec_tool)]

        async def __aexit__(self, *exc):
            return None

    watch = ProgressWatch(stall_after_s=10_000, stall_repeat=3)
    wrapped = watch_provider(_Inner(), watch, "test")
    async with wrapped as tools:
        for _ in range(3):
            await tools[0].executor(EmptyParams())
    assert watch.is_stuck() is True, "trois appels identiques doivent etre vus comme une boucle"
    assert watch.stats()["distinct_actions"] == 1


def _ok(text: str) -> ToolResult:
    return ToolResult[ToolUseCountMetadata](content=text)


async def test_every_browser_tool_goes_through_the_single_watch(config):
    """One funnel for both agents: the browser provider is wrapped as a whole,
    not tool by tool by hand (the old per-tool copy covered 3 tools out of 7)."""
    pytest.importorskip("stirrup")
    from stirrup.core.models import EmptyParams

    from mnemosyne.agents.browser_agent import (
        BrowserAgentToolProvider,
        BrowserCodeParams,
        HelperNameParams,
        PublishParams,
        RememberParams,
        SendMessageParams,
        WriteHelperParams,
        watch_provider,
    )
    from mnemosyne.agents.mailbox import Mailbox
    from mnemosyne.db import Database

    db = Database(config.db_file())
    provider = BrowserAgentToolProvider(config, Mailbox(db))
    try:
        provider._run_harness = lambda code: "fake harness output"
        watch = provider.progress
        wrapped = watch_provider(provider, watch, "navigateur")
        tools = {t.name: t for t in await wrapped.__aenter__()}
        expected = {
            "browser", "list_helpers", "read_helper", "write_helper",
            "publish_helpers", "remember", "send_message",
        }
        assert set(tools) == expected
        params = {
            "browser": BrowserCodeParams(code="pass"),
            "list_helpers": EmptyParams(),
            "read_helper": HelperNameParams(name="ghost"),
            "write_helper": WriteHelperParams(name="probe", code="print(1)"),
            "publish_helpers": PublishParams(summary="test"),
            "send_message": SendMessageParams(to="coder", body="hello"),
            "remember": RememberParams(key="pytest_probe", value="v"),
        }
        for name, p in params.items():
            await tools[name].executor(p)
        recorded = {sig[0] for sig in watch.seen}
        assert recorded == expected, recorded
    finally:
        db.close()
