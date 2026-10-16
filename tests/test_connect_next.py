"""`mnemosyne connect-next` : gel de l'onboarding et hôtes déjà couverts.

Le gel (`dev.sources_freeze`) est le maître : aucune tâche, quel que soit
l'appelant. Et une découverte périmée (hôte déjà au catalogue) est close au lieu
de produire une source en double (cf. digi_vatlib vs vatican).
"""

from __future__ import annotations

from types import SimpleNamespace

from mnemosyne.cli import _cmd_connect_next
from mnemosyne.db import Database
from mnemosyne.discovery.models import DiscoveryRecord


def _save(db: Database, host: str, url: str) -> DiscoveryRecord:
    record = DiscoveryRecord.build(host, url=url, protocol="iiif")
    db.save_discoveries([record])
    return record


def _status(config, record_id: str) -> str:
    db = Database(config.db_file())
    try:
        return next(r.status for r in db.list_discoveries() if r.id == record_id)
    finally:
        db.close()


def test_freeze_refuses_and_touches_nothing(config, monkeypatch):
    monkeypatch.setattr("mnemosyne.cli.get_config", lambda: config)
    config.dev.sources_freeze = True

    db = Database(config.db_file())
    record = _save(db, "nouveau.example", "https://nouveau.example/")
    db.close()

    assert _cmd_connect_next(None) == 1

    db = Database(config.db_file())
    assert db.list_tasks() == []
    db.close()
    assert _status(config, record.id) == "new", "le gel ne consomme pas la découverte"


def test_a_known_host_is_closed_without_a_task(config, monkeypatch):
    """Une découverte périmée (hôte déjà au catalogue) ne refait pas une source."""
    monkeypatch.setattr("mnemosyne.cli.get_config", lambda: config)
    config.dev.sources_freeze = False

    db = Database(config.db_file())
    # the fixture's catalog declares gallica on example.invalid
    record = _save(db, "example.invalid", "https://example.invalid/collections")
    db.close()

    assert _cmd_connect_next(None) == 0

    db = Database(config.db_file())
    assert db.list_tasks() == []
    db.close()
    assert _status(config, record.id) == "connected"


def test_a_fresh_host_posts_the_coder_task(config, monkeypatch):
    monkeypatch.setattr("mnemosyne.cli.get_config", lambda: config)
    config.dev.sources_freeze = False
    seen: list[str] = []

    async def fake_run_agency(cfg, task, *, start=None, journal=None, vault_get=None):
        seen.append(task)
        return SimpleNamespace(turns=[{"branch": "agent/frais-iiif"}], stop_reason="no_pending")

    monkeypatch.setattr("mnemosyne.agents.supervisor.run_agency", fake_run_agency)
    monkeypatch.setattr(
        "mnemosyne.agents.supervisor._branch_has_commits", lambda cfg, branch: True
    )

    db = Database(config.db_file())
    record = _save(db, "frais.example", "https://frais.example/")
    db.close()

    assert _cmd_connect_next(None) == 0
    assert len(seen) == 1
    assert "frais.example" in seen[0]
    assert "config/sources/" in seen[0]
    assert _status(config, record.id) == "connected"
