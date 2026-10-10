"""Isolated tests for the Alexa memory MCP tools (no LLM involved)."""

from __future__ import annotations

import time

import pytest

from src.domain.models.tools import AGENTIC_TOOL_CATALOG
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.mcp.memory_resolvers import (
    MEMORY_TOOL_NAMES,
    build_memory_last_seen_resolver,
    build_memory_resolver,
    build_memory_search_resolver,
    build_memory_summary_resolver,
)
from src.infrastructure.adapters.mcp.tool_resolvers import build_agentic_tool_registry
from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService

_NOW = time.time()


def _memory() -> VectorMemoryService:
    memory = VectorMemoryService()
    memory.store_memory(
        MemoryRecord(
            id="pet-now",
            timestamp=_NOW - 7_200.0,
            location="cam-01",
            source="camera_alert",
            detections=({"label": "PET"},),
            risk="HIGH",
            model_analysis="la mascota corre cerca de la reja",
        )
    )
    memory.store_memory(
        MemoryRecord(
            id="gate-now",
            timestamp=_NOW - 14_400.0,
            location="cam-01",
            source="camera_alert",
            detections=({"label": "GATE_OPEN"},),
            risk="HIGH",
            model_analysis="la reja quedo abierta de par en par",
        )
    )
    return memory


def _seed_timeline() -> VectorMemoryService:
    memory = VectorMemoryService()
    for index, offset_hours in enumerate((1.0, 2.0, 20.0)):
        memory.store_memory(
            MemoryRecord(
                id=f"t-{index}",
                timestamp=_NOW - offset_hours * 3_600.0,
                location="cam-01",
                source="camera_alert",
                detections=({"label": "PET"},),
                risk="HIGH",
                model_analysis="mascota en el perímetro",
            )
        )
    return memory


@pytest.mark.asyncio
async def test_memory_last_seen_answers_with_recency_and_place() -> None:
    resolver = build_memory_last_seen_resolver(_memory())
    response = await resolver({"label": "PET"})
    assert response.is_error is False
    assert response.content[0].data == (
        "La última detección de una mascota ocurrió hace 2 horas en cam-01."
    )


@pytest.mark.asyncio
async def test_memory_last_seen_requires_label() -> None:
    resolver = build_memory_last_seen_resolver(_memory())
    response = await resolver({"location": "cam-01"})
    assert response.is_error is True
    assert "label" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_last_seen_reports_absence() -> None:
    resolver = build_memory_last_seen_resolver(VectorMemoryService())
    response = await resolver({"label": "PERSON_ELDERLY"})
    assert response.is_error is False
    assert "No he observado una persona mayor en la memoria local." in (
        response.content[0].data
    )


@pytest.mark.asyncio
async def test_memory_search_returns_ranked_results() -> None:
    resolver = build_memory_search_resolver(_memory())
    response = await resolver({"query": "la reja quedo abierta", "limit": 2})
    assert response.is_error is False
    lines = response.content[0].data.splitlines()
    assert lines[0].startswith("He encontrado 2 recuerdo(s)")
    assert "GATE_OPEN" in lines[1]
    assert "score" in lines[1]


@pytest.mark.asyncio
async def test_memory_search_requires_query() -> None:
    resolver = build_memory_search_resolver(_memory())
    response = await resolver({})
    assert response.is_error is True
    assert "query" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_search_reports_no_matches() -> None:
    resolver = build_memory_search_resolver(_memory())
    response = await resolver({"query": "zzz totalmente distinto", "min_score": 0.9})
    assert response.is_error is False
    assert "No he encontrado recuerdos para: zzz" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_summary_reports_counts_recency_and_absence() -> None:
    resolver = build_memory_summary_resolver(_seed_timeline())
    response = await resolver({"hours": 24})
    text = response.content[0].data
    assert response.is_error is False
    assert "3 veces una mascota" in text
    assert "he observado" in text
    assert "La última detección de una mascota ocurrió hace 1 hora" in text
    assert "No he observado la reja abierta durante las últimas 24 horas." in text
    assert "No he observado una persona mayor durante las últimas 24 horas." in text


@pytest.mark.asyncio
async def test_memory_summary_reports_empty_window() -> None:
    resolver = build_memory_summary_resolver(_memory())
    response = await resolver({"hours": 1})
    assert response.is_error is False
    assert "no he registrado ninguna alerta memorable" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_resolver_dispatch_handles_missing_service() -> None:
    resolver = build_memory_resolver("memory_search", None)
    response = await resolver({"query": "cualquier cosa"})
    assert response.is_error is True
    assert "memory service is not available" in response.content[0].data


def test_catalog_exposes_memory_tools() -> None:
    names = [tool.name for tool in AGENTIC_TOOL_CATALOG]
    assert MEMORY_TOOL_NAMES <= set(names)


@pytest.mark.asyncio
async def test_memory_tools_execute_through_agentic_registry() -> None:
    fake_llm = _FakeLLM()
    registry = build_agentic_tool_registry(fake_llm, memory=_memory())
    response = await registry.call_tool("memory_last_seen", {"label": "GATE_OPEN"})
    assert response.is_error is False
    assert "La última detección de la reja abierta ocurrió hace 4 horas en cam-01." in (
        response.content[0].data
    )
    assert fake_llm.calls == 0


class _FakeLLM(LLMServicePort):
    """Minimal LLMServicePort double proving memory tools never call it."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text="unused", model_id="fake-model")
