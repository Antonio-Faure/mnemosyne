"""Structured events for the observatory (see `mnemosyne.observatory`).

`from mnemosyne.observatory import events` — then `events.record(...)`.
"""

from __future__ import annotations

from mnemosyne.observatory import (
    job_session_id,
    preview,
    record,
    record_for,
    reset_context,
    task_session_id,
    use_context,
)

__all__ = [
    "job_session_id",
    "preview",
    "record",
    "record_for",
    "reset_context",
    "task_session_id",
    "use_context",
]
