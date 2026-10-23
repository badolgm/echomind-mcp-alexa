"""Isolated tests for the memory history API (top/high/critical/events)."""

from __future__ import annotations

from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService


def _rec(
    record_id: str,
    timestamp: float,
    risk: str,
    labels: tuple[str, ...] = ("PET",),
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location="cam-01",
        source="camera_alert",
        detections=tuple({"label": label} for label in labels),
        risk=risk,
        model_analysis="analisis de respaldo",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    service.store_memory(_rec("critical-old", 200.0, "CRITICAL"))
    service.store_memory(_rec("critical-new", 400.0, "CRITICAL"))
    service.store_memory(_rec("high-1", 300.0, "HIGH"))
    service.store_memory(_rec("high-2", 100.0, "HIGH"))
    service.store_memory(_rec("medium", 250.0, "MEDIUM"))
    return service


def test_top_events_sorts_by_severity_then_recency() -> None:
    service = _service()
    events = service.top_events()
    assert [record.id for record in events] == [
        "critical-new",
        "critical-old",
        "high-1",
        "high-2",
    ]
    assert all(record.risk in ("HIGH", "CRITICAL") for record in events)


def test_top_events_respects_since_and_limit() -> None:
    service = _service()
    events = service.top_events(since=150.0, limit=2)
    assert [record.id for record in events] == ["critical-new", "critical-old"]


def test_recent_high_risk_events_returns_only_high_newest_first() -> None:
    service = _service()
    events = service.recent_high_risk_events()
    assert [record.id for record in events] == ["high-1", "high-2"]
    assert all(record.risk == "HIGH" for record in events)


def test_recent_critical_events_returns_only_critical_newest_first() -> None:
    service = _service()
    events = service.recent_critical_events()
    assert [record.id for record in events] == ["critical-new", "critical-old"]
    assert all(record.risk == "CRITICAL" for record in events)


def test_count_events_counts_and_filters_by_risk() -> None:
    service = _service()
    assert service.count_events() == 5
    assert service.count_events("HIGH") == 2
    assert service.count_events("CRITICAL") == 2
    assert service.count_events("HIGH", since=150.0) == 1
    assert service.count_events("HIGH", location="cam-01") == 2


def test_history_apis_are_empty_without_records() -> None:
    service = VectorMemoryService()
    assert service.top_events() == []
    assert service.recent_high_risk_events() == []
    assert service.recent_critical_events() == []
    assert service.count_events() == 0
