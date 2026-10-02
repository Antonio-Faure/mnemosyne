"""Per-task temporary mailbox (bi-agent).

A task owns its mailbox: agents exchange messages ONLY inside the task they
are working on, and the mailbox dies with the task (the journal keeps the
trace). No global inbox anymore — a message without a task does not exist.
"""

from __future__ import annotations

from mnemosyne.db import Database
from mnemosyne.logger import get_logger

log = get_logger("mailbox")

AGENTS = ("coder", "browser")


class Mailbox:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def other(agent: str) -> str:
        return "browser" if agent == "coder" else "coder"

    def post(self, sender: str, recipient: str, body: str, task_id: int) -> int:
        """Post a message inside one task's mailbox (agent to agent only)."""
        if sender not in AGENTS or recipient not in AGENTS:
            raise ValueError(
                f"the mailbox is agent-to-agent (use {AGENTS}); "
                "the operator posts TASKS to the queue, not messages"
            )
        if sender == recipient:
            raise ValueError("cannot message yourself")
        message_id = self.db.post_message(sender, recipient, body.strip(), task_id)
        log.info(
            "mail #%s (tâche #%s) %s → %s: %s",
            message_id, task_id, sender, recipient, body.strip()[:160],
        )
        return message_id

    def pending_for(self, task_id: int, recipient: str) -> list[dict]:
        return self.db.pending_task_messages(task_id, recipient)

    def recipients(self, task_id: int) -> list[str]:
        return self.db.pending_task_recipients(task_id)

    def pending_count(self, task_id: int) -> int:
        return self.db.task_message_count(task_id)

    def mark(self, message_id: int, status: str = "handled", note: str | None = None) -> None:
        self.db.mark_message(message_id, status=status, note=note)

    def history(self, limit: int = 50) -> list[dict]:
        return self.db.list_messages(limit=limit)
