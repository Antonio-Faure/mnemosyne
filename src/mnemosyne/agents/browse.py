"""Generic browser agent: do an arbitrary operator task with the dedicated Chrome."""

from __future__ import annotations

from stirrup import Agent

from mnemosyne.agents.onboarding import AgentOutcome
from mnemosyne.agents.tools import BrowserToolProvider
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.identity import disclosure
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir

log = get_logger("browse")

_SYSTEM = """You are {name}, driving a real browser to accomplish the operator's
request. You act in your own name and are transparent about it: {disclosure}

TOOLS (deterministic): goto(url) · read_page() · list_links(substring) ·
fill(selector, value) · click(selector) · press_enter(selector) ·
upload_file(selector, path) · blocked_status() · remember(key, value) ·
request_human(reason) · task_done(summary).

RULES:
- One step at a time; read_page() after each action to check the result.
- Files to upload live under /outbox/ (e.g. /outbox/agent-browsing.mp4); call
  upload_file with the CSS selector of the input[type=file].
- If you reach a captcha / login wall / phone verification you cannot pass, call
  request_human with the reason and stop. Never guess or force.
- When done, call task_done with a short factual summary (and any link produced).
"""


async def run_browse(
    config: Config,
    task: str,
    *,
    journal: Journal | None = None,
    vault_get=None,
) -> AgentOutcome:
    client = build_agent_client(config, session="browse", vault_get=vault_get)
    notifier = Notifier(config.notify.telegram)
    provider = BrowserToolProvider(
        vault_path=config.vault_file, notifier=notifier, journal=journal
    )
    agent = Agent(
        client=client,
        name="browse",
        system_prompt=_SYSTEM.format(
            name=config.identity.name, disclosure=disclosure(config.identity)
        ),
        tools=[provider],
        max_turns=config.agents.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(task)
    usage = client.usage.summary()
    log.info("browse usage (cache-aware): %s", usage)
    if journal:
        journal.append(f"browse — {provider.finish or finish}", source="browse")
    return AgentOutcome(finish=provider.finish or finish, outcome={"usage": usage})
