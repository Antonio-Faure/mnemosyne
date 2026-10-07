"""Diagnostic fixture: browser() output is capped at ~4000 chars (tail kept).

``browser(code)`` returns the code's stdout to the navigator, but the harness
truncates that text to roughly 4000 characters and keeps the TAIL when it
overflows. This module is a tiny, side-effect-free fixture used to sanity-check
that behaviour; it is not imported by the product or by other helpers.

Practical consequence: when reading a large page or file, never rely on one big
print. Slice explicitly (e.g. ``t[:1900]`` and ``t[-1900:]``) so nothing
important is silently dropped.
"""

PROBE = "0123456789" * 600  # 6000 chars: comfortably over the ~4000-char cap
