from datetime import UTC, datetime, timedelta

from mnemosyne.config import ReputationConfig
from mnemosyne.db import Database
from mnemosyne.reputation import Governor


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


def test_warmup_phase_by_age(config):
    db = Database(config.db_file())
    gov = Governor(ReputationConfig(account_created_at=_ago(0)), db)
    assert gov.phase().outbound_per_day == 0
    assert gov.allowed("outbound") is False
    assert gov.allowed("harvest") is True
    gov.record("harvest", 50)
    assert gov.allowed("harvest") is False
    db.close()


def test_trusted_account_has_no_warmup(config):
    db = Database(config.db_file())
    gov = Governor(ReputationConfig(account_created_at=None), db)
    assert gov.age_days() is None
    assert gov.phase().outbound_per_day == 20
    assert gov.allowed("outbound") is True
    db.close()


def test_block_sets_cooldown(config):
    db = Database(config.db_file())
    gov = Governor(ReputationConfig(block_cooldown_s=300), db)
    assert gov.status()["pressure"] == 1.0
    db.close()
