"""Unit tests for the A6e context layer.

``context`` is the last stop before words: relations are graded and ranked,
never reworded. The contract under test is that it is structured, complete,
deterministic, JSON-safe — and that it leaves the V1 answer alone.
"""

from __future__ import annotations

import json

import pytest

from src.domain.services.context import (
    DEFAULT_SALIENCE,
    SIGNAL_MIN,
    ContextItem,
    build_context,
    context_to_dict,
    salience_of,
)
from src.domain.services.relation import KNOWN_RELATION_KINDS, Relation
from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.domain.services.relation_rules import RELATION_RULES
from src.infrastructure.adapters.mcp.recall_resolvers import recall_result_payload
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 10000.0

_HIGH_RULE_BY_KIND = {rule.kind: rule.id for rule in RELATION_RULES}


def _relation(kind: str, *, subject: str = "m-1", object_: str = "m-2") -> Relation:
    return Relation(
        kind=kind,
        subject=subject,
        object=object_,
        rule=_HIGH_RULE_BY_KIND.get(kind, "test.rule"),
        facts={"note": "unit"},
    )


# --- the item ----------------------------------------------------------------


def test_context_item_is_frozen_and_slotted() -> None:
    item = ContextItem(relation=_relation("temporal_precedes"), salience=2)
    assert not hasattr(item, "__dict__")
    with pytest.raises(Exception):
        item.salience = 1  # type: ignore[misc]


def test_context_item_rejects_a_salience_above_three() -> None:
    with pytest.raises(ValueError):
        ContextItem(relation=_relation("temporal_precedes"), salience=4)


def test_context_item_rejects_a_negative_salience() -> None:
    with pytest.raises(ValueError):
        ContextItem(relation=_relation("temporal_precedes"), salience=-1)


def test_context_item_delegates_degradation_to_its_relation() -> None:
    degraded = Relation(
        kind="spatial_same_zone",
        subject="m-1",
        object="m-2",
        rule="spatial.same_zone",
        facts={},
        degraded=True,
        fallback="location",
    )
    assert ContextItem(relation=degraded, salience=1).degraded is True
    exact = Relation(
        kind="temporal_precedes",
        subject="m-1",
        object="m-2",
        rule="temporal.precedes",
        facts={},
    )
    assert ContextItem(relation=exact, salience=2).degraded is False


def test_signal_threshold_splits_the_scale() -> None:
    assert SIGNAL_MIN == 2
    relation = _relation("temporal_precedes")
    assert ContextItem(relation=relation, salience=2).signal is True
    assert ContextItem(relation=relation, salience=1).signal is False


# --- salience ---------------------------------------------------------------


def test_salience_is_read_from_the_rule_table() -> None:
    for rule in RELATION_RULES:
        assert salience_of(rule.kind) == rule.salience


def test_an_unknown_kind_falls_back_to_the_default_grade() -> None:
    assert salience_of("temporal_within") == DEFAULT_SALIENCE
    assert DEFAULT_SALIENCE < SIGNAL_MIN


def test_every_declared_rule_kind_is_known_to_the_vocabulary() -> None:
    for rule in RELATION_RULES:
        assert rule.kind in KNOWN_RELATION_KINDS


def test_the_rule_table_is_graded_not_uniform() -> None:
    grades = {rule.salience for rule in RELATION_RULES}
    assert any(grade >= SIGNAL_MIN for grade in grades)
    assert any(grade < SIGNAL_MIN for grade in grades)


# --- building ----------------------------------------------------------------


def test_context_of_an_empty_graph_is_empty() -> None:
    assert build_context(()) == ()


def test_no_relation_is_dropped() -> None:
    relations = tuple(_relation(kind) for kind in KNOWN_RELATION_KINDS)
    assert len(build_context(relations)) == len(relations)


def test_signal_relations_are_ranked_first() -> None:
    relations = (
        _relation("correlation_same_risk"),
        _relation("temporal_transition"),
        _relation("spatial_same_zone"),
        _relation("correlation_overlapping"),
    )
    context = build_context(relations)
    assert [item.relation.kind for item in context] == [
        "correlation_overlapping",
        "temporal_transition",
        "correlation_same_risk",
        "spatial_same_zone",
    ]
    assert context[0].signal is True
    assert context[-1].signal is False


def test_context_order_is_deterministic() -> None:
    relations = tuple(
        _relation(kind, subject=f"m-{index}", object_=f"m-{index + 1}")
        for index, kind in enumerate(KNOWN_RELATION_KINDS)
    )
    assert build_context(relations) == build_context(relations)


def test_context_order_does_not_depend_on_input_order() -> None:
    relations = tuple(_relation(kind) for kind in KNOWN_RELATION_KINDS)
    assert build_context(relations) == build_context(reversed(relations))


def test_context_is_total_ordered_by_salience_then_ids() -> None:
    relations = tuple(
        _relation(kind, subject="m-1", object_="m-2") for kind in KNOWN_RELATION_KINDS
    )
    keys = [
        (-item.salience, item.relation.kind, item.relation.subject)
        for item in build_context(relations)
    ]
    assert keys == sorted(keys)


def test_context_items_hold_their_relation_untouched() -> None:
    relation = _relation("correlation_overlapping")
    item = build_context([relation])[0]
    assert item.relation is relation
    assert item.salience == 3


# --- projection -------------------------------------------------------------


def test_context_to_dict_is_json_safe() -> None:
    context = build_context(_relation(kind) for kind in KNOWN_RELATION_KINDS)
    json.dumps([context_to_dict(item) for item in context])


def test_context_to_dict_exposes_the_grades() -> None:
    item = build_context([_relation("temporal_transition")])[0]
    payload = context_to_dict(item)
    assert payload["salience"] == 3
    assert payload["signal"] is True
    assert payload["kind"] == "temporal_transition"
    assert payload["rule"] == "temporal.transition"


def test_context_to_dict_keeps_the_relation_facts_and_provenance() -> None:
    item = build_context([_relation("temporal_precedes")])[0]
    payload = context_to_dict(item)
    assert payload["subject"] == "m-1"
    assert payload["object"] == "m-2"
    assert payload["facts"] == {"note": "unit"}
    assert payload["degraded"] is False
    assert payload["fallback"] is None


# --- engine wiring ----------------------------------------------------------


def _record(
    record_id: str, timestamp: float, *, labels: tuple[str, ...]
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location="patio",
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk="HIGH",
        model_analysis="",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    service.store_memory(_record("m-1", 1000.0, labels=("GATE_OPEN",)))
    service.store_memory(_record("m-2", 1080.0, labels=("FALL",)))
    service.store_memory(_record("m-3", 1095.0, labels=("PET",)))
    return service


def _plan(*, relations: tuple[RelationKind, ...]) -> RecallPlan:
    return RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=relations,
    )


def test_a_plan_without_relations_carries_no_context() -> None:
    result = RecallEngine(memory=_service()).execute(_plan(relations=()), now=NOW)
    assert result.context == ()
    assert result.trace.relations == ()


def test_a_plan_with_relations_carries_both_views() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert len(result.context) > 0
    assert len(result.trace.relations) == len(result.context)


def test_context_leads_with_the_highest_salience() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    grades = [item.salience for item in result.context]
    assert grades == sorted(grades, reverse=True)


def test_context_is_deterministic_across_runs() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    first = RecallEngine(memory=_service()).execute(plan, now=NOW)
    second = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert first.context == second.context


def test_the_utterance_does_not_read_the_context() -> None:
    service = _service()
    with_context = RecallEngine(memory=service).execute(
        _plan(relations=(RelationKind.EPISODE,)), now=NOW
    )
    without_context = RecallEngine(memory=service).execute(_plan(relations=()), now=NOW)
    assert with_context.utterance == without_context.utterance


def test_the_context_is_reachable_from_the_abstention_path() -> None:
    empty = VectorMemoryService()
    result = RecallEngine(memory=empty).execute(
        _plan(relations=(RelationKind.EPISODE,)), now=NOW
    )
    assert result.context == ()
    assert result.trace.relations == ()


def test_the_payload_exposes_context_and_trace_relations() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    payload = recall_result_payload(result)
    relations = payload["trace"]["relations"]  # type: ignore[index]
    assert payload["context"] is not None  # type: ignore[index]
    assert len(payload["context"]) == len(result.context)  # type: ignore[index]
    assert len(relations) == len(result.trace.relations)
    json.dumps(payload)


def test_the_payload_reports_an_empty_context_when_nothing_was_related() -> None:
    payload = recall_result_payload(
        RecallEngine(memory=_service()).execute(_plan(relations=()), now=NOW)
    )
    assert payload["context"] == []
    assert payload["trace"]["relations"] == []
