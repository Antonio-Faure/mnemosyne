"""One canonical click path: the harness guard refuses redundant/parallel clicks."""

from __future__ import annotations

import pytest

pytest.importorskip("stirrup")
pytest.importorskip("openai")

from mnemosyne.agents.browser_agent import _HARNESS_GUARD  # noqa: E402


def _env() -> tuple[dict, dict]:
    calls = {"click": 0, "js": 0, "cdp": 0}

    def click_at_xy(x, y, button="left", clicks=1):
        calls["click"] += 1
        return "clicked"

    def js(expression, target_id=None):
        calls["js"] += 1
        return "js"

    def cdp(method, *args, **kwargs):
        calls["cdp"] += 1
        return "cdp"

    ns: dict = {"click_at_xy": click_at_xy, "js": js, "cdp": cdp}
    exec(_HARNESS_GUARD, ns)  # noqa: S102 - execute the guard exactly as shipped
    return ns, calls


def test_first_click_passes():
    ns, calls = _env()
    assert ns["click_at_xy"](100, 200) == "clicked"
    assert calls["click"] == 1


def test_repeat_click_same_spot_is_refused():
    ns, _ = _env()
    ns["click_at_xy"](100, 200)
    with pytest.raises(RuntimeError, match="double clic"):
        ns["click_at_xy"](101, 199)


def test_click_elsewhere_is_allowed():
    ns, calls = _env()
    ns["click_at_xy"](100, 200)
    ns["click_at_xy"](400, 700)
    assert calls["click"] == 2


def test_js_can_read_but_not_submit():
    ns, _ = _env()
    assert ns["js"]("document.title") == "js"
    with pytest.raises(RuntimeError, match=r"js\(\) interdit"):
        ns["js"]("document.querySelector('button').click()")
    with pytest.raises(RuntimeError):
        ns["js"]("form.requestSubmit()")
    with pytest.raises(RuntimeError):
        ns["js"]("el.dispatchEvent(new MouseEvent('click'))")


def test_cdp_can_observe_but_not_click():
    ns, _ = _env()
    assert ns["cdp"]("Runtime.evaluate", expression="1") == "cdp"
    with pytest.raises(RuntimeError, match=r"cdp\(\) interdit"):
        ns["cdp"]("Input.dispatchMouseEvent", type="mousePressed")
