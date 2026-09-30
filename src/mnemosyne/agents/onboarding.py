"""Onboarding agent: obtain legitimate access (account / API key) to a provider."""

from __future__ import annotations

from dataclasses import dataclass

from stirrup import Agent

from mnemosyne.agents.prompts import onboarding_system, onboarding_task
from mnemosyne.agents.tools import BrowserToolProvider
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.journal import Journal
from mnemosyne.models import SourceDescriptor
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir


@dataclass
class AgentOutcome:
    finish: str | None
    outcome: dict


async def run_onboarding(
    config: Config,
    descriptor: SourceDescriptor,
    *,
    vault_get=None,
    journal: Journal | None = None,
) -> AgentOutcome:
    client = build_agent_client(
        config, session=f"onboard-{descriptor.id}", vault_get=vault_get
    )
    notifier = Notifier(config.notify.telegram)
    provider = BrowserToolProvider(
        vault_path=config.vault_file,
        notifier=notifier,
        journal=journal,
        service_id=descriptor.id,
        service_title=descriptor.name,
    )

    agent = Agent(
        client=client,
        name=f"onboard_{descriptor.id}",
        system_prompt=onboarding_system(descriptor, config.identity),
        tools=[provider],
        max_turns=config.agents.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(
            onboarding_task(descriptor, config.identity)
        )
    if journal:
        journal.append(
            f"onboarding `{descriptor.id}` LLM usage: {client.usage.summary()}",
            source="onboard",
        )
    return AgentOutcome(finish=provider.finish or finish, outcome=provider.outcome)
