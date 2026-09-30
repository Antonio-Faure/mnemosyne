"""Browser-use session attached to the dedicated Chrome over CDP."""

from __future__ import annotations

from mnemosyne.browser import cdp_url


def new_browser_session(keep_alive: bool = True):
    """Create a browser-use `BrowserSession` bound to the dedicated Chrome.

    Imported lazily so the core (heartbeat, API) works without the `browser`
    extra installed.
    """
    from browser_use import BrowserSession

    return BrowserSession(cdp_url=cdp_url(), keep_alive=keep_alive)
