"""Unit tests for DemoSeedService."""

from __future__ import annotations

import time

from src.infrastructure.services.demo_seed_service import (
    DEMO_SEED_DEFINITIONS,
    seed_demo_memory,
)
from src.infrastructure.services.memory_service import VectorMemoryService


def test_seed_demo_memory_inserts_all_definitions() -> None:
    memory = VectorMemoryService()
    fixed_now = 1700000000.0
    records = seed_demo_memory(memory, base_time=fixed_now)

    assert len(records) == len(DEMO_SEED_DEFINITIONS)
    assert memory.size == len(DEMO_SEED_DEFINITIONS)


def test_seed_demo_memory_retrieves_last_seen_gate() -> None:
    memory = VectorMemoryService()
    fixed_now = 1700000000.0
    seed_demo_memory(memory, base_time=fixed_now)

    record = memory.last_seen(label="GATE_OPEN")
    assert record is not None
    assert record.id == "seed-03-gate-access"
    assert record.location == "cam-01"
    assert record.risk == "HIGH"
    # Offset was 79200s (22 hours)
    assert record.timestamp == fixed_now - 79200.0


def test_seed_demo_memory_risk_counts() -> None:
    memory = VectorMemoryService()
    seed_demo_memory(memory, base_time=time.time())

    high_count = memory.count_events("HIGH")
    critical_count = memory.count_events("CRITICAL")
    low_count = memory.count_events("LOW")

    assert high_count == 3
    assert critical_count == 1
    assert low_count == 1


def test_seed_demo_memory_temporal_ordering() -> None:
    memory = VectorMemoryService()
    fixed_now = 1700000000.0
    seed_demo_memory(memory, base_time=fixed_now)

    top_events = memory.top_events(limit=5)
    # The CRITICAL event (seed-04, 3 hours ago) must rank top by risk severity
    assert top_events[0].risk == "CRITICAL"
    assert top_events[0].id == "seed-04-fall-living"


def test_seed_demo_memory_search() -> None:
    memory = VectorMemoryService()
    seed_demo_memory(memory, base_time=time.time())

    results = memory.search_memory("humo cocina smoke", limit=2)
    assert len(results) > 0
    top_record, _ = results[0]
    analysis = top_record.model_analysis.lower()
    assert "smoke" in analysis or "humo" in analysis
    assert top_record.id == "seed-02-smoke-kitchen"
