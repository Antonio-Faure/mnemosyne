"""Click helpers that survive a non-visible / occluded Chrome window.

House rule: clicks go through `click_at_xy` only (a physical click). But when
Chrome's window is occluded or minimized (outerWidth/outerHeight == 0), Chrome
silently drops synthetic input: `click_at_xy` returns with no error and the DOM
does not change. That reads as "the button is broken" when the real problem is
the invisible window.

Fix that held up in practice: wrap the click with TEMPORARY focus emulation.
`Emulation.setFocusEmulationEnabled` makes the page accept input as if focused
WITHOUT foregrounding the window -- so we never steal the user's screen and we
never call `activate_tab` (a timeout is not permission to foreground Chrome).
Always disable it again afterwards.

    from click_visible import click_at_css, click_label, find_label

    click_at_css(320, 480)            # physical click at CSS pixel (x, y)
    click_label("Obtenir un lien")    # find a button/link by text, click center
    click_label("Sign in", exact=True)
    find_label("Download")            # -> {'x','y','text'} or None (no click)

Coordinates are CSS pixels (the same space `click_at_xy` expects). Check
`js("window.devicePixelRatio")` before turning screenshot pixels into clicks.
"""
from __future__ import annotations

import json

from browser_harness.helpers import click_at_xy, js, cdp

_DEFAULT_TAGS = [
    "button",
    "a",
    "[role=button]",
    "input[type=submit]",
    "input[type=button]",
    "label",
    "summary",
]


def _focus_emu(enabled: bool) -> None:
    try:
        cdp("Emulation.setFocusEmulationEnabled", enabled=enabled)
    except Exception:
        pass


def click_at_css(x: float, y: float) -> None:
    """Physical click at CSS (x, y), robust to an occluded/minimized window."""
    _focus_emu(True)
    try:
        click_at_xy(int(x), int(y))
    finally:
        _focus_emu(False)


def find_label(text, exact: bool = False, tags=None):
    """Return {'x','y','text'} center (CSS px) of the first matching element.

    `text` matches a button/link's visible label (innerText / value /
    aria-label). Substring match by default; set `exact=True` for equality.
    Only on-screen elements (with a non-zero box) are considered. Returns None
    if nothing matches -- observation only, no click.
    """
    sel = ",".join(tags or _DEFAULT_TAGS)
    code = """
    (function(){
      var t = %s;
      var exact = %s;
      var sel = %s;
      var els = Array.from(document.querySelectorAll(sel));
      function label(e){
        var v = (e.innerText || e.value || e.getAttribute('aria-label') || '').trim();
        return v.replace(/\\s+/g,' ');
      }
      for (var i=0;i<els.length;i++){
        var e = els[i];
        var v = label(e);
        var hit = exact ? (v === t) : (v.toLowerCase().indexOf(t.toLowerCase()) !== -1);
        if (!hit) continue;
        var r = e.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue;
        if (r.bottom < 0 || r.top > (window.innerHeight || 0)) continue;
        return {x: r.left + r.width / 2, y: r.top + r.height / 2, text: v};
      }
      return null;
    })()
    """ % (json.dumps(str(text)), "true" if exact else "false", json.dumps(sel))
    info = js(code)
    if isinstance(info, dict) and "x" in info:
        return info
    return None


def click_label(text, exact: bool = False, tags=None) -> bool:
    """Find a button/link by visible text and click its center.

    Returns True if an element was found and clicked, False otherwise.
    """
    info = find_label(text, exact=exact, tags=tags)
    if not info:
        return False
    click_at_css(info["x"], info["y"])
    return True
