"""Unit tests for the experimental parallel ``memory_recall`` channel.

These tests prove that the new surface coexists with (and never replaces) the
production ``memory_converse`` tool: both are registered, both answer from the
same store, and the V1 narrative keeps its exact wording.
"""

from __future__ import annotations

import json
import time

import pytest

from src.domain.models.tools import AGENTIC_TOOL_CATALOG
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.domain.services.evidence import format_relative_time, render_abstention
from src.infrastructure.adapters.mcp.memory_resolvers import (
    MEMORY_TOOL_NAMES,
    _relative_time,
    build_memory_converse_resolver,
    build_memory_resolver,
)
from src.infrastructure.adapters.mcp.recall_resolvers import (
    build_memory_recall_resolver,
    recall,
    recall_result_payload,
)
from src.infrastructure.adapters.mcp.tool_resolvers import build_agentic_tool_registry
from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService

_NOW = time.time()
_FIXED_NOW = 1_000_000.0


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


def _fixed_memory() -> VectorMemoryService:
    memory = VectorMemoryService()
    memory.store_memory(
        MemoryRecord(
            id="fixed-pet",
            timestamp=_FIXED_NOW - 7_200.0,
            location="patio",
            source="camera_alert",
            detections=({"label": "PET"},),
            risk="HIGH",
            model_analysis="mascota en el patio",
        )
    )
    return memory


def test_memory_recall_tool_is_in_the_catalog_and_tool_names() -> None:
    names = [tool.name for tool in AGENTIC_TOOL_CATALOG]
    assert "memory_recall" in names
    assert "memory_recall" in MEMORY_TOOL_NAMES
    assert len(set(names)) == len(names)


def test_memory_recall_declares_query_as_required() -> None:
    tool = next(t for t in AGENTIC_TOOL_CATALOG if t.name == "memory_recall")
    assert tool.required_fields == frozenset({"query"})
    assert tool.validate_arguments({}) == ("query",)


def test_memory_recall_dispatch_routes_to_the_recall_engine() -> None:
    resolver = build_memory_resolver("memory_recall", _memory())
    assert resolver is not None


@pytest.mark.asyncio
async def test_memory_recall_resolver_requires_query() -> None:
    resolver = build_memory_recall_resolver(_memory())
    response = await resolver({"lang": "es"})
    assert response.is_error is True
    assert "query" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_recall_answers_from_memory_with_evidence() -> None:
    resolver = build_memory_recall_resolver(_memory())
    response = await resolver({"query": "¿cuándo viste una mascota?", "now": _NOW})
    text = response.content[0].data
    assert response.is_error is False
    assert "PET" in text
    assert "cam-01" in text
    assert "evidencia:" in text
    assert "pet-now" in text
    assert "trace:" in text


@pytest.mark.asyncio
async def test_memory_recall_abstains_on_an_empty_store() -> None:
    resolver = build_memory_recall_resolver(VectorMemoryService())
    response = await resolver({"query": "mascota", "now": _NOW})
    assert response.is_error is False
    assert render_abstention(lang="es") in response.content[0].data
    assert "evidencia: ninguna" in response.content[0].data


@pytest.mark.asyncio
async def test_memory_recall_is_llm_free_through_the_registry() -> None:
    fake_llm = _FakeLLM()
    registry = build_agentic_tool_registry(fake_llm, memory=_memory())
    response = await registry.call_tool(
        "memory_recall", {"query": "mascota", "now": _NOW}
    )
    assert response.is_error is False
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_memory_recall_is_listed_by_the_tool_registry() -> None:
    registry = build_agentic_tool_registry(_FakeLLM(), memory=_memory())
    tools = await registry.list_tools()
    names = {tool.name for tool in tools}
    assert "memory_recall" in names
    assert "memory_converse" in names


@pytest.mark.asyncio
async def test_memory_recall_does_not_replace_memory_converse() -> None:
    memory = _memory()
    converse = build_memory_converse_resolver(memory)
    recall_resolver = build_memory_recall_resolver(memory)

    v1 = await converse({"query": "¿cuándo viste una mascota?"})
    v2 = await recall_resolver({"query": "¿cuándo viste una mascota?", "now": _NOW})

    assert v1.is_error is False and v2.is_error is False
    assert v1.content[0].data == (
        "La última detección de una mascota ocurrió hace 2 horas en cam-01."
    )
    assert v2.content[0].data != v1.content[0].data
    assert "evidencia:" in v2.content[0].data
    assert memory.size == 2


@pytest.mark.asyncio
async def test_memory_recall_is_injected_now_is_wall_clock_independent() -> None:
    resolver = build_memory_recall_resolver(_fixed_memory())
    first = await resolver({"query": "mascota", "now": _FIXED_NOW})
    second = await resolver({"query": "mascota", "now": _FIXED_NOW})
    assert first.content[0].data == second.content[0].data
    assert "hace 2 horas" in first.content[0].data


@pytest.mark.asyncio
async def test_memory_recall_honours_explicit_english() -> None:
    resolver = build_memory_recall_resolver(VectorMemoryService())
    response = await resolver({"query": "pet", "lang": "en", "now": _NOW})
    assert render_abstention(lang="en") in response.content[0].data
    assert "evidence: none" in response.content[0].data


def test_recall_function_is_deterministic_and_llm_free() -> None:
    memory = _fixed_memory()
    first = recall(memory, "mascota", now=_FIXED_NOW)
    second = recall(memory, "mascota", now=_FIXED_NOW)
    assert first == second
    assert first.trace.evidence_ids == ("fixed-pet",)


def test_recall_result_payload_is_json_safe() -> None:
    payload = recall_result_payload(recall(_fixed_memory(), "mascota", now=_FIXED_NOW))
    json.dumps(payload)


def test_recall_result_payload_exposes_engine_evidence_and_trace() -> None:
    payload = recall_result_payload(
        recall(_memory(), "¿cuándo viste una mascota?", now=_NOW)
    )
    assert payload["engine"] == {"name": "echo-recall", "version": 1}
    assert payload["is_error"] is False
    ids = [item["id"] for item in payload["evidence"]]  # type: ignore[index]
    assert ids == ["pet-now"]
    assert payload["trace"]["evidence_ids"] == ["pet-now"]  # type: ignore[index]
    assert payload["trace"]["plan"]["lang"] == "es"  # type: ignore[index]


def test_recall_result_payload_reports_abstention_without_evidence() -> None:
    payload = recall_result_payload(recall(VectorMemoryService(), "mascota", now=_NOW))
    assert payload["evidence"] == []
    assert payload["response"] == render_abstention(lang="es")
    assert payload["trace"]["evidence_ids"] == []  # type: ignore[index]


@pytest.mark.parametrize(
    "delta",
    [
        0.0,
        30.0,
        59.0,
        60.0,
        61.0,
        3_599.0,
        3_600.0,
        3_601.0,
        7_200.0,
        86_399.0,
        86_400.0,
        86_401.0,
        172_800.0,
        604_799.0,
        604_800.0,
        604_801.0,
        1_209_600.0,
        -100.0,
    ],
)
def test_v1_relative_time_matches_the_domain_helper(delta: float) -> None:
    """Prepares the documented A3 unification of both helpers.

    ``memory_resolvers._relative_time`` (V1) and the domain
    ``format_relative_time`` are expected to be byte-identical; this test locks
    that equivalence before any V1 function is made to delegate.
    """
    for lang in ("es", "en"):
        assert _relative_time(delta, _NOW, lang) == format_relative_time(
            delta, _NOW, lang
        )


class _FakeLLM(LLMServicePort):
    """Minimal double proving the recall channel never reaches an LLM."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.last_request = request
        return LLMResponse(text="unused", model_id="fake-model")
