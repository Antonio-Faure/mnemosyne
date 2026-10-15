import pytest

from mnemosyne.db import Database
from mnemosyne.discovery import WikidataIIIFDiscoverer, host_of, run_discovery

PAYLOAD = {
    "results": {
        "bindings": [
            {
                "host": {"value": "www.nga.gov"},
                "n": {"value": "127942"},
                "sample": {"value": "https://www.nga.gov/iiif/x/manifest"},
            },
            {
                "host": {"value": "gallica.bnf.fr"},
                "n": {"value": "63620"},
                "sample": {"value": "https://gallica.bnf.fr/iiif/ark:/12148/x/manifest.json"},
            },
            {"host": {"value": "not-a-host"}, "n": {"value": "5"}, "sample": {"value": ""}},
        ]
    }
}


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload

    async def get_json(self, url, **kwargs):
        return self.payload


def test_host_of():
    assert host_of("https://www.nga.gov/iiif/x") == "www.nga.gov"
    assert host_of("") == ""


@pytest.mark.asyncio
async def test_wikidata_iiif_discoverer_parses_and_skips_invalid():
    records = await WikidataIIIFDiscoverer().discover(FakeHttp(PAYLOAD), limit=10)
    hosts = {r.host for r in records}
    assert hosts == {"www.nga.gov", "gallica.bnf.fr"}  # "not-a-host" invalid
    nga = next(r for r in records if r.host == "www.nga.gov")
    assert nga.item_count == 127942
    assert nga.protocol == "iiif"
    assert nga.source == "wikidata:iiif_hosts"


@pytest.mark.asyncio
async def test_run_discovery_dedups():
    records = await run_discovery(FakeHttp(PAYLOAD), limit=10)
    assert len(records) == 2


def test_save_and_list_discoveries(config):
    from mnemosyne.discovery.models import DiscoveryRecord

    db = Database(config.db_file())
    recs = [
        DiscoveryRecord.build("a.example", url="https://a.example/", protocol="iiif"),
        DiscoveryRecord.build("b.example", url="https://b.example/", protocol="iiif"),
    ]
    assert db.save_discoveries(recs) == 2
    assert db.save_discoveries(recs) == 0  # idempotent
    assert db.count_discoveries() == 2
    assert {r.host for r in db.list_discoveries()} == {"a.example", "b.example"}
    db.close()


@pytest.mark.asyncio
async def test_discover_handler_is_a_silent_no_op_when_disabled(config, monkeypatch):
    """`discovery.enabled: false` : aucun scan, et pas de replanification."""
    from mnemosyne.engine import Engine
    from mnemosyne.heartbeat.jobs import JobContext, handle_discover
    from mnemosyne.journal import Control, Journal
    from mnemosyne.models import Job
    from mnemosyne.notify import Notifier

    async def _boom(*_args, **_kwargs):
        raise AssertionError("run_discovery ne doit pas être appelé")

    monkeypatch.setattr("mnemosyne.discovery.run_discovery", _boom)
    config.discovery.enabled = False

    engine = Engine(config)
    ctx = JobContext(
        config=config,
        engine=engine,
        journal=Journal(config.journal_path),
        control=Control(config.control_path),
        notifier=Notifier(config.notify.telegram),
    )
    try:
        out = await handle_discover(ctx, Job(kind="discover", payload={"interval_s": 86400}))
    finally:
        await engine.aclose()
    assert out == {"interval_s": None}, "le job ne doit pas se replanifier"
