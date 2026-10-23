"""Unit tests for the Response Intent Adapter (A7D).

Proves two different questions now receive two different, question-directed
answers: the shape of the answer is chosen by a resolved response intent, the
six mandatory A7D cases each get their own answer, and a plan built directly
(with no intent recorded) is derived exactly as it rendered before A7D.
"""

from __future__ import annotations

import pytest

from src.domain.services.evidence import Evidence
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
from src.domain.services.response_intent import (
    ResponseIntent,
    derive_intent,
    resolve_intent,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 1_760_000_000.0
HOUR = 3_600.0


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str,
    camera: str,
    zone: str,
    labels: tuple[str, ...],
    risk: str = "HIGH",
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
        _record(
            "m-01",
            NOW - 6 * HOUR,
            location="patio",
            camera="cam-1",
            zone="patio",
            labels=("GATE_OPEN",),
        ),
        _record(
            "m-02",
            NOW - 6 * HOUR,
            location="patio",
            camera="cam-2",
            zone="patio",
            labels=("PERSON",),
        ),
        _record(
            "m-03",
            NOW - 5 * HOUR,
            location="jardin",
            camera="cam-3",
            zone="jardin",
            labels=("PET",),
            risk="LOW",
        ),
        _record(
            "m-04",
            NOW - 4 * HOUR,
            location="patio",
            camera="cam-1",
            zone="patio",
            labels=("FALL DETECTED", "PERSON"),
            risk="CRITICAL",
        ),
        _record(
            "m-05",
            NOW - 3 * HOUR,
            location="salon",
            camera="cam-3",
            zone="salon",
            labels=("PERSON_ELDERLY",),
            risk="MEDIUM",
        ),
        _record(
            "m-06",
            NOW - 2 * HOUR,
            location="cocina",
            camera="cam-4",
            zone="cocina",
            labels=("SMOKE",),
        ),
        _record(
            "m-07",
            NOW - 2 * HOUR,
            location="salon",
            camera="cam-3",
            zone="salon",
            labels=("SMOKE",),
        ),
        _record(
            "m-08",
            NOW - 1 * HOUR,
            location="patio",
            camera="cam-1",
            zone="patio",
            labels=("PET",),
            risk="LOW",
        ),
    ):
        service.store_memory(record)
    return service


def _answer(
    question: str, *, session_start: float | None = None
) -> tuple[RecallPlan, str]:
    plan = understand(question, now=NOW)
    result = RecallEngine(memory=_service()).execute(
        plan, now=NOW, session_start=session_start
    )
    return plan, result.utterance


# --- the adapter table -------------------------------------------------------


@pytest.mark.parametrize(
    "text,aggregation,relations,direction,expected",
    [
        ("¿cuántos eventos hubo?", "count", (), None, ResponseIntent.COUNT),
        (
            "¿qué pasó antes de la caída?",
            "summary",
            ("before_after",),
            "before",
            ResponseIntent.BEFORE,
        ),
        (
            "¿qué pasó después de la caída?",
            "summary",
            ("before_after",),
            "after",
            ResponseIntent.AFTER,
        ),
        (
            "¿dónde vi mi mascota?",
            None,
            ("spatial",),
            None,
            ResponseIntent.LAST_SEEN_PLACE,
        ),
        (
            "¿qué pasó mientras estaba fuera?",
            "summary",
            ("timeline",),
            None,
            ResponseIntent.TIMELINE,
        ),
        (
            "¿qué cámaras observaron el mismo evento?",
            None,
            ("correlation",),
            None,
            ResponseIntent.CAMERAS,
        ),
        (
            "¿qué eventos están relacionados?",
            None,
            ("correlation",),
            None,
            ResponseIntent.RELATIONS,
        ),
        (
            "where did you see the pet",
            None,
            ("spatial",),
            None,
            ResponseIntent.LAST_SEEN_PLACE,
        ),
        (
            "¿dónde ocurren las caídas?",
            None,
            ("spatial",),
            None,
            ResponseIntent.SPATIAL,
        ),
        ("resúmeme el día", "summary", (), None, ResponseIntent.SUMMARY),
        ("hola", None, (), None, ResponseIntent.FALLBACK),
    ],
)
def test_resolve_intent_maps_the_mandatory_cases(
    text: str,
    aggregation: str | None,
    relations: tuple[str, ...],
    direction: str | None,
    expected: ResponseIntent,
) -> None:
    assert (
        resolve_intent(
            text=text,
            aggregation=aggregation,
            relations=relations,
            direction=direction,
        )
        is expected
    )


def test_resolve_intent_separates_related_events_from_cameras() -> None:
    related = resolve_intent(
        text="¿qué eventos están relacionados?", relations=("correlation",)
    )
    cameras = resolve_intent(
        text="¿qué cámaras vieron lo mismo?", relations=("correlation",)
    )
    assert related is ResponseIntent.RELATIONS
    assert cameras is ResponseIntent.CAMERAS


def test_resolve_intent_count_wins_over_everything() -> None:
    assert (
        resolve_intent(
            text="¿dónde vi mi mascota?",
            aggregation="count",
            relations=("spatial",),
        )
        is ResponseIntent.COUNT
    )


@pytest.mark.parametrize(
    "aggregation,relations,direction,expected",
    [
        (None, (), None, ResponseIntent.FALLBACK),
        ("count", (), None, ResponseIntent.COUNT),
        ("summary", ("before_after",), "before", ResponseIntent.BEFORE),
        ("summary", ("before_after",), "after", ResponseIntent.AFTER),
        (None, ("timeline",), None, ResponseIntent.TIMELINE),
        (None, ("correlation",), None, ResponseIntent.CAMERAS),
        (None, ("spatial",), None, ResponseIntent.SPATIAL),
        ("summary", (), None, ResponseIntent.SUMMARY),
        (None, ("before_after",), None, ResponseIntent.FALLBACK),
    ],
)
def test_derive_intent_reproduces_the_structural_policy(
    aggregation: str | None,
    relations: tuple[str, ...],
    direction: str | None,
    expected: ResponseIntent,
) -> None:
    assert (
        derive_intent(aggregation=aggregation, relations=relations, direction=direction)
        is expected
    )


# --- the six mandatory cases, end to end -------------------------------------


def test_case_1_last_seen_place_names_place_camera_and_time() -> None:
    plan, answer = _answer("¿Dónde vi mi mascota?")
    assert plan.response_intent is ResponseIntent.LAST_SEEN_PLACE
    assert plan.ops[0].kind is RetrieveKind.LAST_SEEN
    assert answer.startswith("La última vez que vi una mascota fue en patio")
    assert "cámara cam-1" in answer
    assert "GATE_OPEN" not in answer
    assert "FALL DETECTED" not in answer


def test_case_2_before_the_fall_answers_the_before_side() -> None:
    plan, answer = _answer("¿Qué ocurrió antes de la caída?")
    assert plan.response_intent is ResponseIntent.BEFORE
    assert answer.startswith("Antes de FALL DETECTED:")


def test_case_3_after_the_fall_answers_the_after_side() -> None:
    plan, answer = _answer("¿Qué ocurrió después de la caída?")
    assert plan.response_intent is ResponseIntent.AFTER
    assert answer.startswith("Después de FALL DETECTED:")


def test_case_4_while_away_aggregates_the_timeline() -> None:
    plan, answer = _answer(
        "¿Qué pasó mientras estaba fuera?", session_start=NOW - 7 * HOUR
    )
    assert plan.response_intent is ResponseIntent.TIMELINE
    assert "episodios," in answer
    assert "Sucesos:" in answer


def test_case_5_related_events_are_narrated_as_relations() -> None:
    plan, answer = _answer("¿Qué eventos están relacionados?")
    assert plan.response_intent is ResponseIntent.RELATIONS
    assert answer.startswith("Eventos relacionados:")


def test_case_6_cameras_name_the_cameras_that_saw_the_event() -> None:
    plan, answer = _answer("¿Qué cámaras observaron el mismo evento?")
    assert plan.response_intent is ResponseIntent.CAMERAS
    assert answer.startswith("Cámaras:")


def test_the_six_cases_no_longer_share_one_answer() -> None:
    _, one = _answer("¿Dónde vi mi mascota?")
    _, two = _answer("¿Qué ocurrió antes de la caída?")
    _, three = _answer("¿Qué ocurrió después de la caída?")
    _, four = _answer("¿Qué pasó mientras estaba fuera?", session_start=NOW - 7 * HOUR)
    _, five = _answer("¿Qué eventos están relacionados?")
    _, six = _answer("¿Qué cámaras observaron el mismo evento?")
    answers = [one, two, three, four, five, six]
    assert len(set(answers)) == 6
    assert five != six


# --- plan auditability and low-level plans -----------------------------------


def test_plan_to_dict_exposes_the_response_intent() -> None:
    plan = understand("¿dónde vi mi mascota?", now=NOW)
    assert plan_to_dict(plan)["response_intent"] == "last_seen_place"


def test_a_directly_built_plan_has_no_intent_and_still_renders() -> None:
    plan = RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.SPATIAL,),
    )
    assert plan.response_intent is None
    entry = {"op": "relate", "relation": "spatial", "groups": {"patio": ["a"]}}
    evidence = (Evidence(record_id="e-1", ts=NOW - HOUR, location="patio"),)
    out = render_synthesis(plan, evidence, [entry], [], now=NOW, lang="es")
    assert out.startswith("Lugares: patio (1).")


def test_a_directly_built_relations_plan_renders_the_relations_answer() -> None:
    plan = RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.CORRELATION,),
        aggregation=Aggregation.SUMMARY,
        response_intent=ResponseIntent.RELATIONS,
    )
    entry = {"op": "relate", "relation": "derived", "count": 3, "relations": []}
    evidence = (Evidence(record_id="e-1", ts=NOW - HOUR, location="patio"),)
    out = render_synthesis(plan, evidence, [entry], [], now=NOW, lang="es")
    assert out == "3 Eventos relacionados."
