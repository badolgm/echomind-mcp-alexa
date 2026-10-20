"""Golden classification tests for the A7C query router."""

from __future__ import annotations

import pytest

from src.domain.services.query_router import (
    QueryKind,
    StateTopic,
    route_query,
)

_STATE_CASES = [
    ("¿La reja está cerrada?", StateTopic.GATE),
    ("¿La puerta está abierta?", StateTopic.DOOR),
    ("¿Hay movimiento ahora?", StateTopic.MOTION),
    ("¿Qué temperatura hay?", StateTopic.TEMPERATURE),
    ("¿Cuál es el riesgo actual?", StateTopic.RISK),
    ("¿Hay humo?", StateTopic.SMOKE),
    ("¿Qué ocurre ahora?", StateTopic.OVERVIEW),
    ("¿Cómo está la reja hoy?", StateTopic.GATE),
    ("¿Hace frío ahora?", StateTopic.TEMPERATURE),
    ("Is the gate closed?", StateTopic.GATE),
    ("Is there motion now?", StateTopic.MOTION),
    ("What is the current risk?", StateTopic.RISK),
    ("What's the temperature?", StateTopic.TEMPERATURE),
]

_MEMORY_CASES = [
    "¿Dónde vi mi mascota?",
    "¿Qué ocurrió antes de la caída?",
    "¿Qué ocurrió después de la caída?",
    "¿Qué pasó mientras estaba fuera?",
    "¿Qué cámaras observaron el mismo evento?",
    "¿Dónde está la reja?",
    "¿Qué recuerdas de hoy?",
    "¿Qué situaciones de riesgo recuerdas?",
    "¿Hubo algo raro en el patio?",
    "Where did you see my pet?",
    "What happened before the fall?",
    "Which cameras saw the same event?",
]


@pytest.mark.parametrize(("query", "topic"), _STATE_CASES)
def test_state_questions_route_to_current_state(query: str, topic: StateTopic) -> None:
    decision = route_query(query)
    assert decision.kind is QueryKind.CURRENT_STATE
    assert decision.topic is topic
    assert decision.matched


@pytest.mark.parametrize("query", _MEMORY_CASES)
def test_memory_questions_route_to_recall(query: str) -> None:
    decision = route_query(query)
    assert decision.kind is QueryKind.RECALL
    assert decision.topic is None


@pytest.mark.parametrize(
    "query",
    [
        "¿La reja ha estado abierta hoy?",
        "¿Qué pasó ahora?",
        "¿Cuántos eventos hay ahora?",
        "¿Se movió alguien?",
        "¿Hay alguien en la puerta?",
        "¿Dejaste la puerta abierta?",
        "When was the gate last seen open?",
        "Were there any critical events?",
        "How many HIGH risk alerts occurred?",
    ],
)
def test_ambiguous_questions_resolve_to_recall(query: str) -> None:
    assert route_query(query).kind is QueryKind.RECALL


def test_person_anchor_vetoes_gate_but_not_motion() -> None:
    person_motion = route_query("¿Se está moviendo alguien?")
    assert person_motion.kind is QueryKind.CURRENT_STATE
    assert person_motion.topic is StateTopic.MOTION

    person_door = route_query("¿Hay alguien en la puerta?")
    assert person_door.kind is QueryKind.RECALL


def test_default_is_recall_and_visible_in_matched() -> None:
    decision = route_query("nonsense xyz 123")
    assert decision.kind is QueryKind.RECALL
    assert decision.matched == ("default",)


def test_count_beats_present_state() -> None:
    decision = route_query("¿Cuántos eventos de riesgo hay ahora?")
    assert decision.kind is QueryKind.RECALL
    assert decision.matched[0].startswith("count:")


def test_empty_query_is_recall() -> None:
    decision = route_query("   ")
    assert decision.kind is QueryKind.RECALL
    assert decision.matched == ("empty",)


def test_language_detection_and_explicit_override() -> None:
    assert route_query("¿Qué temperatura hay?").lang == "es"
    assert route_query("What is the temperature?").lang == "en"
    assert route_query("¿Qué temperatura hay?", lang="en").lang == "en"


def test_past_beats_present_marker() -> None:
    decision = route_query("¿La reja estaba abierta ahora?")
    assert decision.kind is QueryKind.RECALL
    assert decision.matched[0].startswith("past:")


def test_decision_is_deterministic() -> None:
    first = route_query("¿Hay movimiento ahora?")
    second = route_query("¿Hay movimiento ahora?")
    assert first == second
