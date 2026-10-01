"""`task_done` must be the framework finish tool, not an ordinary tool.

As a plain tool it did not end the Stirrup session: the model kept calling it
and the run burned turns up to max_turns (seen on the Gallica treasure hunt,
where task_done was called ten times in a row).
"""

from __future__ import annotations

import pytest

pytest.importorskip("stirrup")
pytest.importorskip("openai")

from mnemosyne.agents.browser_agent import BrowserAgentToolProvider  # noqa: E402
from mnemosyne.agents.mailbox import Mailbox  # noqa: E402
from mnemosyne.db import Database  # noqa: E402
from mnemosyne.dev.tools import DevToolProvider  # noqa: E402


def test_coder_task_done_is_the_finish_tool(config, tmp_path):
    provider = DevToolProvider(tmp_path, config.dev, None)
    assert provider.finish_tool().name == "task_done"
    # must not be a regular tool too: Stirrup rejects name collisions
    assert "task_done" not in {t.name for t in provider._tools()}


def test_browser_task_done_is_the_finish_tool(config):
    db = Database(config.db_file())
    try:
        provider = BrowserAgentToolProvider(config, Mailbox(db))
        assert provider.finish_tool().name == "task_done"
        assert "task_done" not in {t.name for t in provider._tools()}
    finally:
        db.close()


def test_warmup_task_done_is_the_finish_tool(config):
    from mnemosyne.agents.warmup import WarmupToolProvider
    from mnemosyne.notify import Notifier

    provider = WarmupToolProvider(
        sites=["https://example.org"],
        minutes=1.0,
        vault_path=config.vault_file,
        notifier=Notifier(config.notify.telegram),
    )
    assert provider.finish_tool().name == "task_done"
    assert "task_done" not in {t.name for t in provider._tools()}
