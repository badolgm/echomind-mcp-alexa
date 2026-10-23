"""Retrieved evidence and deterministic narration for the recall engine.

Pure domain layer (standard library only): turns a stored observation into a
transport-agnostic :class:`Evidence`, and renders a human answer **only** from
evidence that was actually retrieved — never from a model. When nothing was
retrieved the narrator abstains instead of inventing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.services.context import ContextItem

_SNIPPET_LIMIT = 120
_MAX_LINES = 3

_ABSTENTION: dict[str, str] = {
    "es": "No tengo registros que respondan a esa pregunta.",
    "en": "I have no records that answer that question.",
}


@dataclass(frozen=True, slots=True)
class Evidence:
    """One recalled proof, independent of how it was stored."""

    record_id: str
    ts: float
    location: str = ""
    labels: tuple[str, ...] = ()
    risk: str = ""
    confidence: float = 0.0
    snippet: str = ""
    camera_id: str | None = None
    zone: str | None = None

    @classmethod
    def from_record(
        cls, record: object, *, confidence: float | None = None
    ) -> Evidence:
        """Build evidence from any record-shaped object.

        Attributes are read with ``getattr`` so this stays in the domain layer
        without importing the storage model.
        """
        detections = getattr(record, "detections", ()) or ()
        labels: list[str] = []
        scores: list[float] = []
        for item in detections:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if label and label not in labels:
                labels.append(label)
            scores.append(_number(item.get("confidence"), 0.0))
        snippet = str(getattr(record, "model_analysis", "") or "")
        if not snippet:
            snippet = ", ".join(labels)
        return cls(
            record_id=str(getattr(record, "id", "") or ""),
            ts=float(getattr(record, "timestamp", 0.0) or 0.0),
            location=str(getattr(record, "location", "") or ""),
            labels=tuple(labels),
            risk=str(getattr(record, "risk", "") or ""),
            confidence=round(
                (
                    confidence
                    if confidence is not None
                    else (max(scores) if scores else 0.0)
                ),
                4,
            ),
            snippet=truncate_snippet(snippet),
            camera_id=_optional_text(getattr(record, "camera_id", None)),
            zone=_optional_text(getattr(record, "zone", None)),
        )


@dataclass(frozen=True, slots=True)
class RecallTrace:
    """Auditable link between a plan, the operations ran and the proof kept."""

    lang: str
    plan: dict[str, object]
    ops_executed: tuple[dict[str, object], ...] = ()
    evidence_ids: tuple[str, ...] = ()
    relations: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class RecallResult:
    """Final answer: narration, the evidence behind it and its trace."""

    utterance: str
    evidence: tuple[Evidence, ...]
    trace: RecallTrace
    lang: str
    is_error: bool = False
    context: tuple[ContextItem, ...] = ()
    context_utterance: str = ""


def _number(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _optional_text(value: object) -> str | None:
    """Normalize optional text metadata, treating blanks as absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def truncate_snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    """Collapse whitespace and cut a snippet to ``limit`` characters."""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def format_relative_time(timestamp: float, now: float, lang: str = "es") -> str:
    """Human elapsed time, using the same thresholds as the V1 narration."""
    delta = max(0.0, now - timestamp)
    if lang == "en":
        if delta < 60:
            return "a few seconds ago"
        minutes = int(delta // 60)
        if delta < 3600:
            return "1 minute ago" if minutes == 1 else f"{minutes} minutes ago"
        hours = int(delta // 3600)
        if delta < 86400:
            return "1 hour ago" if hours == 1 else f"{hours} hours ago"
        days = int(delta // 86400)
        if delta < 604800:
            return "1 day ago" if days == 1 else f"{days} days ago"
        weeks = int(delta // 604800)
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"

    if delta < 60:
        return "hace unos segundos"
    minutes = int(delta // 60)
    if delta < 3600:
        return "hace 1 minuto" if minutes == 1 else f"hace {minutes} minutos"
    hours = int(delta // 3600)
    if delta < 86400:
        return "hace 1 hora" if hours == 1 else f"hace {hours} horas"
    days = int(delta // 86400)
    if delta < 604800:
        return "hace 1 día" if days == 1 else f"hace {days} días"
    weeks = int(delta // 604800)
    return "hace 1 semana" if weeks == 1 else f"hace {weeks} semanas"


def render_abstention(*, lang: str) -> str:
    """The answer given when there is nothing to recall."""
    return _ABSTENTION.get(lang, _ABSTENTION["es"])


def render_utterance(evidence: Sequence[Evidence], *, lang: str, now: float) -> str:
    """Narrate retrieved evidence, deterministically and without invention."""
    ordered = tuple(evidence)
    if not ordered:
        return render_abstention(lang=lang)
    english = lang == "en"
    lines: list[str] = []
    for item in ordered[:_MAX_LINES]:
        subject = ", ".join(item.labels) if item.labels else item.snippet
        if not subject:
            subject = "record" if english else "registro"
        when = format_relative_time(item.ts, now, lang)
        if item.location:
            preposition = "at" if english else "en"
            lines.append(f"{subject} {preposition} {item.location}, {when}.")
        else:
            lines.append(f"{subject}, {when}.")
    return " ".join(lines)
