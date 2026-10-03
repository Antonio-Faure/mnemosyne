"""Real-Chrome integration.

The bi-agent drives one headful Chrome over CDP (Xvfb + noVNC inside the
`mnemosyne` container) with its own persistent profile and Google account;
`browser-harness` helpers attach to `cdp_url()`.
"""

from __future__ import annotations

import os


def cdp_url() -> str:
    return os.environ.get("MNEMOSYNE_CDP_URL", "http://localhost:9222")
