"""A restart must not re-verify every source when the last run is recent."""

from __future__ import annotations

import asyncio

from mnemosyne.heartbeat import Heartbeat
from mnemosyne.util import utcnow_iso


def _close(hb: Heartbeat) -> None:
    asyncio.run(hb.aclose())


def _due_verify(hb: Heartbeat) -> bool:
    claimed = hb.engine.db.claim_due_jobs(utcnow_iso(), 20)
    return any(
        job.kind == "verify" and job.payload.get("source_id") == "gallica"
        for job in claimed
    )


def test_recent_verify_is_scheduled_in_the_future(config):
    hb = Heartbeat(config)
    try:
        hb.engine.db.set_kv("verify_at:gallica", utcnow_iso())
        hb.bootstrap()
        assert not _due_verify(hb)
    finally:
        _close(hb)


def test_stale_verify_is_due_now(config):
    hb = Heartbeat(config)
    try:
        hb.engine.db.set_kv("verify_at:gallica", "2020-01-01T00:00:00+00:00")
        hb.bootstrap()
        assert _due_verify(hb)
    finally:
        _close(hb)
