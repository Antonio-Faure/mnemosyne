"""The two Kanbans: resolver resolutions and Atelier source missions."""

from __future__ import annotations

from mnemosyne.db import Database
from mnemosyne.observatory.board import build_board


def _db(config) -> Database:
    return Database(config.db_file())


def _resolver_task(db: Database, text: str, segment: str) -> int:
    return db.enqueue_task(
        "resolver",
        f"Phrase : {text}\nSegment : {segment}",
        payload={
            "kind": "resolver",
            "segment_id": segment,
            "corpus": {
                "id": segment,
                "text": text,
                "start_s": 12.0,
                "video": {"id": "video", "title": "Vidéo"},
            },
        },
    )


def _mission(db: Database, source: str) -> int:
    return db.enqueue_task(
        "browser",
        f"Source {source}",
        payload={
            "kind": "resolver_source",
            "source_id": source,
            "source_name": source.replace("_", " ").title(),
        },
    )


def test_resolver_board_columns_outcomes_and_dependencies(config):
    db = _db(config)
    try:
        queued = _resolver_task(db, "Une phrase en file.", "yt_v_1")
        running = _resolver_task(db, "Une phrase active.", "yt_v_2")
        db.set_task_status(running, "running", agent="resolver")
        waiting_operator = _resolver_task(db, "Une phrase qui attend.", "yt_v_3")
        db.set_task_status(waiting_operator, "running", agent="resolver")
        db.create_ask(
            "ask1", waiting_operator, "resolver", "Quelle image ?",
            [{"label": "A"}, {"label": "B"}],
        )
        waiting_sources = _resolver_task(db, "Une phrase sans source.", "yt_v_4")
        db.set_task_status(waiting_sources, "running", agent="resolver")

        mission_wait = _mission(db, "musee_x")
        db.set_task_status(mission_wait, "running", agent="browser")
        db.create_email_wait(
            mission_wait, "browser", subject_contains="accès", reason="attente accès"
        )
        mission_done = _mission(db, "archive_y")
        db.set_task_status(mission_done, "done", agent="coder", note="Source ajoutée.")

        db.create_resolver_request(
            waiting_sources,
            sentence_id="yt_v_4",
            source_id="musee_x",
            source_name="Musée X",
            agent_task_id=mission_wait,
        )
        db.create_resolver_request(
            waiting_sources,
            sentence_id="yt_v_4",
            source_id="archive_y",
            source_name="Archive Y",
            agent_task_id=mission_done,
        )
        db.complete_resolver_requests_for_agent_task(mission_done, status="done")

        done = _resolver_task(db, "Une phrase trouvée.", "yt_v_5")
        db.set_task_status(done, "done", agent="resolver")
        db.record_resolver_result(
            done, segment_id="yt_v_5", status="match", asset_id="a1", evidence="ok"
        )
        failed = _resolver_task(db, "Une phrase en échec.", "yt_v_6")
        db.set_task_status(failed, "failed", agent="resolver", note="quota 429")
        cancelled = _resolver_task(db, "Une phrase annulée.", "yt_v_7")
        db.set_task_status(cancelled, "cancelled", agent="resolver")

        board = build_board(db, "resolver")
        columns = {column["id"]: column for column in board["columns"]}
        cards = {card["task_id"]: card for card in board["cards"]}

        assert columns["queued"]["count"] == 1
        assert columns["running"]["count"] == 1
        assert columns["waiting"]["count"] == 2
        assert columns["done"]["count"] == 1
        assert columns["failed"]["count"] == 2

        assert cards[queued]["column"] == "queued"
        assert cards[waiting_operator]["waiting_on"] == "operator"
        assert cards[waiting_sources]["waiting_on"] == "sources"
        assert cards[waiting_sources]["source_count"] == 2
        assert "mission #" in cards[waiting_sources]["waiting"][0]["detail"]
        assert "e-mail" in cards[waiting_sources]["waiting"][0]["detail"]
        assert cards[done]["outcome"] == "match"
        assert cards[done]["outcome_label"] == "Match"
        assert cards[failed]["outcome"] == "budget"
        assert cards[cancelled]["outcome"] == "cancelled"

        assert columns["done"]["summary"][0]["label"] == "Match"
        assert columns["failed"]["summary"]
    finally:
        db.close()


def test_atelier_board_groups_missions_and_resolutions(config):
    db = _db(config)
    try:
        resolution = _resolver_task(db, "Une phrase.", "yt_v_1")
        db.set_task_status(resolution, "running", agent="resolver")
        mission = _mission(db, "musee_x")
        db.set_task_status(mission, "running", agent="browser")
        db.create_resolver_request(
            resolution,
            sentence_id="yt_v_1",
            source_id="musee_x",
            source_name="Musée X",
            agent_task_id=mission,
        )

        board = build_board(db, "atelier")
        assert board["board"] == "atelier"
        assert len(board["cards"]) == 1
        card = board["cards"][0]
        assert card["task_id"] == mission
        assert card["title"] == "Source : Musee X"
        assert card["request_count"] == 1
        assert card["resolutions"][0]["task_id"] == resolution
        assert card["links"]["resolver_requests"]
        assert card["links"]["resolutions"] == [resolution]
        assert card["column"] == "running"

        # An email wait moves the mission to En attente / E-mail.
        db.create_email_wait(mission, "browser", reason="attente accès")
        board = build_board(db, "atelier")
        card = board["cards"][0]
        assert card["column"] == "waiting"
        assert card["waiting_on"] == "email"
    finally:
        db.close()
