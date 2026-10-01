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


def test_recover_stale_jobs_releases_a_dead_claimer(config):
    """A killed heartbeat must free its job immediately, not after the TTL."""
    import json
    import socket
    import time

    db = Database(config.db_file())
    job_id = db.enqueue(
        __import__("mnemosyne.models", fromlist=["Job"]).Job(
            kind="agency", payload={}, run_at="2000-01-01T00:00:00+00:00"
        )
    )
    claimed = db.claim_due_jobs("2100-01-01T00:00:00+00:00", 5)
    assert [j.id for j in claimed] == [job_id]
    db._conn.execute(
        "UPDATE jobs SET locked_by = ? WHERE id = ?",
        (
            json.dumps({"who": "job:agency", "pid": 4_000_000, "host": socket.gethostname()}),
            job_id,
        ),
    )
    db._conn.commit()

    # a cutoff far in the future would normally keep it running
    far_future = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(4_000_000_000))
    assert db.recover_stale_jobs(far_future) == 1
    assert db._conn.execute(
        "SELECT state FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()["state"] == "pending"
    db.close()
