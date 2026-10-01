"""Read the current page: text, title, links.

The browser agent reaches for these constantly; the harness only ships
low-level primitives, so they live here (mnemosyne house helper).
"""

from __future__ import annotations

from browser_harness.helpers import js


def read_page(max_chars: int = 4000) -> str:
    """Visible text of the current page (truncated)."""
    text = js("document.body ? document.body.innerText : ''") or ""
    text = str(text).strip()
    return text[:max_chars]


def page_title() -> str:
    return str(js("document.title") or "")


def list_links(limit: int = 60) -> list[str]:
    """First `limit` links as 'text -> href'."""
    raw = js(
        "Array.from(document.querySelectorAll('a[href]'))"
        f".slice(0, {int(limit)})"
        ".map(a => (a.innerText || '').trim().slice(0, 80) + ' -> ' + a.href)"
    )
    if isinstance(raw, str):
        return [line for line in raw.splitlines() if line.strip()]
    return [str(item) for item in (raw or [])]
