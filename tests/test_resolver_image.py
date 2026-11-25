"""Resolver image validation and the one-image-per-resolution registry."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from mnemosyne.db import Database
from mnemosyne.resolver.imagecheck import inspect_image, normalise_image_url


def _png(width: int = 800, height: int = 600) -> bytes:
    image = Image.new("RGB", (width, height), (20, 80, 140))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _client(payload: bytes, content_type: str = "image/png") -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": content_type, "content-length": str(len(payload))},
            content=payload,
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_normalise_image_url_strips_fragment():
    assert (
        normalise_image_url(" https://example.org/a.jpg#frag ")
        == "https://example.org/a.jpg"
    )


@pytest.mark.asyncio
async def test_inspect_image_reads_dimensions_and_preview():
    client = _client(_png())
    result = await inspect_image(
        "https://example.org/photo.png", client=client, min_side=10, min_bytes=10
    )
    await client.aclose()
    assert result["ok"] is True
    assert result["image_format"] == "PNG"
    assert (result["width"], result["height"]) == (800, 600)
    assert result["preview"]
    assert result["hard_failures"] == []


@pytest.mark.asyncio
async def test_inspect_image_refuses_a_non_image():
    client = _client(b"not an image", content_type="text/html")
    result = await inspect_image(
        "https://example.org/notice", client=client, min_side=10, min_bytes=1
    )
    await client.aclose()
    assert result["ok"] is False
    assert any("image" in failure for failure in result["hard_failures"])


@pytest.mark.asyncio
async def test_inspect_image_refuses_a_tiny_image():
    client = _client(_png(50, 50))
    result = await inspect_image(
        "https://example.org/icon.png", client=client, min_side=200, min_bytes=1
    )
    await client.aclose()
    assert result["ok"] is False
    assert any("trop petite" in failure for failure in result["hard_failures"])


def test_illustrations_are_unique_by_image_and_asset(config):
    db = Database(config.db_file())
    try:
        db.upsert_resolver_illustration(
            1,
            segment_id="yt_v_1",
            sentence="Phrase 1",
            context="Vidéo",
            image_url="https://example.org/a.jpg",
            image_context="Un derrick",
            asset_id="asset-a",
        )
        db.upsert_resolver_illustration(
            2,
            segment_id="yt_v_2",
            sentence="Phrase 2",
            context="Vidéo",
            image_url="https://example.org/b.jpg",
            image_context="Un puits",
            asset_id="asset-b",
        )
        first_illustration = db.get_resolver_illustration_by_url(
            "https://example.org/a.jpg"
        )
        assert first_illustration["sentence"] == "Phrase 1"
        assert db.get_resolver_illustration_by_asset("asset-b")["resolver_task_id"] == 2
        assert db.get_resolver_illustration_for_task(1)["asset_id"] == "asset-a"

        with pytest.raises(ValueError, match="déjà utilisée"):
            db.upsert_resolver_illustration(
                3,
                segment_id="yt_v_3",
                sentence="Phrase 3",
                context="Vidéo",
                image_url="https://example.org/a.jpg",
                image_context="La même image",
            )

        # The same resolution may replace its image.
        db.upsert_resolver_illustration(
            1,
            segment_id="yt_v_1",
            sentence="Phrase 1",
            context="Vidéo",
            image_url="https://example.org/c.jpg",
            image_context="Un autre derrick",
            asset_id="asset-c",
        )
        assert db.get_resolver_illustration_for_task(1)["image_url"].endswith("c.jpg")
    finally:
        db.close()


@pytest.mark.asyncio
async def test_inspect_image_retries_a_transient_403(monkeypatch):
    calls = {"n": 0}
    payload = _png()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, headers={"content-type": "text/html"}, content=b"no")
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": str(len(payload))},
            content=payload,
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("mnemosyne.resolver.imagecheck.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await inspect_image(
        "https://example.org/photo.png", client=client, min_side=10, min_bytes=10
    )
    await client.aclose()
    assert result["ok"] is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_inspect_image_reports_a_persistent_403(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, headers={"content-type": "text/html"}, content=b"no")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("mnemosyne.resolver.imagecheck.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await inspect_image(
        "https://example.org/photo.png", client=client, min_side=10, min_bytes=1
    )
    await client.aclose()
    assert result["ok"] is False
    assert "HTTP 403" in result["hard_failures"]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_inspect_image_uses_the_institution_fallback_url(monkeypatch):
    calls: list[str] = []
    payload = _png()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "/full/full/0/native.jpg" in str(request.url):
            return httpx.Response(403, headers={"content-type": "text/html"}, content=b"no")
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": str(len(payload))},
            content=payload,
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("mnemosyne.resolver.imagecheck.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await inspect_image(
        "https://gallica.bnf.fr/iiif/ark:/12148/x/f1/full/full/0/native.jpg",
        client=client,
        min_side=10,
        min_bytes=10,
    )
    await client.aclose()
    assert result["ok"] is True
    assert "1024" in result["final_url"]
    assert any("repli" in warning for warning in result["warnings"])
    assert len(calls) == 3
