"""Adaptive reputation governor.

Single place every rate-limited / sensitive action must pass through:

* per-domain pacing and cooldown after a block (403 / 429 / captcha);
* daily caps that follow the account **warmup** phases (account age driven);
* a per-domain AIMD pressure multiplier: one blocking host slows itself down,
  never the whole catalog, and a served request halves the penalty back.

This is what lets a brand-new agent account ramp up without getting banned.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from mnemosyne.config import ReputationConfig, WarmupPhase
from mnemosyne.db import Database
from mnemosyne.logger import get_logger

log = get_logger("governor")

#: action class -> warmup cap attribute
_ACTION_CAPS = {
    "harvest": "harvest_per_day",
    "outbound": "outbound_per_day",
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
        self._domain_intervals: dict[str, float] = {}
        # Per-domain AIMD penalty. Kept per host: a Cloudflare 403 from one
        # provider must not make every other provider 8x slower.
        self._domain_pressure: dict[str, float] = {}
        self._in_flight = 0  # number of parallel requests currently holding an acquire

    # ── warmup ───────────────────────────────────────────────────────────
    def age_days(self) -> int | None:
        if not self.config.account_created_at:
            return None
        try:
            created = datetime.fromisoformat(self.config.account_created_at)
        except ValueError:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        else:
            # an offset in the string must be honoured, not overwritten
            created = created.astimezone(UTC)
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

    def set_domain_interval(self, domain: str, seconds: float) -> None:
        """Declare the minimum interval for a domain (`rate_limit_per_s`).

        The descriptor's politeness budget is enforced as a floor on top of the
        global `domain_min_interval_s`; the adaptive pressure still multiplies it.
        """
        if domain and seconds > 0:
            self._domain_intervals[domain] = float(seconds)

    def _wait_for(self, domain: str) -> float:
        base = max(self.config.domain_min_interval_s, self._domain_intervals.get(domain, 0.0))
        return base * self._domain_pressure.get(domain, _MIN_PRESSURE)

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
            wait = self._wait_for(domain)
            last = self._last_call.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if last and elapsed < wait:
                await asyncio.sleep(wait - elapsed)
            self._last_call[domain] = time.monotonic()

    async def report_block(self, domain: str, retry_after: float | None = None) -> None:
        now = time.monotonic()
        cooldown = retry_after if retry_after else self.config.block_cooldown_s
        self._cooldown_until[domain] = now + cooldown
        pressure = min(
            self._domain_pressure.get(domain, _MIN_PRESSURE) * 2, _MAX_PRESSURE
        )
        self._domain_pressure[domain] = pressure
        log.warning(
            "block on %s → cooldown %.0fs, pressure %.1f", domain, cooldown, pressure
        )

    def report_success(self, domain: str) -> None:
        """A served request halves this domain's penalty (AIMD recovery).

        Without this, one 403 froze the whole catalog: the multiplier only ever
        grew, so every later search paid for a host that had already blocked us.
        """
        current = self._domain_pressure.get(domain)
        if current is None:
            return
        nxt = current / 2
        if nxt <= _MIN_PRESSURE:
            self._domain_pressure.pop(domain, None)
        else:
            self._domain_pressure[domain] = nxt

    def status(self) -> dict:
        phase = self.phase()
        return {
            "account_age_days": self.age_days(),
            "pressure": round(
                max(self._domain_pressure.values(), default=_MIN_PRESSURE), 2
            ),
            "pressure_by_domain": {
                d: round(p, 2) for d, p in sorted(self._domain_pressure.items())
            },
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
