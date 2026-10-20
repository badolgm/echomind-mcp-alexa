"""Unit tests for the recall plan value objects."""

from __future__ import annotations

import json

import pytest

from src.domain.services.recall_plan import (
    Aggregation,
    Anchor,
    EntitySlot,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
    plan_to_dict,
)


def test_time_window_defaults() -> None:
    window = TimeWindow()
    assert window.since is None
    assert window.until is None
    assert window.hours is None
    assert window.anchor is Anchor.NOW


def test_entities_and_ops_default_to_empty_tuple() -> None:
    plan = RecallPlan(lang="es", window=TimeWindow())
    assert plan.entities == ()
    assert plan.ops == ()
    assert plan.relations == ()


def test_plan_is_frozen_and_slot_sealed() -> None:
    plan = RecallPlan(lang="es", window=TimeWindow())
    with pytest.raises((AttributeError, Exception)):
        plan.lang = "en"  # type: ignore[misc]
    # slots=True => no __dict__ (in normal classes) or at least frozen
    assert not hasattr(plan, "__dict__")


def test_plan_to_dict_is_json_safe() -> None:
    plan = RecallPlan(
        lang="es",
        window=TimeWindow(since=1.0, until=2.0, hours=1.0, anchor=Anchor.EXPLICIT),
        entities=(EntitySlot(kind="label", value="PET"),),
        ops=(RetrieveOp(kind=RetrieveKind.LAST_SEEN, entity="PET"),),
        relations=(RelationKind.SPATIAL,),
        aggregation=Aggregation.COUNT,
        wants_evidence=True,
    )
    data = plan_to_dict(plan)
    # JSON serializable
    _ = json.dumps(data)
    assert data["window"]["anchor"] == "explicit"
    assert data["ops"][0]["kind"] == "last_seen"
    assert data["relations"][0] == "spatial"
    assert data["aggregation"] == "count"


def test_plan_to_dict_is_deterministic() -> None:
    plan = RecallPlan(
        lang="en",
        window=TimeWindow(hours=6.0, anchor=Anchor.EXPLICIT),
        entities=(EntitySlot(kind="zone", value="backyard"),),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.TIMELINE,),
        aggregation=None,
    )
    assert plan_to_dict(plan) == plan_to_dict(plan)


def test_retrieve_kind_values_are_stable() -> None:
    assert RetrieveKind.LAST_SEEN.value == "last_seen"
    assert RetrieveKind.SEARCH.value == "search"
    assert RetrieveKind.RANGE.value == "range"
    assert RetrieveKind.TOP.value == "top"
    assert RetrieveKind.AGGREGATE.value == "aggregate"
    assert RetrieveKind.CURRENT_STATE.value == "current_state"


def test_relation_kind_values_are_stable() -> None:
    for member in RelationKind:
        assert isinstance(member.value, str) and member.value
