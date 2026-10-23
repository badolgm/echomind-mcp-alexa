"""Unit tests for question-directed synthesis (A7B).

Proves the recall answer now reflects the shape of the question — direction,
timeline, aggregate counts, camera groups, places, summary — while the
mandatory fallback to the V1 narration stays byte-identical when no
structural answer applies.
"""

from __future__ import annotations

from src.domain.services.evidence import (
    Evidence,
    render_abstention,
    render_utterance,
)
from src.domain.services.recall_plan import (
    Aggregation,
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
    plan_to_dict,
)
from src.domain.services.recall_planner import understand
from src.domain.services.recall_synthesis import render_synthesis
from src.infrastructure.adapters.mcp.recall_resolvers import recall_result_payload
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 10_000.0
HOUR = 3_600.0


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    camera: str = "cam-1",
    zone: str = "patio",
    risk: str = "HIGH",
    labels: tuple[str, ...] = ("PET",),
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        camera_id=camera,
        zone=zone,
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk=risk,
        model_analysis="registro de prueba",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    for record in (
        _record("b-1", NOW - 6 * HOUR, labels=("GATE_OPEN",), risk="HIGH"),
        _record("b-2", NOW - 5 * HOUR, labels=("PET",), risk="LOW"),
        _record(
            "fall-1",
            NOW - 4 * HOUR,
            labels=("FALL DETECTED", "PERSON"),
            risk="CRITICAL",
        ),
        _record(
            "a-1",
            NOW - 3 * HOUR,
            location="salon",
            camera="cam-3",
            zone="salon",
            labels=("PERSON_ELDERLY",),
            risk="MEDIUM",
        ),
        _record(
            "smoke-a",
            NOW - 2 * HOUR,
            location="cocina",
            camera="cam-4",
            zone="cocina",
            labels=("SMOKE",),
        ),
        _record(
            "smoke-b",
            NOW - 2 * HOUR,
            location="salon",
            camera="cam-3",
            zone="salon",
            labels=("SMOKE",),
        ),
    ):
        service.store_memory(record)
    return service


def _plan(
    *,
    relations: tuple[RelationKind, ...] = (),
    aggregation: Aggregation | None = None,
    direction: str | None = None,
    anchor: str | None = None,
    lang: str = "es",
) -> RecallPlan:
    return RecallPlan(
        lang=lang,
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=relations,
        aggregation=aggregation,
        direction=direction,
        anchor=anchor,
    )


_EVIDENCE = (
    Evidence(record_id="e-1", ts=NOW - HOUR, location="patio", labels=("PET",)),
)


def _count_ops(value: int, *, entity: str | None = None, risk: str | None = None):
    return [
        {
            "op": "retrieve:aggregate",
            "aggregation": "count",
            "value": value,
            "filters": {"entity": entity, "risk": risk},
        }
    ]


def _before_after_ops(*, episodes=(), episodes_after=()):
    return [
        {
            "op": "relate",
            "relation": "before_after",
            "target_ts": NOW - 4 * HOUR,
            "episodes": list(episodes),
            "episodes_after": list(episodes_after),
            "count": len(episodes),
            "count_after": len(episodes_after),
        }
    ]


# --- mandatory fallback ------------------------------------------------------


def test_without_structural_answer_the_v1_narration_is_returned() -> None:
    plan = _plan(relations=(RelationKind.EPISODE,))
    out = render_synthesis(plan, _EVIDENCE, [], [], now=NOW, lang="es")
    assert out == render_utterance(_EVIDENCE, lang="es", now=NOW)


def test_fallback_still_abstains_on_empty_evidence() -> None:
    out = render_synthesis(_plan(), (), [], [], now=NOW, lang="es")
    assert out == render_abstention(lang="es")


def test_empty_store_questions_abstain_through_the_engine() -> None:
    plan = understand("¿qué pasó mientras estaba fuera?", now=NOW)
    result = RecallEngine(memory=VectorMemoryService()).execute(plan, now=NOW)
    assert result.utterance == render_abstention(lang="es")


# --- aggregate counts --------------------------------------------------------


def test_count_line_answers_in_spanish() -> None:
    out = render_synthesis(_plan(), (), _count_ops(3), [], now=NOW, lang="es")
    assert out == "3 eventos."


def test_count_line_is_singular_for_one_event() -> None:
    out = render_synthesis(_plan(), (), _count_ops(1), [], now=NOW, lang="es")
    assert out == "1 evento."


def test_count_line_names_an_entity() -> None:
    out = render_synthesis(
        _plan(), (), _count_ops(2, entity="PET"), [], now=NOW, lang="es"
    )
    assert out == "2 detecciones de PET."


def test_count_line_names_a_risk_in_english() -> None:
    out = render_synthesis(
        _plan(lang="en"), (), _count_ops(4, risk="CRITICAL"), [], now=NOW, lang="en"
    )
    assert out == "4 CRITICAL risk events."


def test_count_line_reports_zero_honestly() -> None:
    out = render_synthesis(_plan(), (), _count_ops(0), [], now=NOW, lang="es")
    assert out == "0 eventos."


def test_a_count_question_is_answered_by_the_engine_with_a_number() -> None:
    plan = understand("¿cuántos eventos hubo hoy?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.utterance == "6 eventos."


# --- explicit before/after direction ----------------------------------------


def test_understand_marks_the_before_side() -> None:
    plan = understand("¿qué pasó antes de la caída?", now=NOW)
    assert plan.direction == "before"
    assert plan.anchor == "FALL DETECTED"


def test_understand_marks_the_after_side() -> None:
    plan = understand("¿qué pasó después de la caída?", now=NOW)
    assert plan.direction == "after"
    assert plan.anchor == "FALL DETECTED"


def test_understand_marks_the_english_sides() -> None:
    assert understand("what happened before the fall", now=NOW).direction == "before"
    assert understand("what happened after the fall", now=NOW).direction == "after"


def test_ambiguous_direction_is_left_unset() -> None:
    plan = understand("¿hubo algo antes o después de la caída?", now=NOW)
    assert plan.direction is None


def test_direction_stays_none_without_the_before_after_relation() -> None:
    plan = understand("dónde vi la mascota", now=NOW)
    assert RelationKind.BEFORE_AFTER not in plan.relations
    assert plan.direction is None


def test_plan_to_dict_exposes_the_direction() -> None:
    plan = _plan(relations=(RelationKind.BEFORE_AFTER,), direction="before")
    assert plan_to_dict(plan)["direction"] == "before"


def test_the_trace_plan_carries_the_direction() -> None:
    plan = understand("¿qué pasó antes de la caída?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.trace.plan["direction"] == "before"


def test_the_before_answer_names_the_anchor_and_the_before_side() -> None:
    plan = understand("¿qué pasó antes de la caída?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.utterance.startswith("Antes de FALL DETECTED:")
    assert "GATE_OPEN" in result.utterance
    assert "PERSON_ELDERLY" not in result.utterance


def test_the_after_answer_names_the_anchor_and_the_after_side() -> None:
    plan = understand("¿qué pasó después de la caída?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.utterance.startswith("Después de FALL DETECTED:")
    assert "PERSON_ELDERLY" in result.utterance
    assert "GATE_OPEN" not in result.utterance


def test_before_and_after_are_different_answers() -> None:
    before = RecallEngine(memory=_service()).execute(
        understand("¿qué pasó antes de la caída?", now=NOW), now=NOW
    )
    after = RecallEngine(memory=_service()).execute(
        understand("¿qué pasó después de la caída?", now=NOW), now=NOW
    )
    assert before.utterance != after.utterance


def test_a_directional_line_never_exceeds_three_episodes() -> None:
    episodes = [
        {
            "start": NOW - i * HOUR,
            "end": NOW - i * HOUR,
            "location": "patio",
            "labels": [f"L{i}"],
        }
        for i in range(1, 6)
    ]
    plan = _plan(
        relations=(RelationKind.BEFORE_AFTER,), direction="before", anchor="FALL"
    )
    out = render_synthesis(
        plan, _EVIDENCE, _before_after_ops(episodes=episodes), [], now=NOW, lang="es"
    )
    assert out.startswith("Antes de FALL:")
    assert "L1" in out and "L3" in out
    assert "L4" not in out and "L5" not in out


def test_an_empty_side_says_so_instead_of_guessing() -> None:
    plan = _plan(
        relations=(RelationKind.BEFORE_AFTER,), direction="after", anchor="FALL"
    )
    out = render_synthesis(
        plan, _EVIDENCE, _before_after_ops(episodes_after=[]), [], now=NOW, lang="es"
    )
    assert out == "No hubo eventos después de FALL."


def test_an_empty_side_in_english() -> None:
    plan = _plan(
        relations=(RelationKind.BEFORE_AFTER,),
        direction="before",
        anchor="FALL",
        lang="en",
    )
    out = render_synthesis(
        plan, _EVIDENCE, _before_after_ops(episodes=[]), [], now=NOW, lang="en"
    )
    assert out == "No events before FALL."


def test_direction_without_an_anchor_never_claims_a_side() -> None:
    plan = _plan(relations=(RelationKind.BEFORE_AFTER,), direction="before")
    out = render_synthesis(plan, _EVIDENCE, _before_after_ops(), [], now=NOW, lang="es")
    assert out == render_utterance(_EVIDENCE, lang="es", now=NOW)


# --- timeline ----------------------------------------------------------------


def test_the_timeline_answer_leads_with_gaps_and_keeps_the_evidence() -> None:
    plan = understand("¿qué pasó mientras estaba fuera?", now=NOW)
    result = RecallEngine(memory=_service()).execute(
        plan, now=NOW, session_start=NOW - 7 * HOUR
    )
    timeline = next(
        entry
        for entry in result.trace.ops_executed
        if entry.get("op") == "relate" and entry.get("relation") == "timeline"
    )
    episodes = len(timeline["episodes"])
    assert result.utterance.startswith(f"{episodes} episodios,")
    assert "silencios;" in result.utterance
    assert "GATE_OPEN en patio" in result.utterance


def test_the_timeline_context_narration_is_part_of_the_answer() -> None:
    plan = understand("¿qué pasó mientras estaba fuera?", now=NOW)
    result = RecallEngine(memory=_service()).execute(
        plan, now=NOW, session_start=NOW - 7 * HOUR
    )
    assert result.context_utterance
    assert result.context_utterance in result.utterance


def test_a_timeline_without_gaps_falls_back() -> None:
    entry = {
        "op": "relate",
        "relation": "timeline",
        "episodes": [{"start": NOW, "end": NOW}],
        "gaps": [],
    }
    plan = _plan(relations=(RelationKind.TIMELINE,))
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out == render_utterance(_EVIDENCE, lang="es", now=NOW)


# --- camera groups -----------------------------------------------------------


def test_the_camera_answer_names_the_cameras_and_the_shared_event() -> None:
    plan = understand("¿qué cámaras observaron la misma situación?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.utterance.startswith("Cámaras:")
    assert "cam-1" in result.utterance
    assert "Las cámaras cam-4 y cam-3 vieron el mismo suceso: SMOKE" in (
        result.utterance
    )


def test_a_camera_roster_is_ordered_by_group_size() -> None:
    entry = {
        "op": "relate",
        "relation": "correlation",
        "groups": {"cam-2": ["x"], "cam-1": ["a", "b", "c"]},
    }
    plan = _plan(relations=(RelationKind.CORRELATION,))
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out.startswith("Cámaras: cam-1 (3), cam-2 (1).")


def test_correlation_without_groups_falls_back() -> None:
    entry = {"op": "relate", "relation": "correlation", "groups": {}}
    plan = _plan(relations=(RelationKind.CORRELATION,))
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out == render_utterance(_EVIDENCE, lang="es", now=NOW)


# --- places ------------------------------------------------------------------


def test_a_where_did_i_see_question_answers_with_the_last_seen_place() -> None:
    plan = understand("¿dónde vi mi mascota?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert RelationKind.SPATIAL in plan.relations
    assert result.utterance.startswith("La última vez que vi una mascota fue en patio")
    assert "cam-1" in result.utterance
    assert "hace 5 horas" in result.utterance


def test_the_place_roster_keeps_the_evidence_behind_it() -> None:
    entry = {"op": "relate", "relation": "spatial", "groups": {"patio": ["a"]}}
    plan = _plan(relations=(RelationKind.SPATIAL,))
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out.startswith("Lugares: patio (1).")
    assert out.endswith(render_utterance(_EVIDENCE, lang="es", now=NOW))


# --- summary counts ----------------------------------------------------------


def test_a_summary_answer_leads_with_label_counts() -> None:
    entry = {
        "op": "retrieve:aggregate",
        "aggregation": "summary",
        "label_counts": {"SMOKE": 1, "PET": 2},
    }
    plan = _plan(aggregation=Aggregation.SUMMARY)
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out.startswith("Resumen: PET 2, SMOKE 1.")


def test_a_summary_without_counts_falls_back() -> None:
    entry = {"op": "retrieve:aggregate", "aggregation": "summary", "label_counts": {}}
    plan = _plan(aggregation=Aggregation.SUMMARY)
    out = render_synthesis(plan, _EVIDENCE, [entry], [], now=NOW, lang="es")
    assert out == render_utterance(_EVIDENCE, lang="es", now=NOW)


# --- engine wiring -----------------------------------------------------------


def test_the_engine_answer_is_deterministic_after_synthesis() -> None:
    plan = understand("¿qué pasó antes de la caída?", now=NOW)
    first = RecallEngine(memory=_service()).execute(plan, now=NOW)
    second = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert first == second


def test_payload_response_still_equals_the_utterance() -> None:
    plan = understand("¿qué pasó después de la caída?", now=NOW)
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    payload = recall_result_payload(result)
    assert payload["response"] == result.utterance
