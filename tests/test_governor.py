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


def test_account_created_at_offset_is_honoured(config):
    """An ISO string with an offset must be converted, not re-labelled UTC."""
    from datetime import timedelta, timezone

    db = Database(config.db_file())
    created = datetime.now(UTC).astimezone(timezone(timedelta(hours=2))).isoformat()
    gov = Governor(ReputationConfig(account_created_at=created), db)
    assert gov.age_days() == 0
    db.close()


def test_per_source_rate_limit_sets_the_pacing_floor(config):
    db = Database(config.db_file())
    gov = Governor(ReputationConfig(domain_min_interval_s=1.0), db)
    gov.set_domain_interval("slow.example.org", 5.0)
    assert gov._wait_for("slow.example.org") == 5.0
    assert gov._wait_for("other.example.org") == 1.0
    db.close()


def test_pressure_is_per_domain_and_recovers(config):
    """One blocked host slows itself down; the rest of the catalog keeps pace."""
    import asyncio

    db = Database(config.db_file())
    gov = Governor(ReputationConfig(domain_min_interval_s=1.0, block_cooldown_s=300), db)

    asyncio.run(gov.report_block("gallica.bnf.fr"))
    assert gov._wait_for("gallica.bnf.fr") == 2.0
    assert gov._wait_for("other.example.org") == 1.0, "a global penalty would slow everything"

    gov.report_success("gallica.bnf.fr")
    assert gov._wait_for("gallica.bnf.fr") == 1.0, "a served request halves the penalty"

    asyncio.run(gov.report_block("gallica.bnf.fr"))
    asyncio.run(gov.report_block("gallica.bnf.fr"))
    assert gov.status()["pressure"] == 4.0
    assert gov.status()["pressure"] == 4.0
    assert gov.status()["pressure_by_domain"] == {"gallica.bnf.fr": 4.0}
    db.close()
