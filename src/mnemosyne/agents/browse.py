"""Generic autonomous browser agent — uses browser-use's NATIVE Agent.

browser-use already knows how to click, type, scroll, switch tabs, handle
dialogs/dropdowns and upload files (see browser-use/browser-harness interaction
skills). We do NOT re-implement those as micro-tools; we drive its `Agent` with
our OpenCode/Zen model and attach it to the dedicated Chrome over CDP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from browser_use import Agent, BrowserSession

from mnemosyne.browser import cdp_url
from mnemosyne.config import Config
from mnemosyne.identity import disclosure
from mnemosyne.journal import Journal
from mnemosyne.llm.client import USER_AGENT, resolve_api_key
from mnemosyne.logger import get_logger

log = get_logger("browse")


@dataclass
class BrowseOutcome:
    finish: str | None
    success: bool | None


def _build_llm(config: Config, vault_get=None):
    from browser_use.llm import ChatOpenAI

    prov = config.llm.providers.get(config.llm.default)
    if prov is None:
        raise RuntimeError(f"LLM provider '{config.llm.default}' is not configured")
    api_key, _ = resolve_api_key(prov, vault_get)
    if not api_key:
        raise RuntimeError("no LLM key for the browse agent")
    return ChatOpenAI(
        model=prov.model or "deepseek-v4.1-flash",
        base_url=prov.base_url,
        api_key=api_key,
        default_headers={
            "User-Agent": USER_AGENT,
            "x-opencode-session": f"mnemosyne-browse-{uuid.uuid4().hex[:8]}",
        },
        max_completion_tokens=8192,
        temperature=0.2,
    )


def _available_files(config: Config) -> list[str]:
    """Files under data/outbox, exposed to the browser as /outbox/<name> (upload)."""
    outbox = config.data_path / "outbox"
    if not outbox.exists():
        return []
    return [f"/outbox/{p.name}" for p in sorted(outbox.iterdir()) if p.is_file()]


async def run_browse(
    config: Config,
    task: str,
    *,
    journal: Journal | None = None,
    vault_get=None,
    out_dir: Path | None = None,
) -> BrowseOutcome:
    session = BrowserSession(cdp_url=cdp_url(), keep_alive=True)
    agent = Agent(
        task=task,
        llm=_build_llm(config, vault_get),
        browser_session=session,
        available_file_paths=_available_files(config),
        max_actions_per_step=5,
        extend_system_message=(
            "You act in your own name and are transparent about it: "
            + disclosure(config.identity)
            + " Files to upload are made available to you (e.g. /outbox/*)."
        ),
    )
    save_dir = out_dir or (config.root / config.agents.output_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    try:
        history = await agent.run(max_steps=config.agents.max_turns)
    finally:
        try:
            await session.stop()
        except Exception:  # noqa: BLE001 - cleanup only
            pass
    final = None
    success = None
    try:
        final = history.final_result()
        success = history.is_successful()
    except Exception:  # noqa: BLE001 - older/newer API differences
        final = str(history)[:2000]
    log.info("browse done: success=%s result=%s", success, (final or "")[:200])
    if journal:
        journal.append(f"browse — {final or '(pas de résultat)'}", source="browse")
    return BrowseOutcome(finish=final, success=success)
