"""Robustly run `browser-harness video review` on a recording.

Why: the stock reviewer opens its render tab in the BACKGROUND. The harness
template (video-template.html) itself warns:

    // Keep this tab focused -- rAF throttles in background tabs and stalls capture.

On a busy machine that makes every `capture_screenshot` take seconds, so the
browser phase blows its budget (`subprocess.TimeoutExpired` from run_harness, or a
60s `Page.captureScreenshot` timeout near the end).

Fix (no product files touched): monkey-patch `video_render.run_harness` at
runtime to (1) bring the render tab to the front + enable focus emulation so
rAF/timers are not throttled (captures drop from ~3s to ~0.4s in practice), and
(2) raise the browser-phase timeout so a slow host still finishes.

In observed use this turned a review that timed out at 282s / 75 captures into a
clean "0 error(s)" review of 94 beats in ~81s.

Usage (in-process, e.g. from a browser() call):
    from video_review_foreground import review_foreground
    review_foreground("/path/to/recordings/xxx")   # returns 0 on success
"""
from __future__ import annotations

from pathlib import Path


def review_foreground(recording, min_timeout: float = 1200.0) -> int:
    from browser_harness import video_render as vr

    rec = Path(recording).expanduser().resolve()
    original = vr.run_harness

    anchor = "    target = new_tab()\n"
    inject = (
        "    target = new_tab()\n"
        "    try:\n"
        "        activate_tab(target)\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        cdp('Emulation.setFocusEmulationEnabled', enabled=True)\n"
        "    except Exception:\n"
        "        pass\n"
    )

    def patched(code, timeout=60):
        if anchor in code:
            code = code.replace(anchor, inject, 1)
        return original(code, timeout=max(timeout, min_timeout))

    vr.run_harness = patched
    try:
        return vr.review(rec)
    finally:
        vr.run_harness = original


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    raise SystemExit(review_foreground(target))
