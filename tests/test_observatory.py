"""Observatory store + API: sessions, events, replay and live stream.

No agent is launched here: the observatory only reads/writes its own tables.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from mnemosyne.db import Database
from mnemosyne.observatory import events


def test_task_becomes_a_session_with_its_creation_event(config):
    db = Database(config.db_file())
    task_id = db.enqueue_task(
        "browser", "MISSION WARMUP — test\nseconde ligne", payload={"kind": "warmup"}
    )
    session = db.get_session(f"task:{task_id}")
    assert session["family"] == "task"
    assert session["type"] == "warmup"
    assert session["title"] == "MISSION WARMUP — test"
    assert session["status"] == "pending"
    assert session["notable"] == 1
    assert [r["kind"] for r in db.list_events(f"task:{task_id}")] == [
        "session.created"
    ]
    db.close()


def test_status_changes_are_mirrored_and_terminal_closes_the_session(config):
    db = Database(config.db_file())
    task_id = db.enqueue_task("coder", "mission")
    db.set_task_status(task_id, "running")
    db.set_task_status(task_id, "done", note="fini")
    session = db.get_session(f"task:{task_id}")
    assert session["status"] == "done"
    assert session["ended_at"]
    kinds = [r["kind"] for r in db.list_events(f"task:{task_id}")]
    assert kinds == ["session.created", "task.status", "task.status"]
    db.close()


def test_job_runs_are_sessions_and_silent_runs_are_hidden(config):
    db = Database(config.db_file())
    db.open_job_session(7, "harvest")
    db.close_job_session(
        7, status="done", activity="harvest gallica « usine » → 3 nouveaux"
    )
    db.open_job_session(8, "agency")
    db.close_job_session(8, status="done", activity=None)

    visible = {s["id"] for s in db.list_sessions()}
    assert "job:7" in visible
    assert "job:8" not in visible, "un run silencieux ne pollue pas la sidebar"
    assert {s["id"] for s in db.list_sessions(include_silent=True)} >= {
        "job:7",
        "job:8",
    }

    session = db.get_session("job:7")
    assert session["title"].startswith("harvest gallica")
    assert session["ended_at"]
    assert session["notable"] == 1
    db.close()


def test_record_is_bound_to_the_current_context(config):
    db = Database(config.db_file())
    task_id = db.enqueue_task("browser", "mission")
    session_id = events.task_session_id(task_id)

    events.record("outside")  # no context: silent no-op
    token = events.use_context(db, session_id, "browser")
    try:
        events.record("tool.call", {"name": "navigate"})
        events.record("llm.call", {"model": "m"})
    finally:
        events.reset_context(token)

    kinds = [r["kind"] for r in db.list_events(session_id)]
    assert kinds[-2:] == ["tool.call", "llm.call"]
    db.close()


def test_mailbox_messages_become_events(config):
    from mnemosyne.agents.mailbox import Mailbox

    db = Database(config.db_file())
    task_id = db.enqueue_task("browser", "mission")
    mailbox = Mailbox(db)
    token = events.use_context(db, events.task_session_id(task_id), "browser")
    try:
        mailbox.post(
            "browser", "coder", "peux-tu brancher le connecteur ?", task_id=task_id
        )
    finally:
        events.reset_context(token)

    kinds = [r["kind"] for r in db.list_events(f"task:{task_id}")]
    assert "mailbox.message" in kinds
    db.close()


@pytest.mark.asyncio
async def test_scheduler_titles_the_job_session_with_activity(config, monkeypatch):
    """`_activity` titles the job session and never leaks into the job payload."""
    from mnemosyne.heartbeat import scheduler as sch
    from mnemosyne.heartbeat.jobs import HANDLERS
    from mnemosyne.models import Job

    async def handler(ctx, job):
        return {"interval_s": 999999, "_activity": "test run: 3 things"}

    monkeypatch.setitem(HANDLERS, "testkind", handler)
    heartbeat = sch.Heartbeat(config)
    try:
        job_id = heartbeat.engine.db.enqueue(
            Job(
                kind="testkind",
                payload={"interval_s": 999999},
                run_at="2000-01-01T00:00:00+00:00",
            )
        )
        claimed = heartbeat.engine.db.claim_due_jobs("2100-01-01T00:00:00+00:00", 5)
        job = next(j for j in claimed if j.id == job_id)
        await heartbeat._run_job(job)

        session = heartbeat.engine.db.get_session(f"job:{job_id}")
        assert session["title"] == "test run: 3 things"
        assert session["status"] == "done"
        assert session["notable"] == 1

        end = next(
            row
            for row in heartbeat.engine.db.list_events(f"job:{job_id}")
            if row["kind"] == "job.end"
        )
        assert "duration_s" in json.loads(end["payload"])

        again = heartbeat.engine.db.claim_due_jobs("2200-01-01T00:00:00+00:00", 5)
        assert len(again) == 1
        assert "_activity" not in again[0].payload
        assert again[0].payload["interval_s"] == 999999
    finally:
        await heartbeat.aclose()


def test_backfill_creates_sessions_for_past_tasks(config):
    db = Database(config.db_file())
    task_id = db.enqueue_task("browser", "old warmup", payload={"kind": "warmup"})
    db.set_task_status(task_id, "done", note="ok")
    # simulate a task that predates the observatory
    with db._lock:
        db._conn.execute("DELETE FROM events")
        db._conn.execute("DELETE FROM sessions")
        db._conn.commit()

    from mnemosyne.observatory.backfill import backfill

    result = backfill(db, days=365)
    assert result["tasks"] == 1
    session = db.get_session(f"task:{task_id}")
    assert session["title"] == "old warmup"
    kinds = [row["kind"] for row in db.list_events(f"task:{task_id}")]
    assert kinds[0] == "session.created"
    assert "task.status" in kinds
    assert backfill(db, days=365)["tasks"] == 0, "idempotent"
    db.close()


def test_tool_results_are_emitted_once(config):
    from mnemosyne.browser.stirrup_client import UsageSink, _CompletionsProxy

    db = Database(config.db_file())
    task_id = db.enqueue_task("browser", "mission")
    token = events.use_context(db, events.task_session_id(task_id), "browser")
    try:
        proxy = _CompletionsProxy(None, UsageSink())
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "navigate", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "page loaded"},
        ]
        proxy._record_tool_results(messages)
        proxy._record_tool_results(messages)  # deduplicated per activation
        # a NEW activation replays the conversation: the DB dedupes on call_id
        _CompletionsProxy(None, UsageSink())._record_tool_results(messages)
    finally:
        events.reset_context(token)

    rows = [
        row
        for row in db.list_events(f"task:{task_id}")
        if row["kind"] == "tool.result"
    ]
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload"])
    assert payload["name"] == "navigate"
    assert "page loaded" in payload["preview"]
    db.close()


def _client(config, monkeypatch) -> TestClient:
    import mnemosyne.api.observatory as obs
    from mnemosyne.api.app import create_app

    monkeypatch.setattr(obs, "get_config", lambda: config)
    return TestClient(create_app())


def test_api_lists_and_serves_sessions(config, monkeypatch):
    db = Database(config.db_file())
    task_id = db.enqueue_task(
        "browser", "MISSION WARMUP — test", payload={"kind": "warmup"}
    )
    db.close()

    client = _client(config, monkeypatch)
    listing = client.get("/api/obs/sessions").json()
    assert f"task:{task_id}" in [s["id"] for s in listing["sessions"]]
    assert listing["latest_event_id"] >= 1

    detail = client.get(f"/api/obs/sessions/task:{task_id}").json()
    assert detail["type"] == "warmup"
    assert detail["event_count"] == 1

    rows = client.get(f"/api/obs/sessions/task:{task_id}/events").json()["events"]
    assert rows[0]["kind"] == "session.created"

    assert client.get("/api/obs/sessions/task:999").status_code == 404
