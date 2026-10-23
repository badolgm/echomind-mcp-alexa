"""Isolated tests for the memory query API (last_seen/counts by label)."""

from __future__ import annotations

from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService


def _record(
    record_id: str,
    timestamp: float,
    labels: tuple[str, ...],
    *,
    location: str = "patio",
    risk: str = "HIGH",
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label} for label in labels),
        risk=risk,
        model_analysis="analisis de respaldo",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    service.store_memory(_record("pet-1", 10.0, ("PET",), location="patio"))
    service.store_memory(_record("gate-1", 20.0, ("GATE_OPEN",), location="patio"))
    service.store_memory(
        _record("pet-2", 30.0, ("PET", "GATE_OPEN"), location="cocina")
    )
    return service


def test_last_seen_filters_by_canonical_label() -> None:
    service = _service()
    assert service.last_seen(label="PET").id == "pet-2"
    assert service.last_seen(label="GATE_OPEN").id == "pet-2"


def test_last_seen_label_without_match_returns_none() -> None:
    service = _service()
    assert service.last_seen(label="PERSON_ELDERLY") is None


def test_last_seen_keeps_existing_contract() -> None:
    service = _service()
    assert service.last_seen(location="cocina").id == "pet-2"
    assert service.last_seen(source="camera_alert").id == "pet-2"


def test_count_occurrences_counts_and_filters() -> None:
    service = _service()
    assert service.count_occurrences("PET") == 2
    assert service.count_occurrences("GATE_OPEN") == 2
    assert service.count_occurrences("PET", location="patio") == 1
    assert service.count_occurrences("PET", since=25.0) == 1
    assert service.count_occurrences("FIRE") == 0


def test_label_counts_aggregates_per_label() -> None:
    service = _service()
    assert service.label_counts() == {"PET": 2, "GATE_OPEN": 2}
    assert service.label_counts(location="cocina") == {"PET": 1, "GATE_OPEN": 1}
    assert service.label_counts(since=25.0) == {"PET": 1, "GATE_OPEN": 1}


def test_counts_are_zero_when_empty() -> None:
    service = VectorMemoryService()
    assert service.label_counts() == {}
    assert service.count_occurrences("PET") == 0
    assert service.last_seen(label="PET") is None
