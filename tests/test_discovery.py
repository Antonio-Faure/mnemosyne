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
