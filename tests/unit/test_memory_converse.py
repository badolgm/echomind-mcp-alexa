"""Isolated tests for memory_converse (deterministic conversational routing)."""

from __future__ import annotations

import time

import pytest

from src.domain.models.tools import AGENTIC_TOOL_CATALOG
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.mcp.memory_resolvers import (
    build_memory_converse_resolver,
)
from src.infrastructure.adapters.mcp.tool_resolvers import build_agentic_tool_registry
from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService


def _store(
    memory: VectorMemoryService,
    record_id: str,
    offset: float,
    risk: str,
    labels: tuple[str, ...],
) -> None:
    memory.store_memory(
        MemoryRecord(
            id=record_id,
            timestamp=time.time() - offset,
            location="cam-01",
            source="camera_alert",
            detections=tuple({"label": label} for label in labels),
            risk=risk,
            model_analysis=f"observación de {', '.join(labels)}",
        )
    )


def _memory() -> VectorMemoryService:
    memory = VectorMemoryService()
    _store(memory, "person", 840.0, "HIGH", ("PERSON",))
    _store(memory, "motion", 3600.0, "HIGH", ("MOTION",))
    _store(memory, "pet-1", 7200.0, "HIGH", ("PET",))
    _store(memory, "pet-2", 10800.0, "HIGH", ("PET",))
    _store(memory, "gate", 14400.0, "HIGH", ("GATE_OPEN",))
    _store(memory, "fire", 5000.0, "CRITICAL", ("FIRE",))
    return memory


@pytest.mark.asyncio
async def test_converse_last_seen_person() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Cuándo viste por última vez una persona?"})
    assert response.is_error is False
    assert response.content[0].data == (
        "La última detección de una persona ocurrió hace 14 minutos en cam-01."
    )


@pytest.mark.asyncio
async def test_converse_summary_today() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Qué recuerdas de hoy?"})
    text = response.content[0].data
    assert response.is_error is False
    assert "Durante las últimas 24 horas he observado" in text
    assert "2 veces una mascota" in text


@pytest.mark.asyncio
async def test_converse_count_high_events() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Cuántos eventos HIGH ocurrieron?"})
    assert response.content[0].data == (
        "He observado 5 eventos HIGH durante el período consultado."
    )


@pytest.mark.asyncio
async def test_converse_top_events() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver(
        {"query": "¿Cuáles fueron los eventos más importantes de hoy?"}
    )
    text = response.content[0].data
    assert text.startswith("Los eventos más importantes del período consultado:")
    assert "CRITICAL" in text


@pytest.mark.asyncio
async def test_converse_high_risk_situations() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Qué situaciones de riesgo recuerdas?"})
    text = response.content[0].data
    assert text.startswith("He registrado 5 situaciones de riesgo:")
    assert "HIGH" in text


@pytest.mark.asyncio
async def test_converse_critical_events_present_and_absent() -> None:
    resolver = build_memory_converse_resolver(_memory())
    present = await resolver({"query": "¿Hubo eventos críticos recientemente?"})
    assert present.content[0].data.startswith("Eventos críticos recientes:")
    assert "CRITICAL" in present.content[0].data

    empty = VectorMemoryService()
    resolver_empty = build_memory_converse_resolver(empty)
    absent = await resolver_empty({"query": "¿Hubo eventos críticos recientemente?"})
    assert absent.content[0].data == "No hubo eventos críticos recientemente."


@pytest.mark.asyncio
async def test_converse_current_state_plus_history() -> None:
    memory = _memory()

    def _state() -> dict[str, object]:
        return {"detections": [{"label": "MOTION", "confidence": 0.71}]}

    resolver = build_memory_converse_resolver(memory, current_state=_state)
    response = await resolver({"query": "¿Qué ocurre ahora?"})
    text = response.content[0].data
    assert text.startswith("Actualmente detecto movimiento en el acceso principal.")
    assert "He observado eventos similares 1 vez durante las últimas 24 horas." in text


@pytest.mark.asyncio
async def test_converse_current_state_without_provider() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Qué ocurre ahora?"})
    assert response.content[0].data == "Actualmente no tengo detecciones activas."


@pytest.mark.asyncio
async def test_converse_requires_query() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({})
    assert response.is_error is True
    assert "query" in response.content[0].data


@pytest.mark.asyncio
async def test_converse_unknown_query_uses_search() -> None:
    resolver = build_memory_converse_resolver(_memory())
    response = await resolver({"query": "¿Hubo algo raro en el patio?"})
    assert response.is_error is False
    assert "He encontrado" in response.content[0].data


@pytest.mark.asyncio
async def test_converse_executes_through_agentic_registry_without_llm() -> None:
    fake_llm = _FakeLLM()
    memory = _memory()

    def _state() -> dict[str, object]:
        return {"detections": [{"label": "GATE_OPEN", "confidence": 0.9}]}

    registry = build_agentic_tool_registry(
        fake_llm, memory=memory, current_state_provider=_state
    )
    names = [tool.name for tool in await registry.list_tools()]
    assert "memory_converse" in names

    response = await registry.call_tool(
        "memory_converse", {"query": "¿Cuándo viste una mascota?"}
    )
    assert response.is_error is False
    assert response.content[0].data == (
        "La última detección de una mascota ocurrió hace 2 horas en cam-01."
    )
    assert fake_llm.calls == 0


def test_catalog_exposes_memory_converse() -> None:
    names = [tool.name for tool in AGENTIC_TOOL_CATALOG]
    assert "memory_converse" in names


class _FakeLLM(LLMServicePort):
    """Minimal LLMServicePort double proving conversation never calls it."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text="unused", model_id="fake-model")
