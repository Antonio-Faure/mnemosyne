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
    usage: dict | None = None


def _build_llm(config: Config, vault_get=None):
    """A ChatOpenAI pointed at OpenCode/Zen that accumulates cache-aware usage."""
    from browser_use.llm import ChatOpenAI

    class TrackedChatOpenAI(ChatOpenAI):
        def __init__(self, *args, **kwargs):  # noqa: D401
            super().__init__(*args, **kwargs)
            self.usage_totals = {"calls": 0, "prompt": 0, "cached": 0, "completion": 0}

        async def ainvoke(self, *args, **kwargs):
            resp = await super().ainvoke(*args, **kwargs)
            usage = getattr(resp, "usage", None)
            if usage is not None:
                self.usage_totals["calls"] += 1
                self.usage_totals["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
                self.usage_totals["cached"] += getattr(usage, "prompt_cached_tokens", 0) or 0
                self.usage_totals["completion"] += getattr(usage, "completion_tokens", 0) or 0
            return resp

    prov = config.llm.providers.get(config.llm.default)
    if prov is None:
        raise RuntimeError(f"LLM provider '{config.llm.default}' is not configured")
    api_key, _ = resolve_api_key(prov, vault_get)
    if not api_key:
        raise RuntimeError("no LLM key for the browse agent")
    return TrackedChatOpenAI(
        model=prov.model or "deepseek-v4.1-flash",
        base_url=prov.base_url,
        api_key=api_key,
        default_headers={
            "User-Agent": USER_AGENT,
            "x-opencode-session": f"mnemosyne-browse-{uuid.uuid4().hex[:8]}",
        },
        # No output cap: reasoning models return empty content when the budget is
        # exhausted (None => the field is omitted from the request).
        max_completion_tokens=None,
        temperature=0.2,
        # OpenCode/Zen rejects strict json_schema response_format (400); put the
        # schema in the system prompt and let browser-use parse the JSON instead.
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
    )


def _available_files(config: Config) -> list[str]:
    """Files under data/outbox, made available to the agent for uploads.

    App and Chrome now live in the same container (same filesystem), so we pass
    the real absolute paths.
    """
    outbox = config.data_path / "outbox"
    if not outbox.exists():
        return []
    return [str(p) for p in sorted(outbox.iterdir()) if p.is_file()]


async def run_browse(
    config: Config,
    task: str,
    *,
    journal: Journal | None = None,
    vault_get=None,
    out_dir: Path | None = None,
) -> BrowseOutcome:
    session = BrowserSession(cdp_url=cdp_url(), keep_alive=True)
    llm = _build_llm(config, vault_get)
    agent = Agent(
        task=task,
        llm=llm,
        browser_session=session,
        available_file_paths=_available_files(config),
        max_actions_per_step=5,
        extend_system_message=(
            "You act in your own name and are transparent about it: "
            + disclosure(config.identity)
            + " Files to upload are made available to you (e.g. /outbox/*)."
        ),
    )
    if config.agents.force_vision:
        # browser-use turns vision OFF for any model named "deepseek"; v4.1-flash
        # has native vision, so re-enable it (deepseek is the first classic
        # DeepSeek model with vision).
        try:
            agent.settings.use_vision = True
            log.info("browse: vision forced ON for %s", getattr(llm, "model", "?"))
        except Exception as exc:  # noqa: BLE001
            log.warning("browse: could not force vision: %s", exc)
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
    usage = getattr(llm, "usage_totals", None)
    if usage:
        usage["cached_pct"] = round(100.0 * usage["cached"] / max(usage["prompt"], 1), 1)
    steps = getattr(history, "number_of_steps", None)
    log.info("browse done: success=%s steps=%s usage=%s", success, steps, usage)
    if journal:
        journal.append(
            f"browse — {final or '(pas de résultat)'} | steps={steps} usage={usage}",
            source="browse",
        )
    return BrowseOutcome(finish=final, success=success, usage=usage)
