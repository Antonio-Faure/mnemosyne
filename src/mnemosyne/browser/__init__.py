"""Dedicated real-Chrome integration (P2).

The heartbeat will drive a headful Chrome over CDP (Xvfb + VNC inside the `chrome`
container) so the agent navigates with its own persistent profile and Google
account. browser-use / Playwright attach to `cdp_url()`.
"""

from __future__ import annotations

import os


def cdp_url() -> str:
    return os.environ.get("MNEMOSYNE_CDP_URL", "http://localhost:9222")


def is_configured() -> bool:
    return bool(os.environ.get("MNEMOSYNE_CDP_URL")) or os.environ.get(
        "MNEMOSYNE_BROWSER_ENABLED", "0"
    ) == "1"
