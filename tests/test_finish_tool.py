"""Session end must be Stirrup's native `finish`, not a homemade tool.

Our first `task_done` was an ordinary tool, so Stirrup never saw a finish signal
and sessions kept running (the model called it ten times in a row on the Gallica
treasure hunt). The native `finish` tool is injected by Stirrup itself; nothing
of ours may shadow it, and the instructions must name it.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("stirrup")
pytest.importorskip("openai")

from mnemosyne.agents.browser_agent import BrowserAgentToolProvider  # noqa: E402
from mnemosyne.agents.mailbox import Mailbox  # noqa: E402
from mnemosyne.agents.warmup import WarmupToolProvider  # noqa: E402
from mnemosyne.db import Database  # noqa: E402
from mnemosyne.dev.tools import DevToolProvider  # noqa: E402


def test_coder_has_no_homemade_finish_tool(config, tmp_path):
    provider = DevToolProvider(tmp_path, config.dev, None)
    assert "task_done" not in {t.name for t in provider._tools()}
    assert not hasattr(provider, "finish_tool")


def test_browser_has_no_homemade_finish_tool(config):
    db = Database(config.db_file())
    try:
        provider = BrowserAgentToolProvider(config, Mailbox(db))
        assert "task_done" not in {t.name for t in provider._tools()}
        assert not hasattr(provider, "finish_tool")
    finally:
        db.close()


def test_warmup_has_no_homemade_finish_tool(config):
    from mnemosyne.notify import Notifier

    provider = WarmupToolProvider(
        sites=["https://example.org"],
        minutes=1.0,
        vault_path=config.vault_file,
        notifier=Notifier(config.notify.telegram),
    )
    assert "task_done" not in {t.name for t in provider._tools()}
    assert not hasattr(provider, "finish_tool")


def test_agents_do_not_override_the_finish_tool():
    """No custom finish_tool= is passed: Stirrup's own `finish` must be used."""
    from mnemosyne.agents import browser_agent, warmup
    from mnemosyne.dev import agent as dev_agent

    for module, func in (
        (browser_agent, browser_agent.run_browser_agent),
        (dev_agent, dev_agent.run_dev_agent),
        (warmup, warmup.run_warmup),
    ):
        source = inspect.getsource(func)
        assert "finish_tool" not in source, f"{module.__name__} overrides finish"


def test_prompts_name_the_native_finish_tool():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    for name in ("coder.md", "browser.md"):
        text = (repo / "agents" / name).read_text(encoding="utf-8")
        assert "finish(reason" in text, f"{name} does not document finish()"
        assert "task_done" not in text, f"{name} still mentions task_done"
