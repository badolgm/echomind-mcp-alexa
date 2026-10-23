"""Isolated unit tests for the local vectorial memory service (V1)."""

from __future__ import annotations

import pytest

from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
    embed_text,
)


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    source: str = "camera_alert",
    risk: str = "HIGH",
    analysis: str = "la mascota se acerca a la reja abierta",
    labels: tuple[str, ...] = ("PET_ESCAPING", "GATE_OPEN"),
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source=source,
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk=risk,
        model_analysis=analysis,
    )


def test_embed_text_is_deterministic_and_discriminative() -> None:
    text = "el perro se acerca a la reja abierta"
    assert embed_text(text) == embed_text(text)
    assert embed_text("puerta cerrada") != embed_text("fuego en la cocina")


def test_memory_record_exposes_canonical_fields() -> None:
    record = _record("mem-1", 1.0)
    assert record.id == "mem-1"
    assert record.timestamp == 1.0
    assert record.location == "patio"
    assert record.source == "camera_alert"
    assert record.risk == "HIGH"
    assert record.detections[0]["label"] == "PET_ESCAPING"
    assert "mascota" in record.model_analysis


def test_store_memory_persists_and_expands_search_index() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("mem-1", 1.0))
    assert service.size == 1
    results = service.search_memory("la mascota intenta escapar")
    assert len(results) == 1
    assert results[0][0].id == "mem-1"


def test_search_ranks_relevant_records_first() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("gate", 1.0, analysis="la reja se abre de golpe"))
    service.store_memory(
        _record("fire", 2.0, analysis="humo saliendo de la cocina", labels=("SMOKE",))
    )
    results = service.search_memory("humo y fuego en la cocina")
    assert results[0][0].id == "fire"
    results = service.search_memory("la reja quedo abierta")
    assert results[0][0].id == "gate"


def test_search_filters_by_location() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("a", 1.0, location="patio"))
    service.store_memory(_record("b", 2.0, location="cocina"))
    results = service.search_memory("movimiento", location="cocina")
    assert [record.id for record, _ in results] == ["b"]


def test_search_filters_by_risk() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("a", 1.0, risk="HIGH"))
    service.store_memory(_record("b", 2.0, risk="LOW"))
    results = service.search_memory("movimiento", risk="HIGH")
    assert [record.id for record, _ in results] == ["a"]


def test_search_respects_limit_and_min_score() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("a", 3.0))
    service.store_memory(_record("b", 2.0))
    service.store_memory(_record("c", 1.0))
    results = service.search_memory("la reja abierta", limit=2)
    assert len(results) == 2
    empty = service.search_memory("zzz sin coincidencia", min_score=0.9)
    assert empty == []


def test_last_seen_returns_most_recent_record() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("a", 10.0, location="cocina"))
    service.store_memory(_record("b", 30.0, location="patio"))
    service.store_memory(_record("c", 20.0, location="patio"))
    assert service.last_seen(location="patio").id == "b"
    assert service.last_seen(source="camera_alert").id == "b"


def test_last_seen_returns_none_when_absent() -> None:
    service = VectorMemoryService()
    assert service.last_seen() is None
    assert service.last_seen(location="patio") is None


def test_forget_memory_removes_record_and_updates_index() -> None:
    service = VectorMemoryService()
    service.store_memory(_record("mem-1", 1.0))
    assert service.forget_memory("mem-1") is True
    assert service.size == 0
    assert service.last_seen() is None
    assert service.search_memory("movimiento") == []
    assert service.forget_memory("mem-1") is False


def test_store_rejects_when_capacity_is_reached() -> None:
    service = VectorMemoryService(max_records=1)
    service.store_memory(_record("a", 1.0))
    with pytest.raises(MemoryError):
        service.store_memory(_record("b", 2.0))
