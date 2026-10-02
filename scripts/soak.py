"""Soak watchdog (manual entry point).

The checks live in `mnemosyne.monitor` and run *inside the service* as a
`watchdog` job, so they survive a restart. This script stays for one-off runs
and for a container without the heartbeat:

    python scripts/soak.py --interval 300

Invariants (an alert means "look at it", never "stop it"):
  * an agent that reported itself stuck (progress stall, with a cause)
  * a message pending for more than --pending minutes
  * a lease (browser, agency) held by a process that no longer exists
  * a job stuck running for more than --stale minutes
  * a message waiting for the operator's decision (status "review"), counted
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from mnemosyne.config import get_config
from mnemosyne.monitor import PENDING_MIN, STALE_MIN, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=300)
    parser.add_argument("--stale", type=float, default=STALE_MIN, help="minutes")
    parser.add_argument("--pending", type=float, default=PENDING_MIN, help="minutes")
    parser.add_argument("--out", default="data/outbox/soak.log")
    parser.add_argument("--once", action="store_true", help="one check, then exit")
    args = parser.parse_args()
    config = get_config()
    out = Path(config.root) / args.out if not args.out.startswith("/") else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    while True:
        report(config, out, stale_min=args.stale, pending_min=args.pending)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
