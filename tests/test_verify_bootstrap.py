"""A restart must not re-verify every source when the last run is recent."""

from __future__ import annotations

import asyncio

from mnemosyne.heartbeat import Heartbeat
from mnemosyne.util import utcnow_iso


def _close(hb: Heartbeat) -> None:
    asyncio.run(hb.aclose())


def test_recent_verify_is_not_reenqueued(config):
    hb = Heartbeat(config)
    try:
        hb.engine.db.set_kv("verify_at:gallica", utcnow_iso())
        hb.bootstrap()
        assert not hb.engine.db.has_open_job("verify", "gallica")
    finally:
        _close(hb)


def test_stale_verify_is_reenqueued(config):
    hb = Heartbeat(config)
    try:
        hb.engine.db.set_kv("verify_at:gallica", "2020-01-01T00:00:00+00:00")
        hb.bootstrap()
        assert hb.engine.db.has_open_job("verify", "gallica")
    finally:
        _close(hb)
