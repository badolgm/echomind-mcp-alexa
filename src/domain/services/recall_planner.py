"""Deterministic understanding: a question becomes a declarative recall plan.

Pure domain layer (standard library only). Every dimension (time, entities,
relations, aggregation, anchor) is resolved by scanning its **own table** and
the plan is then assembled from those slots. No branch compares a whole
question, so adding a use case means adding a table row.
"""

from __future__ import annotations

import re

from src.domain.services.memory_intent import (
    _LABEL_TERMS,
    MemoryIntentClassifier,
    MemoryIntentType,
)
from src.domain.services.query_router import QueryKind, RouteDecision, route_query
from src.domain.services.recall_plan import (
    Aggregation,
    Anchor,
    EntitySlot,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.domain.services.response_intent import ResponseIntent, resolve_intent

_CAMERA_RE = re.compile(r"^cam-?\d+$")

_RELATION_PHRASES: tuple[tuple[str, RelationKind], ...] = (
    ("antes de", RelationKind.BEFORE_AFTER),
    ("after the", RelationKind.BEFORE_AFTER),
    ("después de", RelationKind.BEFORE_AFTER),
    ("before the", RelationKind.BEFORE_AFTER),
    ("despues de", RelationKind.BEFORE_AFTER),
    ("antes de la", RelationKind.BEFORE_AFTER),
    ("después de la", RelationKind.BEFORE_AFTER),
    ("despues de la", RelationKind.BEFORE_AFTER),
    ("relacionado", RelationKind.CORRELATION),
    ("relacionados", RelationKind.CORRELATION),
    ("relacionadas", RelationKind.CORRELATION),
    ("related", RelationKind.CORRELATION),
    ("between", RelationKind.CORRELATION),
    ("entre", RelationKind.CORRELATION),
    ("mientras", RelationKind.TIMELINE),
    ("while", RelationKind.TIMELINE),
    ("al mismo tiempo", RelationKind.CORRELATION),
    ("a la vez", RelationKind.CORRELATION),
    ("simultáne", RelationKind.CORRELATION),
    ("coincidi", RelationKind.CORRELATION),
    ("junto con", RelationKind.CORRELATION),
    ("cámara", RelationKind.CORRELATION),
    ("cámaras", RelationKind.CORRELATION),
    ("camara", RelationKind.CORRELATION),
    ("camaras", RelationKind.CORRELATION),
    ("cerca de", RelationKind.SPATIAL),
    ("dónde", RelationKind.SPATIAL),
    ("donde", RelationKind.SPATIAL),
    ("where", RelationKind.SPATIAL),
    ("alrededor de", RelationKind.EPISODE),
    ("durante", RelationKind.EPISODE),
    ("during", RelationKind.EPISODE),
)

_SESSION_PHRASES: tuple[tuple[str, Anchor], ...] = (
    ("mientras estaba fuera", Anchor.SESSION_START),
    ("cuando salí", Anchor.SESSION_START),
    ("cuando me fui", Anchor.SESSION_START),
    ("while i was away", Anchor.SESSION_START),
    ("when i left", Anchor.SESSION_START),
    ("when i was away", Anchor.SESSION_START),
)

_DIRECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdespu[eé]s\b"), "after"),
    (re.compile(r"\bdespues\b"), "after"),
    (re.compile(r"\bafter\b"), "after"),
    (re.compile(r"\bantes\b"), "before"),
    (re.compile(r"\bbefore\b"), "before"),
)

_INTENT_AGGREGATION: dict[MemoryIntentType, Aggregation] = {
    MemoryIntentType.EVENT_COUNT: Aggregation.COUNT,
    MemoryIntentType.SUMMARY: Aggregation.SUMMARY,
    MemoryIntentType.TOP_EVENTS: Aggregation.LIST,
}

_INTENT_PRIMARY: dict[MemoryIntentType, RetrieveKind] = {
    MemoryIntentType.LAST_SEEN: RetrieveKind.LAST_SEEN,
    MemoryIntentType.SEARCH: RetrieveKind.SEARCH,
    MemoryIntentType.SUMMARY: RetrieveKind.RANGE,
    MemoryIntentType.TOP_EVENTS: RetrieveKind.TOP,
    MemoryIntentType.HIGH_RISK: RetrieveKind.RANGE,
    MemoryIntentType.CRITICAL_RISK: RetrieveKind.RANGE,
    MemoryIntentType.EVENT_COUNT: RetrieveKind.AGGREGATE,
    MemoryIntentType.CURRENT_STATE: RetrieveKind.CURRENT_STATE,
}


def understand(
    text: str, lang: str | None = None, *, now: float | None = None
) -> RecallPlan:
    """Turn a natural-language question into an executable :class:`RecallPlan`."""
    source = str(text)
    normalized = " ".join(source.lower().split())
    decision = route_query(source, lang)
    if decision.kind is QueryKind.CURRENT_STATE:
        return _state_plan(decision)
    intent = MemoryIntentClassifier().classify(source, lang)

    anchor = _detect_anchor(normalized)
    window = _build_window(anchor=anchor, hours=intent.hours, now=now)
    relations = _detect_relations(normalized)

    plan_anchor: str | None = None
    if RelationKind.BEFORE_AFTER in relations or RelationKind.TIMELINE in relations:
        plan_anchor = intent.label
        if plan_anchor is None:
            if "caída" in normalized or "caida" in normalized or "fall" in normalized:
                plan_anchor = "FALL DETECTED"

    direction: str | None = None
    if RelationKind.BEFORE_AFTER in relations:
        direction = _detect_direction(normalized)

    aggregation = _INTENT_AGGREGATION.get(intent.intent)
    response_intent = resolve_intent(
        text=normalized,
        aggregation=aggregation.value if aggregation is not None else None,
        relations=tuple(relation.value for relation in relations),
        direction=direction,
    )

    label = intent.label
    if label is None and response_intent is ResponseIntent.LAST_SEEN_PLACE:
        label = _detect_label(normalized)

    entities = _build_entities(
        label=label, location=intent.location, normalized=normalized
    )
    ops = _build_ops(
        intent_type=intent.intent,
        response_intent=response_intent,
        label=label,
        query=intent.query,
        aggregation=aggregation,
        risk=intent.risk,
        location=intent.location,
    )

    return RecallPlan(
        lang=intent.lang,
        window=window,
        entities=entities,
        ops=ops,
        relations=relations,
        aggregation=aggregation,
        wants_evidence=True,
        anchor=plan_anchor,
        direction=direction,
        response_intent=response_intent,
    )


def _state_plan(decision: RouteDecision) -> RecallPlan:
    """A live-state question becomes one snapshot op (A7C).

    No store op is added: the answer must come from the snapshot the engine
    reads at execution time, never from history. ``state_topic`` records
    which facet was asked about and ``state_polarity`` the open/closed
    property, so the synthesizer can render the honest sentence.
    """
    return RecallPlan(
        lang=decision.lang,
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.CURRENT_STATE),),
        state_topic=decision.topic.value if decision.topic is not None else None,
        state_polarity=decision.polarity,
    )


def _detect_direction(normalized: str) -> str | None:
    """Explicit before/after side: ``None`` when absent or ambiguous."""
    found = {
        direction
        for pattern, direction in _DIRECTION_PATTERNS
        if pattern.search(normalized)
    }
    if len(found) == 1:
        return found.pop()
    return None


def _detect_relations(normalized: str) -> tuple[RelationKind, ...]:
    found: list[RelationKind] = []
    for phrase, relation in _RELATION_PHRASES:
        if phrase in normalized and relation not in found:
            found.append(relation)
    return tuple(found)


def _detect_label(normalized: str) -> str | None:
    """Reuse the classifier's label vocabulary to name what a where-see asks about.

    A *"¿dónde vi la mascota?"* is not the classifier's LAST_SEEN shape, so it
    travels with no entity; the response intent still needs the label to find
    the place, so the same table the classifier scans is scanned here rather
    than duplicated.
    """
    for label, terms in _LABEL_TERMS:
        if any(term in normalized for term in terms):
            return label
    return None


def _detect_anchor(normalized: str) -> Anchor:
    for phrase, anchor in _SESSION_PHRASES:
        if phrase in normalized:
            return anchor
    return Anchor.NOW


def _build_window(
    *, anchor: Anchor, hours: float | None, now: float | None
) -> TimeWindow:
    if anchor is Anchor.SESSION_START:
        return TimeWindow(hours=hours, anchor=Anchor.SESSION_START)
    if hours is None:
        return TimeWindow(anchor=Anchor.NOW)
    return TimeWindow(
        since=None if now is None else now - hours * 3600.0,
        until=None if now is None else now,
        hours=hours,
        anchor=Anchor.EXPLICIT,
    )


def _build_entities(
    *, label: str | None, location: str | None, normalized: str
) -> tuple[EntitySlot, ...]:
    slots: list[EntitySlot] = []
    if label:
        slots.append(EntitySlot(kind="label", value=label))
    if location:
        kind = "camera" if _CAMERA_RE.match(location) else "zone"
        slots.append(EntitySlot(kind=kind, value=location))
    if not slots:
        slots.append(EntitySlot(kind="text", value=normalized))
    return tuple(slots)


def _build_ops(
    *,
    intent_type: MemoryIntentType,
    label: str | None,
    query: str,
    aggregation: Aggregation | None,
    risk: str | None,
    location: str | None,
    response_intent: ResponseIntent | None = None,
) -> tuple[RetrieveOp, ...]:
    """Compose operations from slots (see the table in the plan doc)."""
    primary = _INTENT_PRIMARY.get(intent_type, RetrieveKind.SEARCH)
    if response_intent is ResponseIntent.LAST_SEEN_PLACE:
        primary = RetrieveKind.LAST_SEEN
    if primary is RetrieveKind.CURRENT_STATE:
        return (RetrieveOp(kind=primary, entity=label, location=location),)

    ops: list[RetrieveOp] = [
        RetrieveOp(
            kind=primary,
            entity=label,
            query=query,
            risk=risk,
            location=location,
            aggregation=aggregation if primary is RetrieveKind.AGGREGATE else None,
        )
    ]
    if aggregation is not None and primary is not RetrieveKind.AGGREGATE:
        ops.append(
            RetrieveOp(
                kind=RetrieveKind.AGGREGATE,
                entity=label,
                risk=risk,
                location=location,
                aggregation=aggregation,
            )
        )
    if primary is not RetrieveKind.RANGE:
        ops.append(
            RetrieveOp(
                kind=RetrieveKind.RANGE,
                entity=label,
                risk=risk,
                location=location,
            )
        )
    return tuple(ops)
