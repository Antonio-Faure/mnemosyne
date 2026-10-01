"""Human-like warmup browsing: wander history/archive sites slowly.

Purpose: build the agent account's reputation by doing ordinary research on
history/archival images — reading, scrolling at human speed, occasional searches
— with NO outbound actions (no signups, no emails). Runs for a wall-clock budget.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path

from pydantic import BaseModel, Field
from stirrup import Agent
from stirrup.core.models import (
    EmptyParams,
    Tool,
    ToolResult,
    ToolUseCountMetadata,
)

from mnemosyne.agents.outcome import AgentOutcome
from mnemosyne.agents.tools import BrowserToolProvider, _fail, _ok
from mnemosyne.agents.warmup_schedule import pick_goal
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.notify import Notifier
from mnemosyne.util import ensure_dir, finish_text

log = get_logger("warmup")

_SYSTEM = """You are {name}, browsing the web like a curious human researching
historical photographs and archive images. This is a slow, natural session — not
a task to finish fast.

BEHAVIOUR (look human):
- Visit the sites one by one; on each, read a little, then scroll down a few
  screens in small steps with pauses, like someone reading.
- Sometimes use the search box with a plausible history query (e.g. "usine
  1900", "pétrole", "locomotive", "mine de charbon", "affiche ancienne").
- Sometimes click a link that looks interesting. Dwell; don't rush.
- Spread your actions over the whole time budget. Never hammer actions.

TOOLS: open_site(site) · scroll(screens) · read_page(max_chars) · type_search(query)
· click_link(text) · wait(seconds) · sites_list() · task_done(summary).

RULES: no accounts, no forms, no emails — read-only browsing. If a page is a
captcha/login wall, just move to another site. When the budget message appears
(or you are asked to finish), call task_done.
"""


class SiteParam(BaseModel):
    site: str = Field(description="Site URL or index from sites_list()")


class ScrollParam(BaseModel):
    screens: float = Field(default=1.5, description="How many screens to scroll down")


class ReadParam(BaseModel):
    max_chars: int = Field(default=1200, description="How much page text to read")


class SearchParam(BaseModel):
    query: str = Field(description="A plausible history search query")


class ClickParam(BaseModel):
    text: str = Field(description="Visible text of the link to click")


class WaitParam(BaseModel):
    seconds: float = Field(default=5.0, description="Seconds to dwell")


class DoneParam(BaseModel):
    summary: str = Field(description="Short summary of the session")


def _parse_site(site: str, sites: list[str]) -> str:
    site = site.strip()
    if site.isdigit():
        idx = int(site)
        if 0 <= idx < len(sites):
            return sites[idx]
    if not site.startswith("http"):
        low = site.lower()
        for candidate in sites:
            if low in candidate.lower():
                return candidate
        return "https://" + site
    return site


class WarmupToolProvider(BrowserToolProvider):
    def __init__(
        self,
        *,
        sites: list[str],
        minutes: float,
        vault_path: str | Path,
        notifier: Notifier,
        journal: Journal | None = None,
    ):
        super().__init__(vault_path=vault_path, notifier=notifier, journal=journal)
        self._sites = sites
        self._deadline = time.monotonic() + minutes * 60

    def _budget_over(self) -> bool:
        return time.monotonic() >= self._deadline

    def _budget_msg(self) -> str:
        left = max(0, int(self._deadline - time.monotonic()))
        return f"[budget] {left}s restants."

    async def _human_scroll(self, screens: float) -> None:
        steps = max(1, int(screens * 4))
        for _ in range(steps):
            dy = random.randint(180, 420)
            try:
                await self._eval(f"(...args) => window.scrollBy(0, {dy})")
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(random.uniform(0.5, 1.4))

    async def _human_pause(self, base: float) -> None:
        await asyncio.sleep(base + random.uniform(0.5, 2.5))

    def _tools(self) -> list[Tool]:
        async def sites_exec(_: EmptyParams):
            return _ok("\n".join(f"{i}. {s}" for i, s in enumerate(self._sites)))

        async def open_exec(p: SiteParam):
            url = _parse_site(p.site, self._sites)
            await self._goto(url)
            await self._human_pause(2.0)
            reason = await self._blocked()
            if reason:
                return _fail(f"mur detecte ({reason}); va sur un autre site. {self._budget_msg()}")
            text = (await self._text())[:1500]
            return _ok(f"ouvert {url}\n\n{text}\n\n{self._budget_msg()}")

        async def scroll_exec(p: ScrollParam):
            await self._human_scroll(p.screens)
            return _ok(f"scrollé ~{p.screens} écran(s). {self._budget_msg()}")

        async def read_exec(p: ReadParam):
            text = (await self._text())[: p.max_chars]
            return _ok(f"{text or '(vide)'}\n\n{self._budget_msg()}")

        async def search_exec(p: SearchParam):
            js = (
                "(...args) => { const q = document.querySelector("
                "'input[type=search],input[name=q],input[name=query],"
                "input[name=search],input[type=text]'); if(!q) return 'no-input';"
                " q.focus(); q.value = " + json.dumps(p.query) + ";"
                " q.dispatchEvent(new Event('input',{bubbles:true}));"
                " q.dispatchEvent(new Event('change',{bubbles:true}));"
                " if(q.form && q.form.requestSubmit){ q.form.requestSubmit(); }"
                " else { q.dispatchEvent(new KeyboardEvent('keydown',"
                "{key:'Enter',bubbles:true})); }"
                " return 'ok'; }"
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"recherche échouée: {exc}")
            await self._human_pause(2.5)
            return _ok(f"recherche '{p.query}': {res}. {self._budget_msg()}")

        async def click_exec(p: ClickParam):
            js = (
                "(...args) => { const t = " + json.dumps(p.text.lower()) + ";"
                " const a = [...document.querySelectorAll('a')].find(x =>"
                " (x.innerText||'').toLowerCase().includes(t));"
                " if(!a) return 'no-link'; a.click(); return 'ok'; }"
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"clic échoué: {exc}")
            await self._human_pause(2.0)
            return _ok(f"clic '{p.text}': {res}. {self._budget_msg()}")

        async def wait_exec(p: WaitParam):
            seconds = min(max(p.seconds, 1.0), max(1.0, self._deadline - time.monotonic()))
            await asyncio.sleep(seconds)
            return _ok(f"attendu {seconds:.0f}s. {self._budget_msg()}")

        return [
            Tool(name="sites_list", description="List the history/archive sites.",
                 parameters=EmptyParams, executor=sites_exec),
            Tool(name="open_site", description="Open a site (URL or index).",
                 parameters=SiteParam, executor=open_exec),
            Tool(name="scroll", description="Scroll down a few screens, human speed.",
                 parameters=ScrollParam, executor=scroll_exec),
            Tool(name="read_page", description="Read the visible page text.",
                 parameters=ReadParam, executor=read_exec),
            Tool(name="type_search", description="Type a query in the site search box.",
                 parameters=SearchParam, executor=search_exec),
            Tool(name="click_link", description="Click a link by its visible text.",
                 parameters=ClickParam, executor=click_exec),
            Tool(name="wait", description="Dwell a few seconds.",
                 parameters=WaitParam, executor=wait_exec),
        ]

    async def finish_task(self, p: DoneParam) -> ToolResult[ToolUseCountMetadata]:
        self.finish = p.summary
        return _ok("session terminée")

    def finish_tool(self) -> Tool:
        """Stirrup's finish tool: calling it really ends the session."""
        return Tool(
            name="task_done",
            description="Finish the session.",
            parameters=DoneParam,
            executor=self.finish_task,
        )


async def run_warmup(
    config: Config,
    *,
    minutes: float = 5.0,
    goal: dict | None = None,
    journal: Journal | None = None,
    vault_get=None,
) -> AgentOutcome:
    goal = goal or pick_goal()
    sites = goal.get("sites") or config.agents.warmup_sites
    client = build_agent_client(config, session="warmup", vault_get=vault_get)
    notifier = Notifier(config.notify.telegram)
    provider = WarmupToolProvider(
        sites=sites,
        minutes=minutes,
        vault_path=config.vault_file,
        notifier=notifier,
        journal=journal,
    )
    agent = Agent(
        client=client,
        name="warmup_browse",
        system_prompt=_SYSTEM.format(name=config.identity.name),
        tools=[provider],
        finish_tool=provider.finish_tool(),
        max_turns=config.agents.warmup_max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    task = (
        f"Session goal: {goal.get('instruction', 'browse archive sites')}\n"
        f"Spend about {minutes:.0f} minutes doing this, slowly, like a curious "
        "human. Start with sites_list(), then browse."
    )
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(task)
    usage = client.usage.summary()
    log.info("warmup usage (cache-aware): %s", usage)
    if journal:
        journal.append(f"warmup {minutes:.0f}min — LLM usage: {usage}", source="warmup")
    return AgentOutcome(
        finish=provider.finish or finish_text(finish), outcome={"usage": usage}
    )
