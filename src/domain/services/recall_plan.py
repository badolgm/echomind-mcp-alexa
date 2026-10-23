"""Declarative recall plans: the composable replacement for a single intent.

Pure domain layer (standard library only). A plan states *what* must be
retrieved and *how* the pieces relate, so one question can express several
operations instead of exactly one.

A plan is assembled from slots (see ``src/domain/services/recall_planner``),
never by matching a whole question, so adding a use case means adding a table
row.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.services.response_intent import ResponseIntent


class RelationKind(Enum):
    """How the memories a plan retrieves are meant to be compared."""

    EPISODE = "episode"
    SPATIAL = "spatial"
    CORRELATION = "correlation"
    TIMELINE = "timeline"
    BEFORE_AFTER = "before_after"


class RetrieveKind(Enum):
    """One executable memory operation."""

    LAST_SEEN = "last_seen"
    SEARCH = "search"
    RANGE = "range"
    TOP = "top"
    AGGREGATE = "aggregate"
    CURRENT_STATE = "current_state"


class Aggregation(Enum):
    """Optional aggregation asked for over a window."""

    COUNT = "count"
    LIST = "list"
    SUMMARY = "summary"


class Anchor(Enum):
    """Reference point a window is expressed against."""

    NOW = "now"
    SESSION_START = "session_start"
    EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A window expressed relatively (``hours``) and/or absolutely."""

    since: float | None = None
    until: float | None = None
    hours: float | None = None
    anchor: Anchor = Anchor.NOW


@dataclass(frozen=True, slots=True)
class EntitySlot:
    """One entity a plan operates on: ``label``, ``zone``, ``camera``, ``text``."""

    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class RetrieveOp:
    """One self-contained retrieval operation."""

    kind: RetrieveKind
    entity: str | None = None
    query: str | None = None
    limit: int = 5
    min_score: float = 0.0
    risk: str | None = None
    location: str | None = None
    aggregation: Aggregation | None = None


@dataclass(frozen=True, slots=True)
class RecallPlan:
    """Everything an engine needs to answer one question.

    ``anchor`` optionally names a detection label the whole plan must be
    rebuilt around: when set, the engine resolves the most recent occurrence
    of that label and rebases the time window on it. Left ``None`` the plan
    behaves exactly as it always has, anchored to the window alone.

    ``direction`` is the explicit before/after signal (A7B): ``"before"``
    or ``"after"`` when the question asked for one side of ``anchor``,
    ``None`` when it did not or the wording was ambiguous. The synthesizer
    only makes a directional claim when direction **and** anchor are set.

    ``state_topic`` (A7C) marks a live-state plan: it names which
    :class:`~src.domain.services.query_router.StateTopic` the question is
    about, and ``state_polarity`` carries the open/closed property the
    question itself asserted. Both are ``None`` for every memory plan, so
    nothing about the existing behaviour changes.

    ``response_intent`` (A7D) is the shape of answer the question asked for:
    when the planner can tell, it records the resolved
    :class:`~src.domain.services.response_intent.ResponseIntent` so the
    synthesizer routes the plan to the matching renderer. Left ``None`` the
    synthesizer derives it from the plan's relations/aggregation alone, so a
    directly built plan behaves exactly as it always has.
    """

    lang: str
    window: TimeWindow
    entities: tuple[EntitySlot, ...] = ()
    ops: tuple[RetrieveOp, ...] = ()
    relations: tuple[RelationKind, ...] = ()
    aggregation: Aggregation | None = None
    wants_evidence: bool = True
    anchor: str | None = None
    direction: str | None = None
    state_topic: str | None = None
    state_polarity: str | None = None
    response_intent: ResponseIntent | None = None


def plan_to_dict(plan: RecallPlan) -> dict[str, object]:
    """JSON-safe representation of a plan, used to make traces auditable."""
    return {
        "lang": plan.lang,
        "aggregation": plan.aggregation.value if plan.aggregation else None,
        "wants_evidence": plan.wants_evidence,
        "anchor": plan.anchor,
        "direction": plan.direction,
        "state_topic": plan.state_topic,
        "state_polarity": plan.state_polarity,
        "response_intent": (
            plan.response_intent.value if plan.response_intent else None
        ),
        "window": {
            "since": plan.window.since,
            "until": plan.window.until,
            "hours": plan.window.hours,
            "anchor": plan.window.anchor.value,
        },
        "entities": [
            {"kind": slot.kind, "value": slot.value} for slot in plan.entities
        ],
        "relations": [relation.value for relation in plan.relations],
        "ops": [
            {
                "kind": op.kind.value,
                "entity": op.entity,
                "query": op.query,
                "limit": op.limit,
                "min_score": op.min_score,
                "risk": op.risk,
                "location": op.location,
                "aggregation": op.aggregation.value if op.aggregation else None,
            }
            for op in plan.ops
        ],
    }
