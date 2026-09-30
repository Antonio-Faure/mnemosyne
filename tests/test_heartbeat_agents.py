"""The heartbeat agents must import lazily: core works without the browser extra."""

import pytest
import yaml

from mnemosyne.engine import Engine
from mnemosyne.heartbeat.jobs import JobContext, handle_onboard
from mnemosyne.journal import Control, Journal
from mnemosyne.models import AuthKind, Job
from mnemosyne.notify import Notifier


def _ctx(config) -> JobContext:
    engine = Engine(config)
    engine.catalog.sync()
    return JobContext(
        config=config,
        engine=engine,
        journal=Journal(config.journal_path),
        control=Control(config.control_path),
        notifier=Notifier(config.notify.telegram),
    )


@pytest.mark.asyncio
async def test_onboard_skips_keyless_provider(config):
    ctx = _ctx(config)  # gallica is auth=none
    try:
        result = await handle_onboard(ctx, Job(kind="onboard", payload={"source_id": "gallica"}))
        assert result is None
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_onboard_skips_when_browser_unreachable(config, sources_dir):
    (sources_dir / "acme.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "acme_archives",
                "name": "Acme Archives",
                "protocol": "email",
                "base_url": "https://archives.acme.example",
                "auth": "api_key",
            }
        ),
        encoding="utf-8",
    )
    ctx = _ctx(config)
    try:
        assert ctx.engine.catalog.get("acme_archives").auth == AuthKind.API_KEY
        # No Chrome available in tests -> handler must bail out without importing stirrup.
        result = await handle_onboard(
            ctx, Job(kind="onboard", payload={"source_id": "acme_archives"})
        )
        assert result is None
    finally:
        await ctx.engine.aclose()
