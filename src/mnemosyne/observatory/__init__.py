"""Observatory event emission.

The observatory never drives the system: it only appends to the ``sessions`` /
``events`` tables, which the API tails over SSE. Emission is bound to the
current async context (one session + one actor) so the agent loop, the mailbox
and the LLM proxy can record events without threading a session id through
every call. Outside an activation context, `record()` is a no-op.

Every emission is best-effort: a broken/full/locked database must never break
the work that is being observed.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mnemosyne.logger import get_logger

if TYPE_CHECKING:  # avoid importing the whole persistence layer in hot paths
    from mnemosyne.db import Database

log = get_logger("observatory")


@dataclass(frozen=True)
class EventContext:
    db: Database
    session_id: str
    actor: str


_current: ContextVar[EventContext | None] = ContextVar(
    "mnemosyne_event_ctx", default=None
)


def task_session_id(task_id: int) -> str:
    return f"task:{task_id}"


def job_session_id(job_id: int) -> str:
    return f"job:{job_id}"


def use_context(db: Database, session_id: str, actor: str):
    """Bind the current async context to a session (returns a reset token)."""
    return _current.set(EventContext(db=db, session_id=session_id, actor=actor))


def reset_context(token) -> None:
    _current.reset(token)


def preview(value: Any, limit: int = 280) -> str:
    """One-line, bounded preview of an arbitrary value."""
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def record(
    kind: str, payload: dict[str, Any] | None = None, *, actor: str | None = None
) -> None:
    """Append an event to the session bound to the current context."""
    ctx = _current.get()
    if ctx is None:
        return
    try:
        ctx.db.add_event(ctx.session_id, kind, actor=actor or ctx.actor, payload=payload)
    except Exception as exc:  # noqa: BLE001 - observation must never break work
        log.debug("event %s dropped: %s", kind, exc)


def record_for(
    db: Database,
    session_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    actor: str = "system",
) -> None:
    """Append an event to an explicit session (orchestrator-side emission)."""
    try:
        db.add_event(session_id, kind, actor=actor, payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.debug("event %s dropped: %s", kind, exc)
