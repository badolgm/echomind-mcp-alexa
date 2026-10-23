"""Unit tests for the A6f contextual narration.

The contract: narration is born from ``ContextItem`` (signal, degraded,
salience), speaks only what clears ``NARRATION_MIN``, and never touches the V1
utterance.
"""

from __future__ import annotations

import json

from src.domain.services.context import (
    NARRATION_MIN,
    SIGNAL_MIN,
    ContextItem,
    build_context,
    salience_of,
)
from src.domain.services.context_narrative import (
    MAX_NARRATION_ITEMS,
    render_context,
)
from src.domain.services.relation import Relation
from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.domain.services.relation_rules import RELATION_RULES
from src.domain.services.evidence import RecallResult, RecallTrace
from src.infrastructure.adapters.mcp.recall_resolvers import recall_result_payload
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 10000.0

_RULE_BY_KIND = {rule.kind: rule.id for rule in RELATION_RULES}


def _item(
    kind: str,
    *,
    facts: dict | None = None,
    degraded: bool = False,
    subject: str = "m-1",
    object_: str = "m-2",
    salience: int | None = None,
) -> ContextItem:
    relation = Relation(
        kind=kind,
        subject=subject,
        object=object_,
        rule=_RULE_BY_KIND.get(kind, "test.rule"),
        facts=facts or {},
        degraded=degraded,
        fallback="location" if degraded else None,
    )
    grade = salience_of(kind) if salience is None else salience
    return ContextItem(relation=relation, salience=grade)


def _relation_of(kind: str) -> Relation:
    return Relation(
        kind=kind,
        subject="m-1",
        object="m-2",
        rule=_RULE_BY_KIND.get(kind, "test.rule"),
        facts={"risk": "HIGH"} if kind == "correlation_same_risk" else {},
    )


def _transition(**kwargs: object) -> ContextItem:
    defaults: dict[str, object] = {
        "facts": {
            "seconds": 40.0,
            "from_labels": ("GATE_OPEN",),
            "to_labels": ("FALL",),
        }
    }
    defaults.update(kwargs)
    return _item("temporal_transition", **defaults)  # type: ignore[arg-type]


def _overlapping(**kwargs: object) -> ContextItem:
    defaults: dict[str, object] = {
        "facts": {
            "overlap_seconds": 100.0,
            "subject_labels": ("PET",),
            "object_labels": ("SMOKE",),
        }
    }
    defaults.update(kwargs)
    return _item("correlation_overlapping", **defaults)  # type: ignore[arg-type]


# --- the ladder: signal vs narration ----------------------------------------


def test_narration_grade_is_stricter_than_signal() -> None:
    assert NARRATION_MIN > SIGNAL_MIN


def test_only_the_two_chosen_kinds_may_be_spoken() -> None:
    spoken = {rule.kind for rule in RELATION_RULES if rule.salience >= NARRATION_MIN}
    assert spoken == {"temporal_transition", "correlation_overlapping"}


def test_the_four_holdback_kinds_stay_data_only() -> None:
    for kind in (
        "temporal_precedes",
        "correlation_same_label",
        "correlation_same_risk",
        "spatial_same_zone",
    ):
        assert _item(kind).narratable is False, kind


def test_precedes_and_same_label_are_signal_but_still_not_spoken() -> None:
    for kind in ("temporal_precedes", "correlation_same_label"):
        item = _item(kind)
        assert item.signal is True, kind
        assert item.narratable is False, kind


def test_narratable_implies_signal() -> None:
    for grade in range(NARRATION_MIN, 4):
        item = _item("temporal_transition", salience=grade)
        assert item.narratable is True
        assert item.signal is True


def test_degradation_never_blocks_the_narration() -> None:
    assert _transition(degraded=True).narratable is True


# --- selection --------------------------------------------------------------


def test_an_empty_context_renders_an_empty_string() -> None:
    assert render_context(()) == ""


def test_a_context_holding_only_noise_is_not_spoken() -> None:
    context = build_context(
        [
            _relation_of("correlation_same_risk"),
            _relation_of("spatial_same_zone"),
        ]
    )
    assert all(item.narratable is False for item in context)
    assert render_context(context) == ""


def test_the_cap_bounds_the_number_of_sentences() -> None:
    context = tuple(_transition() for _ in range(MAX_NARRATION_ITEMS + 2))
    narration = render_context(context)
    assert narration.count(". ") + 1 == MAX_NARRATION_ITEMS


def test_the_cap_matches_the_v1_line_ceiling() -> None:
    assert MAX_NARRATION_ITEMS == 3


def test_rendering_is_deterministic() -> None:
    context = (_transition(), _overlapping(), _item("temporal_transition", salience=1))
    assert render_context(context) == render_context(context)


# --- temporal.transition ----------------------------------------------------


def test_transition_sentence_in_spanish() -> None:
    assert (
        render_context([_transition()], lang="es")
        == "Cambio de GATE_OPEN a FALL, 40 segundos después, en el mismo lugar."
    )


def test_transition_sentence_in_english() -> None:
    assert (
        render_context([_transition()], lang="en")
        == "Change from GATE_OPEN to FALL, 40 seconds later, in the same place."
    )


def test_transition_discloses_the_degradation_in_spanish() -> None:
    narration = render_context([_transition(degraded=True)], lang="es")
    assert narration.endswith("(identidad aproximada).")


def test_transition_discloses_the_degradation_in_english() -> None:
    narration = render_context([_transition(degraded=True)], lang="en")
    assert narration.endswith("(approximate identity).")


def test_transition_without_labels_still_says_something() -> None:
    item = _item(
        "temporal_transition",
        facts={"seconds": 40.0, "from_labels": (), "to_labels": ()},
    )
    assert (
        render_context([item], lang="es")
        == "Cambio de actividad, 40 segundos después, en el mismo lugar."
    )


def test_a_single_second_is_not_pluralised() -> None:
    item = _item(
        "temporal_transition",
        facts={
            "seconds": 1.0,
            "from_labels": ("PET",),
            "to_labels": ("FALL",),
        },
    )
    assert "1 segundo después" in render_context([item], lang="es")
    assert "1 second later" in render_context([item], lang="en")


def test_several_labels_are_listed_on_each_side() -> None:
    item = _item(
        "temporal_transition",
        facts={
            "seconds": 5.0,
            "from_labels": ("GATE_OPEN", "MOTION"),
            "to_labels": ("FALL",),
        },
    )
    narration = render_context([item], lang="es")
    assert "Cambio de GATE_OPEN, MOTION a FALL, 5 segundos después" in narration


# --- correlation.overlapping -----------------------------------------------


def test_overlapping_names_both_sides() -> None:
    assert (
        render_context([_overlapping()], lang="es")
        == "PET y SMOKE simultáneos durante 100 segundos."
    )


def test_overlapping_in_english() -> None:
    assert (
        render_context([_overlapping()], lang="en")
        == "PET and SMOKE at the same time for 100 seconds."
    )


def test_overlapping_deduplicates_a_label_present_on_both_sides() -> None:
    item = _item(
        "correlation_overlapping",
        facts={
            "overlap_seconds": 100.0,
            "subject_labels": ("PET", "MOTION"),
            "object_labels": ("PET", "FALL"),
        },
    )
    narration = render_context([item], lang="es")
    assert narration.startswith("PET, MOTION y FALL")
    assert narration.count("PET") == 1


def test_touching_episodes_read_as_the_same_instant() -> None:
    item = _item(
        "correlation_overlapping",
        facts={
            "overlap_seconds": 0.0,
            "subject_labels": ("PET",),
            "object_labels": ("SMOKE",),
        },
    )
    assert render_context([item], lang="es") == "PET y SMOKE en el mismo instante."
    assert render_context([item], lang="en") == "PET and SMOKE at the same instant."


def test_overlapping_without_labels_falls_back() -> None:
    item = _item(
        "correlation_overlapping",
        facts={"overlap_seconds": 0.0, "subject_labels": (), "object_labels": ()},
    )
    assert render_context([item], lang="es") == "Dos episodios en el mismo instante."
    assert render_context([item], lang="en") == "Two episodes at the same instant."


# --- general shape ----------------------------------------------------------


def test_a_future_narratable_kind_is_not_silently_dropped() -> None:
    item = _item("temporal_gap", salience=3, subject="m-9", object_="m-7")
    assert item.narratable is True
    assert render_context([item], lang="es") == "Relación entre m-9 y m-7."


def test_every_sentence_ends_with_a_period() -> None:
    context = (
        _transition(),
        _overlapping(),
        _item("temporal_gap", salience=3),
    )
    narration = render_context(context, lang="es")
    assert narration.endswith(".")
    assert narration.count(".") == len(context)


def test_an_unsupported_language_falls_back_to_spanish() -> None:
    narration = render_context([_transition()], lang="fr")
    assert "Cambio de" in narration


def test_mixed_context_keeps_the_contextual_order() -> None:
    context = (_overlapping(), _transition())
    narration = render_context(context, lang="es")
    assert narration.index("simultáneos") < narration.index("Cambio")


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


def _plan(*, relations: tuple[RelationKind, ...], lang: str = "es") -> RecallPlan:
    return RecallPlan(
        lang=lang,
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=relations,
    )


def test_a_fresh_result_has_no_context_narration() -> None:
    result = RecallResult(
        utterance="ok",
        evidence=(),
        trace=RecallTrace(lang="es", plan={}),
        lang="es",
    )
    assert result.context_utterance == ""


def test_a_plan_without_relations_leaves_the_field_empty() -> None:
    result = RecallEngine(memory=_service()).execute(_plan(relations=()), now=NOW)
    assert result.context_utterance == ""


def test_the_engine_narrates_the_narratable_part_of_its_context() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.context_utterance.startswith("Cambio de")
    narratable = sum(1 for item in result.context if item.narratable)
    assert narratable == 3
    assert result.context_utterance.count("Cambio de") == 3


def test_the_v1_utterance_is_untouched_by_the_narration() -> None:
    service = _service()
    spoken = RecallEngine(memory=service).execute(
        _plan(relations=(RelationKind.EPISODE,)), now=NOW
    )
    silent = RecallEngine(memory=service).execute(_plan(relations=()), now=NOW)
    assert spoken.utterance == silent.utterance
    assert "Cambio de" not in spoken.utterance


def test_the_narration_is_rendered_in_the_plan_language() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,), lang="en")
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.context_utterance.startswith("Change from")


def test_the_abstention_path_leaves_the_field_empty() -> None:
    result = RecallEngine(memory=VectorMemoryService()).execute(
        _plan(relations=(RelationKind.EPISODE,)), now=NOW
    )
    assert result.context_utterance == ""


def test_the_payload_exposes_context_response_without_changing_response() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    payload = recall_result_payload(result)
    assert payload["context_response"] == result.context_utterance
    assert payload["response"] == result.utterance
    json.dumps(payload)


def test_the_payload_reports_an_empty_context_response_when_nothing_was_spoken() -> (
    None
):
    result = RecallEngine(memory=_service()).execute(_plan(relations=()), now=NOW)
    payload = recall_result_payload(result)
    assert payload["context_response"] == ""
