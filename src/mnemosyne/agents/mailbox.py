"""Durable inter-agent mailbox (bi-agent).

The two agents (coder + browser) never launch each other: they *post messages*
here, and the deterministic supervisor (`agents/supervisor.py`) launches the
recipient when the sender has stopped. Messages survive crashes (SQLite).
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

    def post(self, sender: str, recipient: str, body: str) -> int:
        if recipient not in AGENTS and recipient != "operator":
            raise ValueError(f"unknown recipient '{recipient}' (use {AGENTS})")
        message_id = self.db.post_message(sender, recipient, body.strip())
        log.info("mail #%s %s → %s: %s", message_id, sender, recipient, body.strip()[:160])
        return message_id

    def next_for(self, recipient: str) -> dict | None:
        return self.db.next_pending_message(recipient)

    def pending_recipients(self, prefer_exclude: str | None = None) -> list[str]:
        pending = [a for a in AGENTS if self.db.next_pending_message(a) is not None]
        if prefer_exclude and len(pending) > 1 and prefer_exclude in pending:
            pending = [a for a in pending if a != prefer_exclude]
        return pending

    def mark(self, message_id: int, status: str = "handled", note: str | None = None) -> None:
        self.db.mark_message(message_id, status=status, note=note)

    def history(self, limit: int = 50) -> list[dict]:
        return self.db.list_messages(limit=limit)

    def pending_count(self) -> int:
        return self.db.count_messages(status="pending")
