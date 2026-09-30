from mnemosyne.db import Database
from mnemosyne.models import Job, JobState


def _db(config) -> Database:
    return Database(config.db_file())


def test_has_open_job_singleton_and_source(config):
    db = _db(config)
    db.enqueue(Job(kind="journal", payload={"interval_s": 900}))
    # singleton: matched without a source_id
    assert db.has_open_job("journal") is True
    assert db.has_open_job("warmup") is False

    db.enqueue(Job(kind="harvest", payload={"source_id": "gallica", "limit": 20}))
    assert db.has_open_job("harvest", "gallica") is True
    assert db.has_open_job("harvest", "wikidata") is False
    db.close()


def test_prune_duplicate_jobs_keeps_one(config):
    db = _db(config)
    for _ in range(5):
        db.enqueue(Job(kind="journal", payload={"interval_s": 900}))
    assert db.count_jobs(JobState.PENDING) == 5

    removed = db.prune_duplicate_jobs()
    assert removed == 4
    assert db.count_jobs(JobState.PENDING) == 1
    db.close()


def test_prune_done_jobs_by_date(config):
    db = _db(config)
    db.enqueue(Job(kind="x", payload={}, run_at="2020-01-01T00:00:00+00:00"))
    job_id = db.claim_due_jobs("2100-01-01T00:00:00+00:00", 10)[0].id
    db.complete_job(job_id)
    assert db.count_jobs(JobState.DONE) == 1
    removed = db.prune_done_jobs("2021-01-01T00:00:00+00:00")
    assert removed == 1
    db.close()
