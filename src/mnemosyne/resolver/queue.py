"""Enqueue resolver work for one sentence — shared by the CLI and the feeder.

Keeping the objective and the payload in one place means a sentence enqueued by
the automatic feeder (idle resolver) is indistinguishable from a manual
`mnemosyne resolve enqueue`: same message, same claim, same duplicate guard.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.db import Database


def catalog_inventory(config) -> list[dict[str, Any]]:
    """Every declared source, so the resolver never asks for one it has.

    Without this the resolver re-requested `gallica_bnf`, `wikimedia_commons`,
    `ina_fr`… because a thin search looked like missing coverage.
    """
    from mnemosyne.catalog import Catalog

    catalog = Catalog(config.sources_path, None)
    return [
        {"id": descriptor.id, "name": descriptor.name, "enabled": descriptor.enabled}
        for descriptor in catalog.load_descriptors()
    ]


def build_objective(
    segment_id: str,
    entry: dict[str, Any],
    text: str,
    sources: list[dict[str, Any]] | None = None,
) -> str:
    claim = entry.get("claim") or {}
    video = entry.get("video") or {}
    objective = (
        "Phrase historique à illustrer par le résolveur adversarial.\n"
        f"Segment : {segment_id}\n"
        f"Phrase : {text}\n"
    )
    if video.get("title") or video.get("url"):
        objective += (
            f"Vidéo : {video.get('title') or video.get('id') or ''}"
            + (f" — {video['url']}" if video.get("url") else "")
            + "\n"
        )
    if claim:
        objective += f"Claim : {claim}\n"
    objective += (
        "Cherche dans la meta API, fais valider le candidat par l'opérateur, "
        "et demande au biagent les sources manquantes si nécessaire."
    )
    if sources:
        objective += "\n\nCatalogue actuel (source_id — nom — état) :\n"
        objective += "\n".join(
            f"- {source['id']} — {source['name']} — "
            f"{'active' if source.get('enabled', True) else 'désactivée'}"
            for source in sorted(sources, key=lambda item: item["id"])
        )
        objective += (
            "\n\nUne source absente de cette liste peut être demandée via "
            "`request_source`. Une source présente, même désactivée, ne doit PAS "
            "être redemandée : utilise `catalog_search(source_ids=[...])` et "
            "signale le trou à l'opérateur."
        )
    return objective


def enqueue_sentence(
    db: Database, segment_id: str, *, sources: list[dict[str, Any]] | None = None
) -> tuple[int | None, str]:
    """Queue one resolver session for `segment_id` (golden preferred to corpus).

    Returns `(task_id, reason)`; `task_id` is None when the sentence is unknown
    or already open (`reason` then explains why).
    """
    existing = db.open_resolver_task(segment_id)
    if existing is not None:
        return None, f"phrase déjà en cours (tâche #{existing})"

    label = db.get_resolver_golden(segment_id)
    corpus = None
    if label is not None:
        text = (label.get("segment") or {}).get("text") or ""
        entry: dict[str, Any] = label
        source = "golden"
    else:
        corpus = db.get_resolver_corpus(segment_id)
        if corpus is None:
            return None, "segment inconnu (ni golden, ni corpus)"
        text = corpus.get("text") or ""
        entry = corpus
        source = "corpus"

    payload: dict[str, Any] = {
        "kind": "resolver",
        "segment_id": segment_id,
        "source": source,
    }
    if label is not None:
        payload["label"] = label
    if corpus is not None:
        payload["corpus"] = corpus
    task_id = db.enqueue_task(
        "resolver", build_objective(segment_id, entry, text, sources), payload=payload
    )
    return task_id, source
