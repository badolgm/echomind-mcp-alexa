"""Response Intent Adapter (A7D): route a question to the answer it deserves.

Pure domain layer (standard library only). The recall engine already computes
far more than it used to say: counts, directional slices, timelines, camera
groups, aggregate labels and relation digests. This module decides **which**
of those a question should be answered with, so the synthesizer dispatches to
the right renderer instead of narrating the raw evidence — and two different
questions stop producing the same answer.

Two entry points, one fixed precedence order:

* :func:`resolve_intent` reads a natural-language question **plus** the
  structural signals the planner already extracted (aggregation, relations,
  direction) — the text refines what the structure alone cannot separate,
  such as *related events* (case 5) versus *cameras* (case 6).
* :func:`derive_intent` reads only the structural signals, for plans built
  directly (low-level tests, programmatic callers) where no question text
  exists. It reproduces the pre-A7D policy order exactly.

Both return the first matching :class:`ResponseIntent`, so behaviour is
deterministic and adding a use case means adding a rule, never editing a
branch.
"""

from __future__ import annotations

import re
from enum import Enum


class ResponseIntent(Enum):
    """The single shape of answer one recall question asks for."""

    COUNT = "count"
    BEFORE = "before"
    AFTER = "after"
    LAST_SEEN_PLACE = "last_seen_place"
    TIMELINE = "timeline"
    CAMERAS = "cameras"
    RELATIONS = "relations"
    SPATIAL = "spatial"
    SUMMARY = "summary"
    FALLBACK = "fallback"


_WHERE_RE = re.compile(r"\b(?:d[oó]nde|where)\b")
_SEE_VERB_RE = re.compile(
    r"\b(?:vi|viste|vio|vimos|vieron|estuvo|estuvieron|estaba|estaban|"
    r"last\s+saw|last\s+seen|saw|seen|see)\b"
)
_CAMERAS_RE = re.compile(r"\bc[aá]maras?\b|\bcameras?\b")
_RELATIONS_RE = re.compile(r"\brelacionad|\brelaci[oó]n\b|\brelated\b")


def resolve_intent(
    *,
    text: str,
    aggregation: str | None = None,
    relations: tuple[str, ...] = (),
    direction: str | None = None,
    has_count: bool = False,
) -> ResponseIntent:
    """Map a question and its structural signals onto one response intent."""
    normalized = " ".join(str(text).lower().split())
    relation_set = frozenset(relations)

    if has_count or aggregation == "count":
        return ResponseIntent.COUNT
    if "before_after" in relation_set and direction in ("before", "after"):
        return ResponseIntent.AFTER if direction == "after" else ResponseIntent.BEFORE
    if _WHERE_RE.search(normalized) and _SEE_VERB_RE.search(normalized):
        return ResponseIntent.LAST_SEEN_PLACE
    if "timeline" in relation_set:
        return ResponseIntent.TIMELINE
    if _CAMERAS_RE.search(normalized):
        return ResponseIntent.CAMERAS
    if _RELATIONS_RE.search(normalized):
        return ResponseIntent.RELATIONS
    if "correlation" in relation_set:
        return ResponseIntent.CAMERAS
    if "spatial" in relation_set:
        return ResponseIntent.SPATIAL
    if aggregation == "summary":
        return ResponseIntent.SUMMARY
    return ResponseIntent.FALLBACK


def derive_intent(
    *,
    aggregation: str | None = None,
    relations: tuple[str, ...] = (),
    direction: str | None = None,
    has_count: bool = False,
) -> ResponseIntent:
    """Same precedence as :func:`resolve_intent`, without any question text."""
    relation_set = frozenset(relations)

    if has_count or aggregation == "count":
        return ResponseIntent.COUNT
    if "before_after" in relation_set and direction in ("before", "after"):
        return ResponseIntent.AFTER if direction == "after" else ResponseIntent.BEFORE
    if "timeline" in relation_set:
        return ResponseIntent.TIMELINE
    if "correlation" in relation_set:
        return ResponseIntent.CAMERAS
    if "spatial" in relation_set:
        return ResponseIntent.SPATIAL
    if aggregation == "summary":
        return ResponseIntent.SUMMARY
    return ResponseIntent.FALLBACK
