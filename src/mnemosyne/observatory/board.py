"""The two operator Kanbans: Le Résolveur and L'Atelier.

This is a read-only projection of the task/request tables. It does not drive
anything: the agents keep their mailbox/supervisor semantics. The board exists
to answer *where is the work?* without opening a session timeline.

Vocabulary (docs/NOMENCLATURE.md):
- une résolution = a resolver task (one sentence);
- une demande de source = one `resolver_requests` row;
- une mission de source = the coder/browser task referenced by that request.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mnemosyne.db import Database

BOARDS = ("resolver", "atelier")

COLUMN_LABELS = {
    "queued": "En file",
    "running": "En cours",
    "waiting": "En attente",
    "done": "Terminé",
    "failed": "Échec",
}

RESOLVER_OUTCOMES = {
    "match": "Match",
    "partial": "Partiel",
    "no_match": "Abstention",
    "ambiguous": "Ambigu",
    "technique": "Technique",
    "budget": "Budget",
    "cancelled": "Annulé",
}

MISSION_OUTCOMES = {
    "source_added": "Source ajoutée",
    "already_covered": "Déjà couverte",
    "refused": "Refusée",
    "no_source": "Sans source",
    "access_denied": "Accès refusé",
    "technique": "Technique",
    "abandon": "Abandon",
    "cancelled": "Annulé",
}

WAITING_LABELS = {
    "operator": "Opérateur",
    "sources": "Sources",
    "email": "E-mail",
    "access": "Accès",
}

WAITING_ORDER = ("operator", "sources", "email", "access")
RESOLVER_DONE_ORDER = ("match", "partial", "no_match", "ambiguous")
RESOLVER_FAILED_ORDER = ("technique", "budget", "cancelled")
MISSION_DONE_ORDER = ("source_added", "already_covered", "refused", "no_source")
MISSION_FAILED_ORDER = ("access_denied", "technique", "abandon", "cancelled")


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _payload(task: dict) -> dict:
    return _json(task.get("payload"), {})


def _fmt_time(seconds: Any) -> str:
    try:
        total = max(0, int(round(float(seconds or 0))))
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _short(text: str, limit: int = 170) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _resolver_text(task: dict) -> tuple[str, str, float | None]:
    """(phrase, segment_id, start_s) from the frozen task payload."""
    payload = _payload(task)
    source = payload.get("corpus") or payload.get("label") or {}
    segment = source.get("segment") or {}
    text = str(source.get("text") or segment.get("text") or "").strip()
    segment_id = str(payload.get("segment_id") or source.get("id") or "")
    start_s = source.get("start_s", segment.get("start_s"))
    if not text:
        for line in str(task.get("objective") or "").splitlines():
            if line.startswith("Phrase :"):
                text = line.split(":", 1)[1].strip()
                break
    return text or "Résolution sans phrase", segment_id, start_s


def _resolver_segment(task: dict) -> str:
    return _resolver_text(task)[1]


def _is_budget(text: str) -> bool:
    lowered = text.casefold()
    return any(
        token in lowered
        for token in ("budget", "quota", "rate limit", "429", "insufficient_quota")
    )


def _is_access_refusal(text: str) -> bool:
    lowered = text.casefold()
    return any(
        token in lowered
        for token in ("accès refusé", "access denied", "403", "401", "refus d'accès")
    )


def _is_access_wait(text: str) -> bool:
    lowered = text.casefold()
    return any(
        token in lowered
        for token in (
            "attente d'accès",
            "attente de l'accès",
            "waiting for access",
            "demande d'accès",
            "en attente d'accès",
        )
    )


def _task_text(task: dict) -> str:
    return " ".join(
        str(task.get(name) or "") for name in ("note", "objective", "payload")
    )


def _mission_outcome(task: dict, requests: list[dict]) -> str | None:
    status = str(task.get("status") or "")
    if status == "cancelled":
        return "cancelled"
    text = _task_text(task) + " " + " ".join(
        str(request.get("note") or "") for request in requests
    )
    if status == "failed":
        if _is_access_refusal(text):
            return "access_denied"
        if "abandon" in text.casefold():
            return "abandon"
        return "technique"
    if status == "done":
        lowered = text.casefold()
        if any(
            token in lowered
            for token in ("déjà couverte", "déjà couvert", "already covered", "déjà présent")
        ):
            return "already_covered"
        if any(
            token in lowered
            for token in ("sans source", "aucune source", "no source", "introuvable")
        ):
            return "no_source"
        if any(
            token in lowered
            for token in ("refus", "droits réservés", "all rights reserved", "droits")
        ):
            return "refused"
        return "source_added"
    return None


def _mission_waiting(
    db: Database, task: dict, requests: list[dict]
) -> tuple[list[dict], str | None]:
    waiting: list[dict] = []
    asks = db.pending_asks_for(int(task["id"]))
    if asks:
        waiting.append(
            {
                "type": "operator",
                "label": WAITING_LABELS["operator"],
                "detail": _short(asks[-1].get("question") or "", 140),
            }
        )
    email_wait = db.task_email_wait(int(task["id"]))
    if email_wait is not None:
        waiting.append(
            {
                "type": "email",
                "label": WAITING_LABELS["email"],
                "detail": _short(
                    email_wait.get("reason") or email_wait.get("subject_contains") or "",
                    140,
                ),
            }
        )
    text = _task_text(task) + " " + " ".join(
        str(request.get("note") or "") for request in requests
    )
    if _is_access_wait(text):
        waiting.append(
            {
                "type": "access",
                "label": WAITING_LABELS["access"],
                "detail": "accès à obtenir",
            }
        )
    return waiting, (waiting[0]["type"] if waiting else None)


def _column_for(status: str, waiting: list[dict], outcome: str | None) -> str:
    if status == "pending":
        return "queued"
    if status == "running":
        return "waiting" if waiting else "running"
    if status == "done":
        return "done"
    if status in ("failed", "cancelled"):
        return "failed"
    return "failed" if outcome else "running"


def _resolver_outcome(result: dict | None) -> str:
    if result is None:
        return "ambiguous"
    status = str(result.get("status") or "")
    return status if status in RESOLVER_OUTCOMES else "ambiguous"


def _resolver_agents(task: dict) -> list[str]:
    return ["resolver"]


def _mission_agents(db: Database, task: dict) -> list[str]:
    agents = db.task_activation_agents(int(task["id"]))
    start = str(task.get("start_agent") or "")
    if start and start not in agents:
        agents.insert(0, start)
    return agents or [start]


def _mission_title(task: dict, requests: list[dict]) -> str:
    payload = _payload(task)
    name = str(payload.get("source_name") or "").strip()
    if not name and requests:
        name = str(requests[0].get("source_name") or "").strip()
    if not name:
        name = str(payload.get("source_id") or "").strip()
    if not name and requests:
        name = str(requests[0].get("source_id") or "").strip()
    return f"Source : {name}" if name else f"Mission #{task['id']}"


def _mission_resolutions(
    db: Database, requests: list[dict], *, limit: int = 8
) -> list[dict]:
    out: list[dict] = []
    seen: set[int] = set()
    for request in requests:
        task_id = request.get("resolver_task_id")
        if task_id is None or int(task_id) in seen:
            continue
        seen.add(int(task_id))
        task = db.get_task(int(task_id))
        if task is None:
            continue
        text, segment_id, _ = _resolver_text(task)
        result = db.get_resolver_result(int(task_id))
        outcome = _resolver_outcome(result) if task.get("status") == "done" else None
        status = task.get("status")
        if status == "running" and (
            db.pending_asks_for(int(task_id))
            or db.pending_resolver_requests(int(task_id))
        ):
            status = "waiting"
        out.append(
            {
                "task_id": int(task_id),
                "title": _short(text, 120),
                "segment_id": segment_id,
                "status": status,
                "outcome": outcome,
                "outcome_label": RESOLVER_OUTCOMES.get(outcome or ""),
            }
        )
        if len(out) >= limit:
            break
    return out


def _mission_card(
    db: Database,
    task: dict,
    requests: list[dict],
    *,
    include_resolutions: bool = True,
) -> dict:
    waiting, waiting_on = _mission_waiting(db, task, requests)
    outcome = _mission_outcome(task, requests)
    column = _column_for(str(task.get("status") or ""), waiting, outcome)
    agents = _mission_agents(db, task)
    resolutions = _mission_resolutions(db, requests) if include_resolutions else []
    source_id = next(
        (str(request.get("source_id")) for request in requests if request.get("source_id")),
        "",
    )
    resolution_count = len({r.get("resolver_task_id") for r in requests})
    return {
        "id": f"mission:{task['id']}",
        "kind": "mission",
        "task_id": int(task["id"]),
        "title": _mission_title(task, requests),
        "subtitle": (
            f"demandée par {resolution_count} résolution"
            + ("s" if resolution_count > 1 else "")
            if requests
            else "aucune résolution liée"
        ),
        "source_id": source_id,
        "agent": task.get("start_agent"),
        "current_agent": agents[-1] if agents else task.get("start_agent"),
        "agents": agents,
        "status": task.get("status"),
        "column": column,
        "waiting_on": waiting_on,
        "waiting": waiting,
        "outcome": outcome,
        "outcome_label": MISSION_OUTCOMES.get(outcome or ""),
        "created_at": task.get("created_at"),
        "updated_at": task.get("last_activation_at")
        or task.get("finished_at")
        or task.get("created_at"),
        "request_count": len({r.get("resolver_task_id") for r in requests}),
        "resolutions": resolutions,
        "missions": [],
        "source_count": None,
        "links": {
            "session": f"task:{task['id']}",
            "resolver_requests": [request["id"] for request in requests if request.get("id")],
            "resolutions": [r["task_id"] for r in resolutions],
        },
    }


def _resolver_card(
    db: Database,
    task: dict,
    *,
    mission_cards: dict[int, dict],
) -> dict:
    text, segment_id, start_s = _resolver_text(task)
    requests = db.resolver_requests(int(task["id"]))
    pending_requests = [
        request for request in requests if request.get("status") in ("pending", "running")
    ]
    waiting: list[dict] = []
    asks = db.pending_asks_for(int(task["id"]))
    if asks:
        waiting.append(
            {
                "type": "operator",
                "label": WAITING_LABELS["operator"],
                "detail": _short(asks[-1].get("question") or "", 140),
            }
        )
    if pending_requests:
        detail_parts: list[str] = []
        for request in pending_requests:
            mission = mission_cards.get(int(request.get("agent_task_id") or 0))
            if mission is None:
                detail_parts.append(f"mission #{request.get('agent_task_id')}")
                continue
            suffix = ""
            if mission["waiting_on"] == "email":
                suffix = " — e-mail"
            elif mission["waiting_on"] == "access":
                suffix = " — accès"
            elif mission["waiting_on"] == "operator":
                suffix = " — opérateur"
            detail_parts.append(f"mission #{mission['task_id']}{suffix}")
        waiting.append(
            {
                "type": "sources",
                "label": WAITING_LABELS["sources"],
                "detail": " ; ".join(detail_parts),
            }
        )

    status = str(task.get("status") or "")
    result = db.get_resolver_result(int(task["id"]))
    outcome = _resolver_outcome(result) if status == "done" else None
    if status == "failed":
        outcome = "budget" if _is_budget(_task_text(task)) else "technique"
    elif status == "cancelled":
        outcome = "cancelled"
    column = _column_for(status, waiting, outcome)

    missions = []
    for request in requests:
        mission = mission_cards.get(int(request.get("agent_task_id") or 0))
        if mission is not None:
            missions.append(
                {
                    "task_id": mission["task_id"],
                    "source_id": mission.get("source_id"),
                    "status": mission["status"],
                    "column": mission["column"],
                    "waiting_on": mission["waiting_on"],
                    "outcome": mission["outcome"],
                    "outcome_label": mission["outcome_label"],
                    "agent": mission["current_agent"],
                }
            )
        else:
            missions.append(
                {
                    "task_id": request.get("agent_task_id"),
                    "source_id": request.get("source_id"),
                    "status": request.get("status"),
                    "column": None,
                    "waiting_on": None,
                    "outcome": None,
                    "outcome_label": None,
                    "agent": None,
                }
            )

    subtitle = segment_id
    if start_s is not None:
        subtitle = f"{segment_id} · {_fmt_time(start_s)}" if segment_id else _fmt_time(start_s)

    return {
        "id": f"resolution:{task['id']}",
        "kind": "resolution",
        "task_id": int(task["id"]),
        "title": _short(text),
        "subtitle": subtitle,
        "source_id": None,
        "agent": "resolver",
        "current_agent": "resolver",
        "agents": _resolver_agents(task),
        "status": status,
        "column": column,
        "waiting_on": waiting[0]["type"] if waiting else None,
        "waiting": waiting,
        "outcome": outcome,
        "outcome_label": RESOLVER_OUTCOMES.get(outcome or ""),
        "created_at": task.get("created_at"),
        "updated_at": task.get("last_activation_at")
        or task.get("finished_at")
        or task.get("created_at"),
        "request_count": None,
        "source_count": len(requests),
        "missions": missions,
        "resolutions": [],
        "links": {
            "session": f"task:{task['id']}",
            "resolver_requests": [request["id"] for request in requests if request.get("id")],
            "missions": [mission["task_id"] for mission in missions if mission.get("task_id")],
        },
    }


def _columns(board: str) -> list[dict]:
    return [
        {"id": column, "label": label}
        for column, label in COLUMN_LABELS.items()
    ]


def _summarise(column: dict, cards: list[dict]) -> dict:
    column = dict(column)
    column["cards"] = cards
    column["count"] = len(cards)
    if column["id"] == "waiting":
        counts: dict[str, int] = {}
        for card in cards:
            for item in card.get("waiting") or []:
                key = item.get("type")
                if key:
                    counts[key] = counts.get(key, 0) + 1
        keys = list(WAITING_ORDER) + sorted(set(counts) - set(WAITING_ORDER))
        column["summary"] = [
            {"key": key, "label": WAITING_LABELS.get(key, key), "count": counts[key]}
            for key in keys
            if counts.get(key)
        ]
    elif column["id"] in ("done", "failed"):
        counts = {}
        for card in cards:
            key = card.get("outcome")
            if key:
                counts[key] = counts.get(key, 0) + 1
        kind = cards[0].get("kind") if cards else "resolution"
        if column["id"] == "done":
            order = MISSION_DONE_ORDER if kind == "mission" else RESOLVER_DONE_ORDER
        else:
            order = MISSION_FAILED_ORDER if kind == "mission" else RESOLVER_FAILED_ORDER
        labels = MISSION_OUTCOMES if kind == "mission" else RESOLVER_OUTCOMES
        keys = list(order) + sorted(set(counts) - set(order))
        column["summary"] = [
            {
                "key": key,
                "label": next(
                    (card.get("outcome_label") for card in cards if card.get("outcome") == key),
                    labels.get(key, key),
                ),
                "count": counts[key],
            }
            for key in keys
            if counts.get(key)
        ]
    else:
        column["summary"] = []
    return column


def build_board(db: Database, board: str) -> dict:
    """Build one of the two read-only boards."""
    if board not in BOARDS:
        raise ValueError(f"unknown board: {board}")
    requests = db.all_resolver_requests()
    groups: dict[int, list[dict]] = {}
    for request in requests:
        task_id = request.get("agent_task_id")
        if task_id is None:
            continue
        groups.setdefault(int(task_id), []).append(request)

    mission_cards: dict[int, dict] = {}
    for task_id, task_requests in groups.items():
        task = db.get_task(task_id)
        if task is None:
            continue
        mission_cards[task_id] = _mission_card(db, task, task_requests)

    if board == "resolver":
        tasks = [
            task
            for task in db.list_tasks(limit=2000)
            if task.get("start_agent") == "resolver"
        ]
        cards = [_resolver_card(db, task, mission_cards=mission_cards) for task in tasks]
    else:
        cards = list(mission_cards.values())

    columns = _columns(board)
    by_column = {column["id"]: [] for column in columns}
    for card in cards:
        by_column.setdefault(card["column"], []).append(card)
    for column in columns:
        column_cards = by_column.get(column["id"], [])
        column_cards.sort(
            key=lambda card: str(card.get("updated_at") or ""), reverse=True
        )

    return {
        "board": board,
        "generated_at": datetime.now(UTC).isoformat(),
        "columns": [
            _summarise(column, by_column.get(column["id"], [])) for column in columns
        ],
        "cards": cards,
    }
