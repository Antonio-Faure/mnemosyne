"""Global video context for the resolver.

A sentence alone cannot tell the resolver what the video is about: the same
words can refer to a person, a place or a period introduced ten minutes
earlier. This module builds two layers:

* a **stored context card** (summary, outline, period/places/entities),
  generated once per video with the configured LLM;
* a **local window** of surrounding transcript segments, inserted directly in
  the task objective. The resolver also has tools to read/search more when the
  window is not enough.
"""

from __future__ import annotations

import json
from typing import Any

from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.llm import LlmClient
from mnemosyne.logger import get_logger

log = get_logger("resolver.context")

#: The window inserted in every task. ~15 segments each side is roughly 2–3
#: minutes of speech: enough to resolve pronouns and local references.
DEFAULT_BEFORE = 15
DEFAULT_AFTER = 15
#: Hard cap of the card, so a verbose outline cannot crowd out the tools.
MAX_CARD_CHARS = 6000
#: The summary prompt receives the whole transcript up to this size.
MAX_TRANSCRIPT_CHARS = 80000


def format_time(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _video_of(payload: dict) -> dict:
    video = payload.get("video")
    return video if isinstance(video, dict) else {}


def segment_label(payload: dict) -> str:
    """The short numeric suffix of yt_<video>_<index>, for compact display."""
    segment_id = str(payload.get("id") or "")
    suffix = segment_id.rsplit("_", 1)[-1]
    return suffix if suffix.isdigit() else segment_id


def _duration_of(segments: list[dict]) -> float:
    return max((float(segment.get("end_s") or 0.0) for segment in segments), default=0.0)


def video_context_card(
    db: Database,
    segment_id: str,
    *,
    before: int = DEFAULT_BEFORE,
    after: int = DEFAULT_AFTER,
    include_summary: bool = True,
    max_chars: int = MAX_CARD_CHARS,
) -> str:
    """The context block inserted in the task objective (and returned by the tool)."""
    payload = db.get_resolver_corpus(segment_id)
    if payload is None:
        return ""

    video = _video_of(payload)
    video_id = str(video.get("id") or "")
    segments = (
        db.list_resolver_corpus_for_video(video_id) if video_id else [payload]
    )
    if not segments:
        segments = [payload]

    index = next(
        (i for i, segment in enumerate(segments) if segment.get("id") == segment_id),
        None,
    )
    if index is None:
        # Golden segment or stale id: find the closest start time.
        start = float(payload.get("start_s") or 0.0)
        index = min(
            range(len(segments)),
            key=lambda i: abs(float(segments[i].get("start_s") or 0.0) - start),
        )

    def render(window_before: int, window_after: int) -> str:
        start_i = max(0, index - window_before)
        end_i = min(len(segments), index + window_after + 1)
        window = segments[start_i:end_i]
        lines: list[str] = ["Contexte vidéo :"]
        title = str(video.get("title") or "").strip() or video_id or "(titre inconnu)"
        duration = _duration_of(segments)
        lines.append(f"- Titre : {title}")
        if duration:
            lines.append(f"- Durée : {format_time(duration)}")

        context = db.get_video_context(video_id) if video_id and include_summary else None
        if context:
            summary = str(context.get("summary") or "").strip()
            if summary:
                lines.append(f"- Résumé : {summary}")
            meta = context.get("meta") or {}
            if meta.get("period"):
                lines.append(f"- Période : {meta['period']}")
            if meta.get("places"):
                lines.append(f"- Lieux : {', '.join(map(str, meta['places']))}")
            if meta.get("entities"):
                lines.append(f"- Entités : {', '.join(map(str, meta['entities']))}")
            outline = context.get("outline") or []
            if outline:
                lines.append("- Plan :")
                for i, part in enumerate(outline, 1):
                    start = format_time(part.get("start_s"))
                    end = format_time(part.get("end_s"))
                    label = str(part.get("title") or "").strip()
                    lines.append(f"  {i}. {start}–{end} — {label}")
        else:
            lines.append(
                "- Résumé global : non généré — utilise `video_context` et "
                "`search_transcript` pour situer la phrase."
            )

        current = payload
        lines.append(
            f"- Position : [{segment_label(current)}] — {index + 1}/{len(segments)} — "
            f"{format_time(current.get('start_s'))} à {format_time(current.get('end_s'))}"
        )
        lines.append("- Extrait autour de la phrase :")
        for segment in window:
            marker = "  ← phrase" if segment.get("id") == segment_id else ""
            lines.append(
                f"  - [{segment_label(segment)}] "
                f"{format_time(segment.get('start_s'))} — "
                f"{str(segment.get('text') or '').strip()}{marker}"
            )
        lines.append(
            "La transcription est un contexte, jamais une preuve pour l'image : "
            "ne la cite pas comme provenance."
        )
        return "\n".join(lines)

    text = render(before, after)
    while len(text) > max_chars and (before > 0 or after > 0):
        before = max(0, before - 3)
        after = max(0, after - 3)
        text = render(before, after)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _extract_json(raw: str) -> dict:
    """Parse the model output, tolerating code fences or a short preamble."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("réponse sans objet JSON")
    return json.loads(text[start : end + 1])


def _normalise_outline(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    outline: list[dict] = []
    for part in raw:
        if not isinstance(part, dict):
            continue
        try:
            start = float(part.get("start_s") or 0.0)
            end = float(part.get("end_s") or start)
        except (TypeError, ValueError):
            continue
        title = str(part.get("title") or "").strip()
        summary = str(part.get("summary") or "").strip()
        if not title and not summary:
            continue
        outline.append(
            {
                "start_s": max(0.0, min(start, end)),
                "end_s": max(0.0, max(start, end)),
                "title": title[:160],
                "summary": summary[:600],
            }
        )
    outline.sort(key=lambda part: part["start_s"])
    return outline[:12]


async def generate_video_context(
    config: Config,
    db: Database,
    video_id: str,
    *,
    force: bool = False,
    client: Any | None = None,
) -> dict:
    """Build and store the global context card for one video.

    The summary is generated once (or again with ``force``); the transcript is
    never sent to the resolver by default. ``client`` is injectable for tests.
    """
    existing = db.get_video_context(video_id)
    if existing and not force:
        return existing

    segments = db.list_resolver_corpus_for_video(video_id)
    if not segments:
        raise ValueError(f"aucun segment pour la vidéo {video_id!r}")

    title = str(_video_of(segments[0]).get("title") or "").strip() or video_id
    duration = _duration_of(segments)
    transcript = "\n".join(
        f"[{format_time(segment.get('start_s'))}] "
        f"{str(segment.get('text') or '').strip()}"
        for segment in segments
    )
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript = (
            transcript[:half]
            + "\n[… transcription tronquée pour le résumé …]\n"
            + transcript[-half:]
        )

    prompt = f"""Tu prépares la fiche de contexte globale d'une vidéo historique.
Cette fiche sera donnée à un agent qui doit illustrer UNE phrase de la vidéo
par une image d'archive. Il doit comprendre le sujet, l'époque, les lieux et
les entités avant de chercher.

Vidéo : {title}
Durée : {format_time(duration)}

Transcription complète (timecodes) :
{transcript}

Réponds uniquement par un objet JSON valide, sans markdown :
{{
  "summary": "150 à 250 mots : sujet, période, lieux, personnes/entités, thèse et arc narratif",
  "meta": {{
    "period": "période historique principale",
    "places": ["lieu 1", "lieu 2"],
    "entities": ["personne, organisation, événement ou notion clé"]
  }},
  "outline": [
    {{"start_s": 0, "end_s": 120, "title": "titre court de la partie", "summary": "une phrase"}}
  ]
}}

Contraintes : 6 à 10 parties, timecodes croissants et cohérents avec la durée,
n'invente rien, ne cite pas la transcription comme preuve d'une image."""

    client = client or LlmClient(config, session="video-context")
    raw = await client.chat(
        [
            {
                "role": "system",
                "content": (
                    "Tu résumes des transcriptions historiques pour un moteur de "
                    "recherche d'images d'archives. Tu réponds en JSON strict."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    data = _extract_json(raw)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise ValueError("le modèle n'a pas fourni de résumé")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    outline = _normalise_outline(data.get("outline"))

    db.upsert_video_context(
        video_id,
        title=title,
        duration_s=duration or None,
        summary=summary,
        outline=outline,
        meta=meta,
        model=getattr(client, "model", None),
    )
    log.info(
        "video context generated: %s (%d chars, %d parts, model %s)",
        video_id,
        len(summary),
        len(outline),
        getattr(client, "model", "?"),
    )
    stored = db.get_video_context(video_id)
    if stored is None:  # pragma: no cover - defensive, upsert just wrote it
        raise RuntimeError("contexte vidéo non enregistré")
    return stored
