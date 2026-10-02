"""Self-extension agent: writes new providers/connectors and opens a PR.

Runs on the host (where the git checkout and token live), not in the browser
container. Requires the `agent` extra (`stirrup`, `openai`).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from stirrup import Agent

from mnemosyne.agents.progress import ProgressWatch, watch_provider
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.dev.tools import DevToolProvider
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir, finish_text, load_prompt

log = get_logger("dev")

_FALLBACK = (
    "You are {name}, the coder agent of mnemosyne. MISSION: {task}. "
    "Read agents/coder.md for your full instructions."
)


@dataclass
class DevOutcome:
    finish: str | None
    branch: str | None
    turns: int = 0


def _ensure_clean(repo: Path) -> None:
    """Abort if the working tree has uncommitted tracked changes.

    The dev agent commits on a fresh branch; pre-existing modified tracked files
    (outside its allowlist) make the commit guard refuse, which the model may
    misreport as success. Better to fail fast and loud.
    """
    res = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if res.stdout.strip():
        raise RuntimeError(
            "dev agent refused: the repo has uncommitted tracked changes — "
            "commit or stash them first (git status).\n" + res.stdout.strip()
        )


async def run_dev_agent(
    config: Config,
    task: str,
    *,
    vault_get=None,
    repo: str | Path | None = None,
    journal: Journal | None = None,
    mailbox=None,
    max_turns: int | None = None,
) -> DevOutcome:
    repo_path = Path(repo or config.root).resolve()
    _ensure_clean(repo_path)
    token = (vault_get("github_token") if vault_get else None) or os.environ.get("GITHUB_TOKEN")
    client = build_agent_client(
        config, session="dev", vault_get=vault_get, model=config.dev.model
    )
    notifier = Notifier(config.notify.telegram)
    provider = DevToolProvider(
        repo_path, config.dev, token, notifier=notifier, journal=journal, mailbox=mailbox
    )
    # Stuck detection, not a deadline: a long refactor that keeps progressing runs
    # to the end; only a freeze or a repeated-call loop is asked to report.
    progress = ProgressWatch(
        stall_after_s=config.agents.stall_after_s,
        stall_repeat=config.agents.stall_repeat,
    )
    watched = watch_provider(provider, progress, "codeur")
    agent = Agent(
        client=client,
        name="mnemosyne_dev",
        system_prompt=load_prompt(
            repo_path / "agents" / "coder.md",
            fallback=_FALLBACK,
            name=config.identity.name,
            task=task,
        ),
        tools=[watched],
        max_turns=max_turns or config.dev.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, history, _metadata = await session.run(task)
    usage = client.usage.summary()
    turns = int(usage.get("calls") or 0) or len(history)
    log.info("dev agent usage (cache-aware): %s (tours=%d)", usage, turns)
    if journal:
        journal.append(f"dev agent usage: {usage}", source="dev")
    return DevOutcome(
        finish=finish_text(finish), branch=provider.branch, turns=turns
    )
