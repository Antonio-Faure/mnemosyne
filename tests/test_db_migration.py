"""Database migration: the legacy `biagent_task_id` column becomes `agent_task_id`."""

from __future__ import annotations

import sqlite3

from mnemosyne.db import Database


def _old_database(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE resolver_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolver_task_id INTEGER NOT NULL,
            sentence_id TEXT,
            source_id TEXT,
            source_name TEXT,
            biagent_task_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            note TEXT
        );
        CREATE INDEX idx_resolver_requests_biagent
            ON resolver_requests(biagent_task_id, status);
        INSERT INTO resolver_requests
            (resolver_task_id, source_id, biagent_task_id, status, created_at)
        VALUES (7, 'src', 42, 'pending', '2026-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()


def test_biagent_task_id_is_renamed_to_agent_task_id(tmp_path):
    path = tmp_path / "old.db"
    _old_database(path)

    db = Database(path)
    try:
        cols = {row["name"] for row in db._conn.execute("PRAGMA table_info(resolver_requests)")}
        assert "agent_task_id" in cols
        assert "biagent_task_id" not in cols
        row = db._conn.execute(
            "SELECT resolver_task_id, agent_task_id FROM resolver_requests"
        ).fetchone()
        assert row["resolver_task_id"] == 7
        assert row["agent_task_id"] == 42
        indexes = {row["name"] for row in db._conn.execute("PRAGMA index_list(resolver_requests)")}
        assert "idx_resolver_requests_agent_task" in indexes
        assert "idx_resolver_requests_biagent" not in indexes
    finally:
        db.close()

    # idempotent: opening the migrated database again must not fail
    db = Database(path)
    db.close()
