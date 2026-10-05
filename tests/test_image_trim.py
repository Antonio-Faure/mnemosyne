"""Zen refuses a request carrying more than 30 images.

A browser session adds one screenshot per step; the client caps every outgoing
request to the `max_request_images` most recent ones (older images become a
text placeholder) so a long session never trips the provider limit.
"""

from __future__ import annotations

from mnemosyne.browser.stirrup_client import IMAGE_PLACEHOLDER, trim_request_images


def _image(idx: int) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{idx}"}}


def _messages(count: int) -> list[dict]:
    return [{"role": "user", "content": [f"step {i}", _image(i)]} for i in range(count)]


def test_request_under_the_cap_is_untouched() -> None:
    messages = _messages(3)
    assert trim_request_images(messages, max_images=12) == messages


def test_oldest_images_become_placeholders() -> None:
    out = trim_request_images(_messages(20), max_images=12)
    images = [
        p for m in out for p in m["content"] if isinstance(p, dict) and p.get("type") == "image_url"
    ]
    placeholders = [
        p
        for m in out
        for p in m["content"]
        if isinstance(p, dict) and p.get("text") == IMAGE_PLACEHOLDER
    ]
    assert len(images) == 12
    assert len(placeholders) == 8
    # the 12 kept are the most recent ones (0..7 dropped)
    kept = [p["image_url"]["url"].rsplit(",", 1)[1] for p in images]
    assert kept == [str(i) for i in range(8, 20)]
    # roles and order are preserved
    assert [m["role"] for m in out] == ["user"] * 20


def test_string_content_is_left_alone() -> None:
    messages = [{"role": "tool", "content": "ok"}, {"role": "user", "content": [_image(0)]}]
    out = trim_request_images(messages, max_images=1)
    assert out[0] == {"role": "tool", "content": "ok"}
