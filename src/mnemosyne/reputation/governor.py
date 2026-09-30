"""Adaptive reputation governor.

Single place every rate-limited / sensitive action must pass through:

* per-domain pacing and cooldown after a block (403 / 429 / captcha);
* daily caps that follow the account **warmup** phases (account age driven);
* an AIMD-style pressure multiplier applied globally when a domain fights back.

This is what lets a brand-new agent account ramp up without getting banned.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from mnemosyne.config import ReputationConfig, WarmupPhase
from mnemosyne.db import Database
from mnemosyne.logger import get_logger

log = get_logger("governor")

#: action class -> warmup cap attribute
_ACTION_CAPS = {
    "harvest": "harvest_per_day",
    "outbound": "outbound_per_day",
    "onboard": "outbound_per_day",
}

_MAX_PRESSURE = 8.0
_MIN_PRESSURE = 1.0


class GovernorBlocked(RuntimeError):
    """Raised by `acquire` when a domain is cooling down after a block."""


class Governor:
    def __init__(self, config: ReputationConfig, db: Database):
        self.config = config
        self.db = db
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_call: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._pressure = _MIN_PRESSURE
        self._in_flight = 0  # number of parallel requests currently holding an acquire

    # ── warmup ───────────────────────────────────────────────────────────
    def age_days(self) -> int | None:
        if not self.config.account_created_at:
            return None
        try:
            created = datetime.fromisoformat(self.config.account_created_at).replace(tzinfo=UTC)
        except ValueError:
            return None
        return (datetime.now(UTC) - created).days

    def phase(self) -> WarmupPhase:
        age = self.age_days()
        phases = self.config.warmup
        if age is None:
            return phases[-1]  # trusted: no warmup
        for p in phases:
            if p.until_day is None or age < p.until_day:
                return p
        return phases[-1]

    def _today(self) -> str:
        return datetime.now(UTC).date().isoformat()

    def daily_count(self, action: str) -> int:
        return self.db.get_counter(f"{action}:{self._today()}")

    def cap(self, action: str) -> int | None:
        attr = _ACTION_CAPS.get(action)
        return getattr(self.phase(), attr) if attr else None

    def allowed(self, action: str) -> bool:
        cap = self.cap(action)
        return cap is None or self.daily_count(action) < cap

    def record(self, action: str, amount: int = 1) -> None:
        self.db.incr_counter(f"{action}:{self._today()}", amount)

    # ── per-domain pacing ────────────────────────────────────────────────
    def _lock(self, domain: str) -> asyncio.Lock:
        lock = self._domain_locks.get(domain)
        if lock is None:
            lock = self._domain_locks[domain] = asyncio.Lock()
        return lock

    async def acquire(self, domain: str) -> None:
        """Block until it is polite to call `domain`, or raise if cooling down."""
        if not domain:
            return
        now = time.monotonic()
        cooldown = self._cooldown_until.get(domain, 0.0)
        if cooldown > now:
            raise GovernorBlocked(
                f"{domain} cooling down for {cooldown - now:.0f}s after a block"
            )
        async with self._lock(domain):
            wait = self.config.domain_min_interval_s * self._pressure
            last = self._last_call.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if last and elapsed < wait:
                await asyncio.sleep(wait - elapsed)
            self._last_call[domain] = time.monotonic()

    async def report_block(self, domain: str, retry_after: float | None = None) -> None:
        now = time.monotonic()
        cooldown = retry_after if retry_after else self.config.block_cooldown_s
        self._cooldown_until[domain] = now + cooldown
        self._pressure = min(self._pressure * 2, _MAX_PRESSURE)
        log.warning(
            "block on %s → cooldown %.0fs, pressure %.1f", domain, cooldown, self._pressure
        )

    async def report_ok(self, domain: str) -> None:
        self._pressure = max(self._pressure * 0.9, _MIN_PRESSURE)

    def status(self) -> dict:
        phase = self.phase()
        return {
            "account_age_days": self.age_days(),
            "pressure": round(self._pressure, 2),
            "warmup": {
                "until_day": phase.until_day,
                "harvest_per_day": phase.harvest_per_day,
                "outbound_per_day": phase.outbound_per_day,
            },
            "today": {
                "harvest": self.daily_count("harvest"),
                "outbound": self.daily_count("outbound"),
            },
            "cooling_down": {
                d: round(until - time.monotonic())
                for d, until in self._cooldown_until.items()
                if until > time.monotonic()
            },
        }


def next_midnight_iso() -> str:
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).isoformat()
