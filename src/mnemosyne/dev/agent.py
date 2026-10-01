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

from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.dev.tools import DevToolProvider
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir, finish_text

log = get_logger("dev")

_SYSTEM = """You are {name}, an autonomous software agent that extends its OWN
repository: an open aggregator of historical image archive providers.

MISSION: {task}

CONVENTIONS (read AGENTS.md, docs/ARCHITECTURE.md, docs/P2-AGENTS.md first):
- A new provider = a descriptor `config/sources/<id>.yaml` + a `Connector`
  subclass in `src/mnemosyne/sources/<id>.py` + its registration in
  `src/mnemosyne/sources/__init__.py` + a mocked test in `tests/`.
- Normalize at the connector boundary into `Asset`; never leak provider shapes.
- Follow the existing connectors (gallica.py, wikidata.py) as models.

HARD RULES (enforced in code, do not attempt to bypass):
- You may only write under: config/sources/, src/mnemosyne/sources/, tests/, docs/.
- Never touch: .env, vault/, data/, journal/, control/, heartbeat/, reputation/,
  agents/, dev/, AGENTS.md, docker-compose.yml, Dockerfile, pyproject.toml.
- Never force-push, delete branches, reset or clean. No destructive git.
- `run_lint` and `run_tests` MUST pass before you commit.

WORKFLOW: start_branch(<slug>) → read code → write descriptor + connector +
test → run_lint → run_tests → commit → push → open_pr → task_done.
If you are stuck or a decision is ambiguous, call ask_operator (Telegram) and
stop rather than guessing.

BUDGET (token cost is quadratic: every step resends the whole transcript):
- Read AT MOST one existing connector as a template. Do NOT re-read files you
  already read. Do NOT list the whole tree.
- Prefer grep to locate things, then read only the relevant file.
- Keep tool outputs small; do not fetch large pages unless truly needed.
"""


@dataclass
class DevOutcome:
    finish: str | None
    branch: str | None


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
    agent = Agent(
        client=client,
        name="mnemosyne_dev",
        system_prompt=_SYSTEM.format(name=config.identity.name, task=task),
        tools=[provider],
        max_turns=config.dev.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(task)
    usage = client.usage.summary()
    log.info("dev agent usage (cache-aware): %s", usage)
    if journal:
        journal.append(f"dev agent usage: {usage}", source="dev")
    return DevOutcome(finish=provider.finish or finish_text(finish), branch=provider.branch)
