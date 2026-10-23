"""Isolated tests for the memory bridge (camera_alert -> MemoryRecord)."""

from __future__ import annotations

import asyncio

import pytest

from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.memory_bridge import (
    MemoryBridge,
    camera_alert_to_memory_record,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)


def _alert(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "kind": "camera_alert",
        "tool": "ambient_watchdog",
        "status": "HIGH",
        "risk": "HIGH",
        "location": "camera",
        "source": "live",
        "detections": [
            {"label": "GATE_OPEN", "confidence": 0.91},
            {"label": "PET_ESCAPING", "confidence": 0.85},
        ],
        "motion_score": 0.5,
        "announcement": "Atención: la reja está abierta.",
        "model_analysis": "Atención: la reja está abierta.\nActúa ya.",
        "ts": 1700000000.0,
    }
    event.update(overrides)
    return event


def test_high_camera_alert_maps_to_memory_record() -> None:
    record = camera_alert_to_memory_record(_alert())
    assert record is not None
    assert record.timestamp == 1700000000.0
    assert record.location == "camera"
    assert record.source == "live"
    assert record.risk == "HIGH"
    assert len(record.detections) == 2
    assert record.detections[0]["label"] == "GATE_OPEN"
    assert "la reja" in record.model_analysis


def test_only_high_and_critical_alerts_are_memorable() -> None:
    assert camera_alert_to_memory_record(_alert(risk="LOW")) is None
    assert camera_alert_to_memory_record(_alert(risk="MEDIUM")) is None

    status_driven = _alert()
    del status_driven["risk"]
    status_driven["status"] = "CRITICAL"
    critical = camera_alert_to_memory_record(status_driven)
    assert critical is not None
    assert critical.risk == "CRITICAL"


def test_non_camera_alert_events_are_ignored() -> None:
    tool_event = _alert(kind="tool_call", tool="schedule_reminder", status="OK")
    assert camera_alert_to_memory_record(tool_event) is None


def test_model_analysis_falls_back_to_announcement() -> None:
    event = _alert()
    del event["model_analysis"]
    record = camera_alert_to_memory_record(event)
    assert record is not None
    assert record.model_analysis == "Atención: la reja está abierta."


def test_bridge_ingest_persists_into_memory() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory)
    record = bridge.ingest(_alert())
    assert record is not None
    assert memory.size == 1
    assert memory.last_seen(label="GATE_OPEN") is not None


def test_bridge_skips_non_memorable_events() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory)
    assert bridge.ingest(_alert(risk="LOW")) is None
    assert bridge.ingest(_alert(kind="tool_call")) is None
    assert memory.size == 0


@pytest.mark.asyncio
async def test_bridge_consumes_events_without_swallowing_dashboard_stream() -> None:
    hub = EventHub()
    dashboard_queue = hub.subscribe()
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=hub, memory=memory)
    bridge.attach()
    alert = _alert()
    hub.publish(alert)
    record = await bridge.consume_next()
    assert record is not None
    assert memory.size == 1
    delivered = dashboard_queue.get_nowait()
    assert delivered == alert


@pytest.mark.asyncio
async def test_bridge_run_loop_ingests_until_stopped() -> None:
    hub = EventHub()
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=hub, memory=memory)
    task = asyncio.create_task(bridge.run())
    bridge.attach()
    hub.publish(_alert(ts=1700000001.0))
    await asyncio.sleep(0.2)
    bridge.stop()
    await task
    assert memory.size == 1


def test_bridge_survives_a_full_memory_store() -> None:
    memory = VectorMemoryService(max_records=1)
    memory.store_memory(
        MemoryRecord(
            id="mem-full",
            timestamp=1600000000.0,
            location="camera",
            source="live",
            detections=(),
            risk="HIGH",
            model_analysis="pre-existing",
        )
    )
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory)
    assert bridge.ingest(_alert(ts=1700000000.0)) is None
    assert memory.size == 1


def _motion_alert(ts: float) -> dict[str, object]:
    return _alert(
        ts=ts,
        location="camera",
        detections=[{"label": "MOTION", "confidence": 0.85}],
        model_analysis="Atención: movimiento detectado.\nActúa ya.",
    )


def test_consecutive_motion_ticks_coalesce_into_one_episode() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory, episode_gap=30.0)
    for i in range(60):
        bridge.ingest(_motion_alert(1700000000.0 + i * 0.5))
    assert memory.size == 1
    assert memory.count_occurrences("MOTION") == 1
    record = memory.last_seen(label="MOTION")
    assert record is not None
    assert record.timestamp == 1700000000.0 + 59 * 0.5


def test_motion_after_gap_starts_a_new_episode() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory, episode_gap=30.0)
    bridge.ingest(_motion_alert(1700000000.0))
    bridge.ingest(_motion_alert(1700000000.5))
    bridge.ingest(_motion_alert(1700000100.0))
    assert memory.size == 2
    assert memory.count_occurrences("MOTION") == 2


def test_distinct_detection_sets_are_distinct_episodes() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory)
    bridge.ingest(_motion_alert(1700000000.0))
    bridge.ingest(_alert(ts=1700000000.5))
    assert memory.size == 2
