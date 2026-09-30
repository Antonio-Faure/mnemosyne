"""Outreach agent: ask a provider (by email or contact form) for archive access."""

from __future__ import annotations

from stirrup import Agent

from mnemosyne.agents.onboarding import AgentOutcome
from mnemosyne.agents.prompts import outreach_system, outreach_task
from mnemosyne.agents.tools import OutreachToolProvider
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.journal import Journal
from mnemosyne.models import SourceDescriptor
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir


async def run_outreach(
    config: Config,
    descriptor: SourceDescriptor,
    ask: str,
    *,
    contact_email: str | None = None,
    contact_form_url: str | None = None,
    vault_get=None,
    journal: Journal | None = None,
) -> AgentOutcome:
    client = build_agent_client(
        config, session=f"outreach-{descriptor.id}", vault_get=vault_get
    )
    notifier = Notifier(config.notify.telegram)
    provider = OutreachToolProvider(
        vault_path=config.vault_file,
        notifier=notifier,
        journal=journal,
        service_id=descriptor.id,
        service_title=descriptor.name,
    )

    agent = Agent(
        client=client,
        name=f"outreach_{descriptor.id}",
        system_prompt=outreach_system(config.identity),
        tools=[provider],
        max_turns=config.agents.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    task = outreach_task(
        descriptor,
        ask,
        config.identity,
        contact_email=contact_email,
        contact_form_url=contact_form_url,
    )
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(task)
    if journal:
        journal.append(
            f"outreach `{descriptor.id}` LLM usage: {client.usage.summary()}",
            source="outreach",
        )
    return AgentOutcome(finish=provider.finish or finish, outcome=provider.outcome)
