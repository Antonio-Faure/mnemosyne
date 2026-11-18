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
    *,
    context: str | None = None,
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
    if context:
        objective += f"\n{context}\n"
    objective += (
        "\nCherche dans la meta API, fais valider le candidat par l'opérateur, "
        "et demande aux agents les sources manquantes si nécessaire.\n"
        "Le catalogue des sources déjà connues est disponible via "
        "`catalog_inventory` : consulte-le avant de demander une source."
    )
    return objective


def enqueue_sentence(db: Database, segment_id: str) -> tuple[int | None, str]:
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

    context = None
    if corpus is not None and (corpus.get("video") or {}).get("id"):
        from mnemosyne.resolver.context import video_context_card

        context = video_context_card(db, segment_id)

    task_id = db.enqueue_task(
        "resolver", build_objective(segment_id, entry, text, context=context), payload=payload
    )
    return task_id, source
