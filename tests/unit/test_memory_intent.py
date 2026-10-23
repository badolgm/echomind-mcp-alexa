"""Isolated tests for the deterministic memory-intent classifier (V3)."""

from __future__ import annotations

from src.domain.services.memory_intent import (
    MemoryIntentClassifier,
    MemoryIntentType,
)


def _classify(text: str):
    return MemoryIntentClassifier().classify(text)


def test_ultima_vez_una_persona_maps_to_last_seen() -> None:
    intent = _classify("¿Cuándo viste por última vez una persona?")
    assert intent.intent is MemoryIntentType.LAST_SEEN
    assert intent.label == "PERSON"


def test_cuando_viste_una_mascota_maps_to_last_seen() -> None:
    intent = _classify("¿Cuándo viste una mascota?")
    assert intent.intent is MemoryIntentType.LAST_SEEN
    assert intent.label == "PET"


def test_reja_abierta_hoy_maps_to_last_seen() -> None:
    intent = _classify("¿La reja ha estado abierta hoy?")
    assert intent.intent is MemoryIntentType.LAST_SEEN
    assert intent.label == "GATE_OPEN"


def test_persona_mayor_recientemente_maps_to_last_seen() -> None:
    intent = _classify("¿Has visto una persona mayor recientemente?")
    assert intent.intent is MemoryIntentType.LAST_SEEN
    assert intent.label == "PERSON_ELDERLY"


def test_cuantos_eventos_high_maps_to_event_count() -> None:
    intent = _classify("¿Cuántos eventos HIGH ocurrieron?")
    assert intent.intent is MemoryIntentType.EVENT_COUNT
    assert intent.risk == "HIGH"


def test_que_recuerdas_de_hoy_maps_to_summary() -> None:
    intent = _classify("¿Qué recuerdas de hoy?")
    assert intent.intent is MemoryIntentType.SUMMARY
    assert intent.hours == 24.0


def test_ultimas_24_horas_maps_to_summary_with_window() -> None:
    intent = _classify("¿Qué ocurrió durante las últimas 24 horas?")
    assert intent.intent is MemoryIntentType.SUMMARY
    assert intent.hours == 24.0


def test_que_ocurre_ahora_maps_to_current_state() -> None:
    intent = _classify("¿Qué ocurre ahora?")
    assert intent.intent is MemoryIntentType.CURRENT_STATE


def test_situaciones_de_riesgo_maps_to_high_risk() -> None:
    intent = _classify("¿Qué situaciones de riesgo recuerdas?")
    assert intent.intent is MemoryIntentType.HIGH_RISK


def test_eventos_criticos_maps_to_critical_risk() -> None:
    intent = _classify("¿Hubo eventos críticos recientemente?")
    assert intent.intent is MemoryIntentType.CRITICAL_RISK


def test_eventos_mas_importantes_maps_to_top_events() -> None:
    intent = _classify("¿Cuáles fueron los eventos más importantes de hoy?")
    assert intent.intent is MemoryIntentType.TOP_EVENTS


def test_ha_ocurrido_antes_maps_to_summary() -> None:
    intent = _classify("¿ha ocurrido antes?")
    assert intent.intent is MemoryIntentType.SUMMARY


def test_unknown_query_maps_to_search() -> None:
    intent = _classify("¿Hubo algo raro en el patio?")
    assert intent.intent is MemoryIntentType.SEARCH
    assert "raro" in intent.query


def test_empty_query_maps_to_search() -> None:
    intent = _classify("   ")
    assert intent.intent is MemoryIntentType.SEARCH
