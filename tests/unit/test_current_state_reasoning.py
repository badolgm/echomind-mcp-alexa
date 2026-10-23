"""Unit tests for the A7C current-state renderer (pure, no store access)."""

from __future__ import annotations

import pytest

from src.domain.services.current_state_reasoning import render_state_answer


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "risk": "LOW",
        "signals": [],
        "detections": [],
        "temperature_c": 22.4,
        "smoke_density": 0.02,
        "gate_open": False,
        "door_open": False,
        "pet_proximity": 0.12,
        "motion_score": 0.0,
        "source": "live",
        "ts": 1760000000.0,
    }
    state.update(overrides)
    return state


def test_gate_closed_mandatory_answer() -> None:
    answer = render_state_answer("gate", _state(), "es", polarity="closed")
    assert answer == "Sí. La reja se encuentra cerrada actualmente."


def test_gate_closed_contradicted_by_fact() -> None:
    answer = render_state_answer(
        "gate", _state(gate_open=True), "es", polarity="closed"
    )
    assert answer == "No. La reja está abierta ahora mismo."


def test_gate_open_confirmed_and_contradicted() -> None:
    open_state = _state(gate_open=True)
    confirmed = render_state_answer("gate", open_state, "es", polarity="open")
    assert confirmed == "Sí. La reja está abierta ahora mismo."
    contradicted = render_state_answer("gate", open_state, "es", polarity="closed")
    assert contradicted == "No. La reja está abierta ahora mismo."


def test_gate_without_polarity_states_the_fact_only() -> None:
    answer = render_state_answer("gate", _state(), "es")
    assert answer == "La reja se encuentra cerrada actualmente."


def test_motion_inactive_mandatory_answer() -> None:
    answer = render_state_answer("motion", _state(), "es")
    assert answer == "No detecto movimiento activo."


def test_motion_active_from_detections() -> None:
    state = _state(detections=[{"label": "MOTION", "confidence": 0.71}])
    assert render_state_answer("motion", state, "es") == (
        "Sí, detecto movimiento activo."
    )


def test_temperature_mandatory_answer() -> None:
    answer = render_state_answer("temperature", _state(), "es")
    assert answer == "La temperatura actual es 22.4°C."


def test_risk_mandatory_answer() -> None:
    answer = render_state_answer("risk", _state(), "es")
    assert answer == "El nivel de riesgo actual es LOW."


def test_door_closed_uses_door_noun() -> None:
    answer = render_state_answer("door", _state(), "es", polarity="closed")
    assert answer == "Sí. La puerta se encuentra cerrada actualmente."


def test_smoke_absent_and_active() -> None:
    assert render_state_answer("smoke", _state(), "es") == ("No detecto humo activo.")
    active = _state(detections=[{"label": "SMOKE", "confidence": 0.9}])
    assert render_state_answer("smoke", active, "es") == ("Sí, detecto humo activo.")


def test_missing_fields_degrade_to_honest_unavailable() -> None:
    assert render_state_answer("gate", {}, "es") == (
        "No dispongo del estado actual de la reja."
    )
    assert render_state_answer("temperature", {}, "es") == (
        "No dispongo de la temperatura actual."
    )
    assert render_state_answer("risk", {}, "es") == (
        "No dispongo del nivel de riesgo actual."
    )
    assert render_state_answer("motion", {}, "es") == (
        "No dispongo del estado actual del movimiento."
    )


def test_invalid_temperature_value_degrades_honestly() -> None:
    assert render_state_answer("temperature", _state(temperature_c="hot"), "es") == (
        "No dispongo de la temperatura actual."
    )


def test_empty_risk_degrades_honestly() -> None:
    assert render_state_answer("risk", _state(risk="  "), "es") == (
        "No dispongo del nivel de riesgo actual."
    )


def test_overview_composes_only_from_present_fields() -> None:
    answer = render_state_answer("overview", _state(), "es")
    assert answer == (
        "El nivel de riesgo actual es LOW. "
        "No detecto incidencias activas. "
        "La temperatura actual es 22.4°C."
    )


def test_overview_with_detections_lists_phrases() -> None:
    state = _state(
        risk="HIGH",
        detections=[{"label": "MOTION", "confidence": 0.8}, {"label": "PET"}],
    )
    answer = render_state_answer("overview", state, "es")
    assert answer == (
        "El nivel de riesgo actual es HIGH. "
        "Detecto movimiento, una mascota. "
        "La temperatura actual es 22.4°C."
    )


def test_overview_empty_state_is_honest() -> None:
    assert render_state_answer("overview", {}, "es") == (
        "No dispongo del estado actual de la vivienda."
    )


def test_english_answers() -> None:
    assert render_state_answer("gate", _state(), "en", polarity="closed") == (
        "Yes. The gate is currently closed."
    )
    assert render_state_answer("motion", _state(), "en") == (
        "I detect no active motion."
    )
    assert render_state_answer("temperature", _state(), "en") == (
        "The current temperature is 22.4°C."
    )
    assert render_state_answer("risk", _state(), "en") == (
        "The current risk level is LOW."
    )


def test_unknown_topic_degrades_honestly() -> None:
    answer = render_state_answer("garden", _state(), "es")
    assert answer == "No dispongo de una respuesta de estado para esa consulta."


@pytest.mark.parametrize("topic", ["gate", "door", "motion", "risk", "overview"])
def test_rendering_is_deterministic(topic: str) -> None:
    state = _state()
    assert render_state_answer(topic, state, "es") == render_state_answer(
        topic, state, "es"
    )
