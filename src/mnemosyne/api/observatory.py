"""Read-only observatory API: sessions, events and the live SSE stream.

The observatory is a *reader* of the `sessions` / `events` tables: it never
drives the agents. The stream tails `events` by id, so a reconnect resumes
exactly where it stopped (`Last-Event-ID`), and replay is the same data with a
cursor instead of a live offset.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from mnemosyne.config import get_config
from mnemosyne.db import Database

router = APIRouter(prefix="/api/obs", tags=["observatory"])

#: tail interval of the SSE stream (SQLite is local: 400 ms is responsive
#: enough and keeps the writer cost near zero)
POLL_S = 0.4
#: comment frame sent on an idle stream so proxies/browsers keep it open
KEEPALIVE_S = 15.0


def _connect() -> Database:
    return Database(get_config().db_file())


def _decode(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value


def _session(row: dict) -> dict:
    out = dict(row)
    out["meta"] = _decode(out.get("meta"))
    out["notable"] = bool(out.get("notable"))
    return out


def _event(row: dict) -> dict:
    out = dict(row)
    out["payload"] = _decode(out.get("payload"))
    return out


@router.get("/sessions")
def list_sessions(
    limit: Annotated[int, Query(ge=1, le=500)] = 80,
    before: str | None = None,
    family: str | None = None,
    include_silent: bool = False,
) -> dict:
    """Sessions, newest first. Silent runs are hidden unless asked for."""
    db = _connect()
    try:
        rows = db.list_sessions(
            limit=limit, before=before, include_silent=include_silent, family=family
        )
        return {
            "sessions": [_session(row) for row in rows],
            "latest_event_id": db.max_event_id(),
        }
    finally:
        db.close()


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    db = _connect()
    try:
        row = db.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        return _session(row)
    finally:
        db.close()


@router.get("/sessions/{session_id}/events")
def get_events(
    session_id: str,
    after: int | None = None,
    upto: int | None = None,
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
) -> dict:
    """The session's whole timeline (for replay) or a slice of it."""
    db = _connect()
    try:
        rows = db.list_events(session_id, after=after, upto=upto, limit=limit)
        return {"events": [_event(row) for row in rows]}
    finally:
        db.close()


@router.get("/artifacts/{name}")
def get_artifact(name: str):
    """Serve a screenshot copied from the (ephemeral) agent /tmp directory."""
    base = (Path(os.environ.get("MNEMOSYNE_DATA_DIR", "data")) / "obs-artifacts").resolve()
    path = (base / name).resolve()
    if path.parent != base or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path)


@router.get("/stream")
async def stream(request: Request, after: int = 0, session: str | None = None):
    """SSE tail of the event log (global, or one session).

    `after` / `Last-Event-ID` give the starting cursor: the frontend can load
    history over REST, then subscribe from the last id it saw.
    """
    last_event_id = request.headers.get("last-event-id")
    if last_event_id and last_event_id.isdigit():
        after = max(after, int(last_event_id))
    db = _connect()

    async def generate():
        cursor = after
        idle = 0.0
        try:
            while True:
                if await request.is_disconnected():
                    break
                rows = db.events_after(cursor, session_id=session, limit=300)
                if rows:
                    idle = 0.0
                    for row in rows:
                        cursor = int(row["id"])
                        data = json.dumps(_event(row), default=str)
                        yield f"id: {cursor}\ndata: {data}\n\n"
                else:
                    idle += POLL_S
                    if idle >= KEEPALIVE_S:
                        idle = 0.0
                        yield ": keep-alive\n\n"
                await asyncio.sleep(POLL_S)
        finally:
            db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
