"""Unit tests for the A6d relation rules.

Covers the pure rule table (pairwise over ``Episode``) and the engine wiring,
whose contract is strict: relations appear **in the trace only**, and the
answer is byte for byte what it was before.
"""

from __future__ import annotations

import json

import pytest

from src.domain.services.relation import KNOWN_RELATION_KINDS, Relation
from src.domain.services.relation_rules import (
    DEFAULT_MAX_RELATIONS,
    RELATION_RULES,
    relate_episodes,
)
from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.memory_timeline import Episode
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 10000.0


def _episode(
    record_id: str,
    start: float,
    end: float,
    *,
    location: str = "patio",
    labels: tuple[str, ...] = ("PET",),
    risk: str = "HIGH",
) -> Episode:
    return Episode(
        start=start,
        end=end,
        location=location,
        labels=labels,
        risk=risk,
        record_ids=(record_id,),
    )


def _kinds(relations: tuple[Relation, ...]) -> list[str]:
    return [relation.kind for relation in relations]


# --- rule table -------------------------------------------------------------


def test_rule_table_ids_are_unique() -> None:
    ids = [rule.id for rule in RELATION_RULES]
    assert len(ids) == len(set(ids))


def test_rule_table_kinds_are_in_the_closed_vocabulary() -> None:
    for rule in RELATION_RULES:
        assert rule.kind in KNOWN_RELATION_KINDS, rule.id


def test_rule_table_rules_are_frozen() -> None:
    rule = RELATION_RULES[0]
    assert not hasattr(rule, "__dict__")
    with pytest.raises(Exception):
        rule.id = "changed"  # type: ignore[misc]


def test_rule_table_declares_the_six_a6d_rules() -> None:
    assert {rule.id for rule in RELATION_RULES} == {
        "temporal.precedes",
        "temporal.transition",
        "correlation.same_label",
        "correlation.same_risk",
        "correlation.overlapping",
        "spatial.same_zone",
    }


def test_rule_table_entries_carry_a_description() -> None:
    for rule in RELATION_RULES:
        assert rule.description.strip(), rule.id
        assert isinstance(rule.salience, int) and 0 <= rule.salience <= 3, rule.id


# --- temporal ---------------------------------------------------------------


def test_no_relations_for_an_empty_input() -> None:
    assert relate_episodes([]) == ()


def test_no_relations_for_a_single_episode() -> None:
    assert relate_episodes([_episode("m-1", 0.0, 10.0)]) == ()


def test_temporal_precedes_for_a_chronological_pair() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    assert "temporal_precedes" in _kinds(relations)


def test_temporal_precedes_carries_the_seconds() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    precedes = next(r for r in relations if r.kind == "temporal_precedes")
    assert precedes.facts["seconds"] == 40.0


def test_temporal_precedes_is_emitted_in_one_direction_only() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    precedes = [r for r in relations if r.kind == "temporal_precedes"]
    assert len(precedes) == 1
    assert precedes[0].subject == "m-1"
    assert precedes[0].object == "m-2"


def test_no_temporal_precedes_for_overlapping_episodes() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 500.0), _episode("m-2", 300.0, 400.0)]
    )
    assert "temporal_precedes" not in _kinds(relations)


def test_temporal_transition_when_adjacent_and_labels_change() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("GATE_OPEN",)),
            _episode("m-2", 50.0, 60.0, labels=("FALL",)),
        ]
    )
    assert "temporal_transition" in _kinds(relations)


def test_temporal_transition_carries_both_label_sets() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("GATE_OPEN",)),
            _episode("m-2", 50.0, 60.0, labels=("FALL",)),
        ]
    )
    transition = next(r for r in relations if r.kind == "temporal_transition")
    assert transition.facts["from_labels"] == ("GATE_OPEN",)
    assert transition.facts["to_labels"] == ("FALL",)
    assert transition.facts["seconds"] == 40.0


def test_no_temporal_transition_when_labels_are_unchanged() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("PET",)),
            _episode("m-2", 50.0, 60.0, labels=("PET",)),
        ]
    )
    assert "temporal_transition" not in _kinds(relations)


def test_no_temporal_transition_when_the_episodes_are_far_apart() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("GATE_OPEN",)),
            _episode("m-2", 9000.0, 9010.0, labels=("FALL",)),
        ]
    )
    assert "temporal_transition" not in _kinds(relations)


def test_temporal_transition_honours_a_custom_adjacency() -> None:
    episodes = [
        _episode("m-1", 0.0, 10.0, labels=("GATE_OPEN",)),
        _episode("m-2", 210.0, 220.0, labels=("FALL",)),
    ]
    assert "temporal_transition" in _kinds(relate_episodes(episodes))
    assert "temporal_transition" not in _kinds(
        relate_episodes(episodes, adjacency_seconds=100.0)
    )


def test_temporal_transition_is_marked_degraded_for_legacy_episodes() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("GATE_OPEN",)),
            _episode("m-2", 50.0, 60.0, labels=("FALL",)),
        ]
    )
    transition = next(r for r in relations if r.kind == "temporal_transition")
    assert transition.degraded is True
    assert transition.fallback == "location"


# --- correlational ----------------------------------------------------------


def test_correlation_same_label_on_a_shared_label() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("PET", "MOTION")),
            _episode("m-2", 50.0, 60.0, labels=("PET",)),
        ]
    )
    shared = next(r for r in relations if r.kind == "correlation_same_label")
    assert shared.facts["shared"] == ("PET",)


def test_no_correlation_same_label_for_disjoint_labels() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, labels=("PET",)),
            _episode("m-2", 50.0, 60.0, labels=("SMOKE",)),
        ]
    )
    assert "correlation_same_label" not in _kinds(relations)


def test_correlation_same_risk() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, risk="CRITICAL"),
            _episode("m-2", 50.0, 60.0, risk="CRITICAL"),
        ]
    )
    same = next(r for r in relations if r.kind == "correlation_same_risk")
    assert same.facts["risk"] == "CRITICAL"


def test_no_correlation_same_risk_for_different_levels() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, risk="LOW"),
            _episode("m-2", 50.0, 60.0, risk="HIGH"),
        ]
    )
    assert "correlation_same_risk" not in _kinds(relations)


def test_correlation_overlapping_on_an_overlap() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 500.0), _episode("m-2", 300.0, 400.0)]
    )
    assert "correlation_overlapping" in _kinds(relations)


def test_correlation_overlapping_carries_the_overlap_seconds() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 500.0), _episode("m-2", 300.0, 400.0)]
    )
    overlap = next(r for r in relations if r.kind == "correlation_overlapping")
    assert overlap.facts["overlap_seconds"] == 100.0


def test_no_correlation_overlapping_when_the_episodes_are_disjoint() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    assert "correlation_overlapping" not in _kinds(relations)


# --- spatial ----------------------------------------------------------------


def test_spatial_same_zone_for_a_shared_location() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    assert "spatial_same_zone" in _kinds(relations)


def test_spatial_same_zone_is_marked_degraded_for_legacy_episodes() -> None:
    relations = relate_episodes(
        [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    )
    zone = next(r for r in relations if r.kind == "spatial_same_zone")
    assert zone.degraded is True
    assert zone.fallback == "location"
    assert zone.facts["zone"] == "patio"


def test_no_spatial_same_zone_for_different_locations() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0, location="patio"),
            _episode("m-2", 50.0, 60.0, location="kitchen"),
        ]
    )
    assert "spatial_same_zone" not in _kinds(relations)


# --- determinism, ordering and the cap --------------------------------------


def test_relations_are_ordered_deterministically() -> None:
    episodes = [
        _episode("m-3", 900.0, 910.0),
        _episode("m-1", 100.0, 110.0),
        _episode("m-2", 500.0, 510.0),
    ]
    first = relate_episodes(episodes)
    assert first == relate_episodes(episodes)


def test_input_order_does_not_change_the_output() -> None:
    episodes = [
        _episode("m-3", 900.0, 910.0),
        _episode("m-1", 100.0, 110.0),
        _episode("m-2", 500.0, 510.0),
    ]
    assert relate_episodes(episodes) == relate_episodes(list(reversed(episodes)))


def test_relations_are_sorted_by_kind_then_ids() -> None:
    relations = relate_episodes(
        [
            _episode("m-2", 500.0, 510.0),
            _episode("m-1", 100.0, 110.0),
        ]
    )
    keys = [(r.kind, r.subject, r.object) for r in relations]
    assert keys == sorted(keys)


def test_relations_are_capped() -> None:
    episodes = [
        _episode(f"m-{i}", float(i * 100), float(i * 100 + 10)) for i in range(9)
    ]
    capped = relate_episodes(episodes, max_relations=3)
    assert len(capped) == 3
    full = relate_episodes(episodes, max_relations=DEFAULT_MAX_RELATIONS)
    assert len(full) > 3
    assert capped == full[:3]


def test_a_zero_cap_returns_nothing() -> None:
    episodes = [_episode("m-1", 0.0, 10.0), _episode("m-2", 50.0, 60.0)]
    assert relate_episodes(episodes, max_relations=0) == ()


def test_the_default_cap_is_positive() -> None:
    assert DEFAULT_MAX_RELATIONS > 0


# --- provenance -------------------------------------------------------------


def test_every_relation_carries_its_rule_id() -> None:
    relations = relate_episodes(
        [
            _episode("m-1", 0.0, 10.0),
            _episode("m-2", 50.0, 60.0),
        ]
    )
    declared = {rule.id for rule in RELATION_RULES}
    for relation in relations:
        assert relation.rule in declared
        assert relation.rule.replace(".", "_") == relation.kind


def test_episode_identity_uses_the_first_record() -> None:
    episode = Episode(
        start=0.0,
        end=10.0,
        location="patio",
        labels=("PET",),
        risk="HIGH",
        record_ids=("mem-9", "mem-8"),
    )
    relations = relate_episodes([episode, _episode("m-2", 50.0, 60.0)])
    assert any(relation.subject == "mem-9" for relation in relations)


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


def _derived(result: object) -> dict:
    entries = [
        entry
        for entry in result.trace.ops_executed  # type: ignore[attr-defined]
        if entry["op"] == "relate" and entry.get("relation") == "derived"
    ]
    assert len(entries) == 1
    return entries[0]


def test_derived_relations_appear_in_the_trace() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    entry = _derived(result)
    kinds = {item["kind"] for item in entry["relations"]}
    assert "temporal_precedes" in kinds
    assert "temporal_transition" in kinds
    assert entry["count"] == len(entry["relations"])


def test_a_plan_without_relations_adds_no_derived_entry() -> None:
    plan = _plan(relations=())
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    derived = [
        entry
        for entry in result.trace.ops_executed
        if entry.get("relation") == "derived"
    ]
    assert derived == []


def test_derived_relations_are_json_safe() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    _ = json.dumps(_derived(result))


def test_the_answer_is_identical_with_and_without_derived_relations() -> None:
    service = _service()
    with_relations = RecallEngine(memory=service).execute(
        _plan(relations=(RelationKind.EPISODE,)), now=NOW
    )
    without_relations = RecallEngine(memory=service).execute(
        _plan(relations=()), now=NOW
    )
    assert with_relations.utterance == without_relations.utterance
    assert with_relations.evidence == without_relations.evidence


def test_the_engine_honours_a_custom_relation_cap() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service(), max_relations=2).execute(plan, now=NOW)
    assert _derived(result)["count"] == 2
