"""Stuck detection: tell an agent to stop only when it stops *progressing*.

A mission that takes an hour is fine — as long as the agent keeps getting
somewhere. What we must not do is cut a long task short because a clock ran
out. So we do not measure elapsed time as a verdict; we measure progress:

- every tool call gets a signature (tool + arguments + a fingerprint of what it
  returned). A signature never seen before is *progress*;
- N identical actions in a row is a loop;
- no new distinct action for `stall_after_s` is a freeze.

Only then does the orchestrator say "either finish, or write an honest report of
where you are stuck". The agent stays in charge: it decides whether it is stuck.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from dataclasses import dataclass, field

from mnemosyne.logger import get_logger

log = get_logger("progress")

#: What we inject once the agent looks stuck. Not a stop order: a long mission
#: that is advancing must run to the end.
STALL_NOTE = (
    "ORCHESTRATEUR — constat : aucune action nouvelle depuis {mins} min ({reason}).\n"
    "- blocage réel : termine par finish(reason=...) avec l'état exact du travail "
    "(fait, restant, chemins des fichiers, dernières pistes essayées) ;\n"
    "- mission qui avance : continue, ce constat est sans effet.\n"
    "Aucune limite de temps n'est appliquée : la détection porte sur l'absence "
    "de progrès, pas sur la durée de la session."
)

_WS = re.compile(r"\s+")


def _fingerprint(text: str) -> str:
    """Stable hash of a tool result, ignoring volatile bits (timings, paths)."""
    cleaned = _WS.sub(" ", text or "").strip()
    cleaned = re.sub(r"\d+(\.\d+)?\s*(ms|s)\b", "T", cleaned)
    cleaned = re.sub(r"/tmp/[^\s\"']+", "/tmp/x", cleaned)
    return hashlib.sha1(cleaned[:4000].encode("utf-8", "ignore")).hexdigest()[:12]


@dataclass
class ProgressWatch:
    """Decide whether an agent is advancing or going in circles.

    `agent` and `db` are optional: when a database is given, a stall marker is
    written for the watchdog, and cleared as soon as the agent moves again. The
    watchdog then reports "stuck, with a cause" instead of "running for long",
    which are very different things.
    """

    agent: str = ""
    db: object = None
    stall_after_s: float = 900.0
    stall_repeat: int = 6
    #: keep a bounded history: enough to detect a loop, small enough to forget
    history: deque[tuple[str, str, str]] = field(default_factory=lambda: deque(maxlen=40))
    seen: set[tuple[str, str, str]] = field(default_factory=set)
    last_progress_at: float = field(default_factory=time.monotonic)
    last_note_at: float = 0.0
    notes_sent: int = 0
    last_description: str = ""

    def record(self, tool: str, arguments: str, result: str) -> bool:
        """Register a tool call. Returns True when this call is new progress."""
        signature = (tool, _WS.sub(" ", arguments or "").strip()[:200], _fingerprint(result))
        self.last_description = f"{tool}({signature[1][:60]})"
        if signature not in self.seen:
            self.seen.add(signature)
            self.last_progress_at = time.monotonic()
            self.history.append(signature)
            if self.db is not None:
                from mnemosyne.monitor import clear_stall

                clear_stall(self.db, self.agent)
            return True
        self.history.append(signature)
        return False

    @property
    def repeat_run(self) -> int:
        """Length of the current run of identical calls."""
        if not self.history:
            return 0
        last = self.history[-1]
        run = 0
        for signature in reversed(self.history):
            if signature == last:
                run += 1
            else:
                break
        return run

    def is_stuck(self, now: float | None = None) -> bool:
        """True when nothing new happened for a while, or the same call repeats."""
        now = now if now is not None else time.monotonic()
        frozen = (now - self.last_progress_at) >= self.stall_after_s
        looping = self.repeat_run >= max(2, self.stall_repeat)
        return frozen or looping

    def reason(self, now: float | None = None) -> str:
        parts = []
        frozen = (now if now is not None else time.monotonic()) - self.last_progress_at
        if frozen >= self.stall_after_s:
            parts.append(f"{int(frozen // 60)} min sans action nouvelle")
        if self.repeat_run >= max(2, self.stall_repeat):
            parts.append(f"{self.repeat_run} fois la meme action")
        return ", ".join(parts) or self.last_description

    def note_for(self, now: float | None = None) -> str | None:
        """The nudge to attach to a tool result, at most once per 3 minutes.

        Never returned while the agent is progressing: a long mission must be
        allowed to finish.
        """
        now = now if now is not None else time.monotonic()
        if not self.is_stuck(now):
            return None
        if now - self.last_note_at < 180:
            return None
        self.last_note_at = now
        self.notes_sent += 1
        if self.db is not None:
            from mnemosyne.monitor import mark_stall

            mark_stall(self.db, self.agent, self.reason(now))
        frozen_min = max(1, int((now - self.last_progress_at) // 60))
        return STALL_NOTE.format(mins=frozen_min, reason=self.reason(now))

    def stats(self) -> dict:
        return {
            "notes_sent": self.notes_sent,
            "repeat_run": self.repeat_run,
            "since_progress_s": round(time.monotonic() - self.last_progress_at, 1),
            "distinct_actions": len(self.seen),
        }

def watch_provider(provider, watch: ProgressWatch, label: str):
    """Wrap a ToolProvider so every tool call goes through `watch`.

    One wrapper instead of touching each tool: a new tool must be covered the
    day it is added, on both agents (coder via run_dev_agent, browser via
    run_browser_agent).
    """
    class _Watched:
        def __init__(self, inner):
            self._inner = inner

        async def __aenter__(self):
            tools = await self._inner.__aenter__()
            return [_wrap_tool(tool, watch, label) for tool in tools]

        async def __aexit__(self, *exc):
            return await self._inner.__aexit__(*exc)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    return _Watched(provider)


def _wrap_tool(tool, watch: ProgressWatch, label: str):
    """Return a copy of `tool` whose result passes through the stuck detector."""
    from stirrup.core.models import Tool as _Tool

    executor = tool.executor

    async def watched_executor(params):
        result = await executor(params)
        text = ""
        content = getattr(result, "content", None)
        if isinstance(content, str):
            text = content
        else:
            text = str(content)
        watch.record(tool.name, str(getattr(params, "__dict__", params)), text)
        note = watch.note_for()
        if not note:
            return result
        log.warning("agent %s patine (%s) -> rapport demandé", label, watch.reason())
        if isinstance(content, str):
            try:
                result.content = f"{content}\n\n{note}"
                return result
            except Exception:  # noqa: BLE001 - fall back to the original result
                return result
        return result

    return _Tool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        executor=watched_executor,
    )
