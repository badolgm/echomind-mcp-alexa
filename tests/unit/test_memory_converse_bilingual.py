"""Unit tests for bilingual English/Spanish conversational memory narratives."""

from __future__ import annotations

import time
import pytest

from src.infrastructure.adapters.mcp.memory_resolvers import (
    build_memory_converse_resolver,
)
from src.infrastructure.services.demo_seed_service import seed_demo_memory
from src.infrastructure.services.memory_service import VectorMemoryService


def _seeded_memory() -> VectorMemoryService:
    memory = VectorMemoryService()
    # Fixed base timestamp for predictable relative time tests
    # now = 1700000000.0
    seed_demo_memory(memory, base_time=time.time())
    return memory


@pytest.mark.asyncio
async def test_converse_english_last_seen_gate() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "When was the gate last seen open?"})
    assert response.is_error is False
    text = response.content[0].data
    assert "The last detection of the open gate occurred" in text
    assert "at cam-01." in text


@pytest.mark.asyncio
async def test_converse_english_last_seen_pet() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "When did you last see a pet?"})
    assert response.is_error is False
    text = response.content[0].data
    assert "The last detection of a pet occurred" in text
    assert "at patio." in text


@pytest.mark.asyncio
async def test_converse_english_summary_today() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "What happened today?"})
    assert response.is_error is False
    text = response.content[0].data
    assert "During the last 24 hours I have observed:" in text


@pytest.mark.asyncio
async def test_converse_english_critical_events() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "Were there any critical events?"})
    assert response.is_error is False
    text = response.content[0].data
    assert text.startswith("Recent critical events:")
    assert "CRITICAL" in text
    assert "living" in text


@pytest.mark.asyncio
async def test_converse_english_count_high_risk() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "How many HIGH risk alerts occurred?"})
    assert response.is_error is False
    text = response.content[0].data
    assert "I observed 3 HIGH events during the requested period." in text


@pytest.mark.asyncio
async def test_converse_english_current_state() -> None:
    memory = _seeded_memory()

    def _state() -> dict[str, object]:
        return {"detections": [{"label": "MOTION", "confidence": 0.85}]}

    resolver = build_memory_converse_resolver(memory, current_state=_state)
    response = await resolver({"query": "What is happening right now?"})
    assert response.is_error is False
    text = response.content[0].data
    assert "Currently I detect motion at main access." in text


@pytest.mark.asyncio
async def test_converse_explicit_lang_priority() -> None:
    memory = _seeded_memory()
    resolver = build_memory_converse_resolver(memory)

    # English query but forced lang="es"
    resp_es = await resolver(
        {
            "query": "When did you see a pet?",
            "lang": "es",
        }
    )
    assert "La última detección de una mascota ocurrió" in resp_es.content[0].data

    # Spanish query but forced lang="en"
    resp_en = await resolver(
        {
            "query": "¿Cuándo viste una mascota?",
            "lang": "en",
        }
    )
    assert "The last detection of a pet occurred" in resp_en.content[0].data


@pytest.mark.asyncio
async def test_converse_absent_item_in_english() -> None:
    memory = VectorMemoryService()
    resolver = build_memory_converse_resolver(memory)

    response = await resolver({"query": "When was the gate last seen open?"})
    assert response.is_error is False
    assert response.content[0].data == (
        "I have not observed the open gate in local memory."
    )
