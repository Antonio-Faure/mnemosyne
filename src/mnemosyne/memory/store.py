"""Persistent conversation memory with rolling compaction.

Long-running agents must not resend their whole history to the model on every
call: that is slow and expensive. Instead:

* recent messages are kept verbatim (``max_recent_messages``);
* once the stored history grows past ``compact_after_messages``, older messages
  are summarized by the LLM into a single rolling summary and **deleted** from
  the store (compaction).

Every call therefore sends only ``[system, summary, recent messages]``, so the
context — and the token bill — stays bounded no matter how long the agent runs.
The summary itself persists in the DB, so memory survives restarts.
"""

from __future__ import annotations

from typing import Any, Protocol

from mnemosyne.config import MemoryConfig
from mnemosyne.db import Database
from mnemosyne.logger import get_logger

log = get_logger("memory")


class SupportsChat(Protocol):
    async def chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> str: ...


def _summary_key(session: str) -> str:
    return f"memory_summary:{session}"


class Memory:
    def __init__(
        self,
        db: Database,
        llm: SupportsChat,
        session: str,
        config: MemoryConfig | None = None,
    ):
        self.db = db
        self.llm = llm
        self.session = session
        self.config = config or MemoryConfig()

    # ── writing ──────────────────────────────────────────────────────────
    def add(self, role: str, content: str) -> int:
        return self.db.memory_append(self.session, role, content)

    def summary(self) -> str:
        return str(self.db.get_kv(_summary_key(self.session), "") or "")

    def window(self) -> list[dict[str, str]]:
        rows = self.db.memory_messages(self.session)
        recent = rows[-self.config.max_recent_messages :]
        return [{"role": r["role"], "content": r["content"]} for r in recent]

    def count(self) -> int:
        return self.db.memory_count(self.session)

    # ── context ──────────────────────────────────────────────────────────
    def build_context(self, system: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        summary = self.summary()
        if summary:
            messages.append(
                {"role": "system", "content": f"Memory summary so far:\n{summary}"}
            )
        messages.extend(self.window())
        return messages

    # ── compaction ───────────────────────────────────────────────────────
    async def maybe_compact(self) -> bool:
        """Summarize and prune old messages once the history grows too large."""
        if self.count() <= self.config.compact_after_messages:
            return False

        rows = self.db.memory_messages(self.session)
        keep = self.config.max_recent_messages
        if len(rows) <= keep:
            return False
        older = rows[:-keep]

        transcript = "\n".join(f"{r['role']}: {r['content']}" for r in older)
        previous = self.summary()
        prompt = (
            (f"Existing summary:\n{previous}\n\n" if previous else "")
            + f"Conversation to fold into the summary:\n{transcript}\n\n"
            + self.config.summary_instruction
        )
        try:
            new_summary = (await self.llm.chat([{"role": "user", "content": prompt}])).strip()
        except Exception as exc:  # noqa: BLE001 - never lose the session on a failed summary
            log.warning("compaction failed, keeping full history: %s", exc)
            return False
        if not new_summary:
            return False

        self.db.set_kv(_summary_key(self.session), new_summary)
        pruned = self.db.memory_prune(self.session, older[-1]["seq"])
        log.info(
            "compacted session %s: %d messages folded, %d pruned",
            self.session,
            len(older),
            pruned,
        )
        return True

    async def reply(self, user_message: str, *, system: str, **chat_kwargs: Any) -> str:
        """Full turn: store the user message, compact if needed, answer, store reply."""
        self.add("user", user_message)
        await self.maybe_compact()
        answer = await self.llm.chat(self.build_context(system), **chat_kwargs)
        self.add("assistant", answer)
        return answer

    def clear(self) -> None:
        self.db.memory_prune(self.session, 10**9)
        self.db.set_kv(_summary_key(self.session), "")
