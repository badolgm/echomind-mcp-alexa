"""V1 memory_converse routing through the A7C query router.

Verifies the functional bug fix end to end: a current-state question now
answers from ``watch.last_state`` and never from ``search_memory``, while
every memory question and the pinned overview answers keep their exact
pre-A7C behaviour.
"""

from __future__ import annotations

import time

import pytest

from src.infrastructure.adapters.mcp.memory_resolvers import (
    build_memory_converse_resolver,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)


def _state(**overrides: object) -> dict[str, object]:
    """Shape produced by ``AmbientWatchService.tick`` (baseline, calm home)."""
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


def _memory() -> VectorMemoryService:
    memory = VectorMemoryService()
    memory.store_memory(
        MemoryRecord(
            id="pet-1",
            timestamp=time.time() - 7200.0,
            location="cam-01",
            source="camera_alert",
            detections=({"label": "PET"},),
            risk="HIGH",
            model_analysis="observación de PET",
        )
    )
    memory.store_memory(
        MemoryRecord(
            id="gate",
            timestamp=time.time() - 14400.0,
            location="cam-01",
            source="camera_alert",
            detections=({"label": "GATE_OPEN"},),
            risk="HIGH",
            model_analysis="observación de GATE_OPEN",
        )
    )
    return memory


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("¿La reja está cerrada?", "Sí. La reja se encuentra cerrada actualmente."),
        ("¿Hay movimiento ahora?", "No detecto movimiento activo."),
        ("¿Qué temperatura hay?", "La temperatura actual es 22.4°C."),
        ("¿Cuál es el riesgo actual?", "El nivel de riesgo actual es LOW."),
    ],
)
async def test_state_questions_answer_from_live_state(
    query: str, expected: str
) -> None:
    resolver = build_memory_converse_resolver(_memory(), current_state=_state)
    response = await resolver({"query": query})
    assert response.is_error is False
    assert response.content[0].data == expected


@pytest.mark.asyncio
async def test_state_question_without_provider_is_honest() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿La reja está cerrada?"})
    assert response.content[0].data == ("No dispongo del estado actual de la reja.")


@pytest.mark.asyncio
async def test_state_question_never_hits_memory_store() -> None:
    resolver = build_memory_converse_resolver(VectorMemoryService())
    response = await resolver({"query": "¿La reja está cerrada?"})
    data = response.content[0].data
    assert "No he encontrado recuerdos" not in data
    assert "No tengo registros" not in data
    assert data == "No dispongo del estado actual de la reja."


@pytest.mark.asyncio
async def test_gate_open_state_contradicts_closed_question() -> None:
    resolver = build_memory_converse_resolver(
        _memory(), current_state=lambda: _state(gate_open=True)
    )
    response = await resolver({"query": "¿La reja está cerrada?"})
    assert response.content[0].data == "No. La reja está abierta ahora mismo."


@pytest.mark.asyncio
async def test_motion_detected_state() -> None:
    resolver = build_memory_converse_resolver(
        _memory(),
        current_state=lambda: _state(
            detections=[{"label": "MOTION", "confidence": 0.8}]
        ),
    )
    response = await resolver({"query": "¿Hay movimiento ahora?"})
    assert response.content[0].data == "Sí, detecto movimiento activo."


@pytest.mark.asyncio
async def test_overview_keeps_pinned_v1_answer() -> None:
    resolver = build_memory_converse_resolver(
        _memory(),
        current_state=lambda: _state(
            detections=[{"label": "MOTION", "confidence": 0.71}]
        ),
    )
    response = await resolver({"query": "¿Qué ocurre ahora?"})
    assert response.content[0].data.startswith("Actualmente detecto movimiento")


@pytest.mark.asyncio
async def test_memory_questions_still_use_the_store() -> None:
    resolver = build_memory_converse_resolver(_memory(), current_state=_state)
    response = await resolver({"query": "¿Cuándo viste una mascota?"})
    data = response.content[0].data
    assert data.startswith("La última detección de una mascota")
    assert "cam-01" in data


@pytest.mark.asyncio
async def test_state_answer_in_english() -> None:
    resolver = build_memory_converse_resolver(_memory(), current_state=_state)
    response = await resolver({"query": "Is the gate closed?"})
    assert response.content[0].data == "Yes. The gate is currently closed."
