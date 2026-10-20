"""Event anchoring (A6c): resolving "the moment of X" from stored evidence.

Pure domain layer (standard library only), duck-typed like
:mod:`memory_spatial` so it works on ``MemoryRecord`` and on bare stand-ins
alike.

Anchoring is what makes the contextual questions answerable: "what happened
*before the fall*" needs the fall's timestamp before it can build a window.
The rule is deliberately closed and deterministic:

* the anchor is the **most recent** record carrying ``label``
* ties break on ``id``, descending, so the winner never depends on insertion
  order
* the number of matching records is carried as ``candidates``, so an ambiguous
  anchor is visible in the trace instead of silently resolved
* **no match means no anchor**, and without an anchor there is no contextual
  answer — the caller abstains rather than approximating
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnchorRef:
    """The resolved moment an anchored query is built around."""

    record_id: str
    ts: float
    label: str
    location: str
    camera_id: str | None = None
    zone: str | None = None
    candidates: int = 1


def anchor_from_record(record: object, *, label: str, candidates: int) -> AnchorRef:
    """Project one record into an anchor, reading only what it carries."""
    return AnchorRef(
        record_id=str(getattr(record, "id", "") or ""),
        ts=float(getattr(record, "timestamp", 0.0) or 0.0),
        label=label,
        location=str(getattr(record, "location", "") or ""),
        camera_id=_optional_text(getattr(record, "camera_id", None)),
        zone=_optional_text(getattr(record, "zone", None)),
        candidates=max(1, int(candidates)),
    )


def resolve_anchor(records: Iterable[object], *, label: str) -> AnchorRef | None:
    """Most recent record carrying ``label``, or ``None`` when there is none."""
    matches = [record for record in records if _carries_label(record, label)]
    if not matches:
        return None
    matches.sort(key=_order_key, reverse=True)
    return anchor_from_record(matches[0], label=label, candidates=len(matches))


def _carries_label(record: object, label: str) -> bool:
    detections = getattr(record, "detections", ()) or ()
    for item in detections:
        if isinstance(item, dict) and str(item.get("label") or "") == label:
            return True
    return False


def _order_key(record: object) -> tuple[float, str]:
    return (
        float(getattr(record, "timestamp", 0.0) or 0.0),
        str(getattr(record, "id", "") or ""),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
