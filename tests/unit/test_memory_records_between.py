"""Unit tests for the additive windowed read on the local memory service."""

from __future__ import annotations

from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    risk: str = "LOW",
    labels: tuple[str, ...] = ("PET",),
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.8} for label in labels),
        risk=risk,
        model_analysis="",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    for record in (
        _record("mem-a", 100.0, location="patio", risk="LOW"),
        _record("mem-b", 200.0, location="kitchen", risk="HIGH"),
        _record("mem-c", 300.0, location="patio", risk="CRITICAL"),
        _record("mem-d", 400.0, location="patio", risk="LOW"),
    ):
        service.store_memory(record)
    return service


def test_records_between_filters_window() -> None:
    found = _service().records_between(150.0, 350.0)
    assert [record.id for record in found] == ["mem-b", "mem-c"]


def test_records_between_window_bounds_are_inclusive() -> None:
    found = _service().records_between(200.0, 200.0)
    assert [record.id for record in found] == ["mem-b"]


def test_records_between_unbounded_when_none() -> None:
    found = _service().records_between(None, None)
    assert [record.id for record in found] == ["mem-a", "mem-b", "mem-c", "mem-d"]


def test_records_between_only_since() -> None:
    found = _service().records_between(300.0, None)
    assert [record.id for record in found] == ["mem-c", "mem-d"]


def test_records_between_only_until() -> None:
    found = _service().records_between(None, 200.0)
    assert [record.id for record in found] == ["mem-a", "mem-b"]


def test_records_between_orders_ascending() -> None:
    found = _service().records_between(None, None)
    assert [record.timestamp for record in found] == [100.0, 200.0, 300.0, 400.0]


def test_records_between_filters_location() -> None:
    found = _service().records_between(None, None, location="kitchen")
    assert [record.id for record in found] == ["mem-b"]


def test_records_between_filters_risk_case_insensitive() -> None:
    service = _service()
    assert [r.id for r in service.records_between(None, None, risk="high")] == ["mem-b"]
    assert [r.id for r in service.records_between(None, None, risk="HIGH")] == ["mem-b"]


def test_records_between_returns_empty_outside_window() -> None:
    assert _service().records_between(1000.0, 2000.0) == []


def test_records_between_is_deterministic_on_equal_timestamps() -> None:
    service = VectorMemoryService()
    for record_id in ("mem-z", "mem-a", "mem-m"):
        service.store_memory(_record(record_id, 100.0))
    assert [r.id for r in service.records_between(None, None)] == [
        "mem-a",
        "mem-m",
        "mem-z",
    ]


def test_records_between_empty_store() -> None:
    assert VectorMemoryService().records_between(None, None) == []


def test_records_between_does_not_mutate_the_store() -> None:
    service = _service()
    before = service.size
    found = service.records_between(None, None, location="patio")
    assert len(found) == 3
    assert service.size == before
    assert service.last_seen(label="PET") is not None
    assert service.count_events(None) == 4
