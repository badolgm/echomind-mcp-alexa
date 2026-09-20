"""Tests for the autonomous ambient watchdog and prediction engine."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.infrastructure.adapters.iot.vivotek_adapter import (
    CameraFrame,
    mount_camera_routes,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.ambient_watch_service import (
    AmbientWatchService,
    frame_delta_ratio,
    predict_ambient_state,
)
from src.infrastructure.services.sensor_bus import (
    SensorReading,
    SimulatedSensorBus,
    read_sensors,
)


def test_frame_delta_ratio_identifies_changing_scene() -> None:
    identical = b"\x00\x01\x02\x03\x04\x05"
    assert frame_delta_ratio(identical, identical) == 0.0
    changed = b"\xff\xfe\x00\x03\x00\x01"
    assert frame_delta_ratio(identical, changed) >= 0.4
    assert frame_delta_ratio(b"", b"abc") == 0.0


def test_predict_baseline_is_low_without_detections() -> None:
    prediction = predict_ambient_state(read_sensors(10.0))
    assert prediction.risk_level == "LOW"
    assert prediction.detections == ()


def test_predict_smoke_at_critical_escalates() -> None:
    prediction = predict_ambient_state(read_sensors(88.0))
    assert prediction.risk_level == "CRITICAL"
    assert "SMOKE" in {item["label"] for item in prediction.detections}
    assert "FIRE" in {item["label"] for item in prediction.detections}
    assert "¡Alerta crítica!" in prediction.announcement


def test_predict_gate_open_with_pet_flags_escape() -> None:
    prediction = predict_ambient_state(read_sensors(50.0))
    assert prediction.risk_level == "HIGH"
    labels = {item["label"] for item in prediction.detections}
    assert "PET_ESCAPING" in labels
    assert "GATE_OPEN" in labels
    assert "mascota" in prediction.announcement


def test_predict_temperature_rise_escalates_on_trend() -> None:
    prev = read_sensors(99.0)
    current = read_sensors(100.0)
    prediction = predict_ambient_state(current, prev)
    assert prediction.risk_level == "HIGH"
    assert "TEMP_RISING" in {item["label"] for item in prediction.detections}
    assert "temperatura" in prediction.announcement


class _FakeCamera:
    def __init__(self, frame: CameraFrame) -> None:
        self._frame = frame
        self.detections: list[dict[str, object]] = []
        self.source = "fallback"

    async def get_frame(self) -> CameraFrame:
        return self._frame

    def record_detections(self, items: list[dict[str, object]], source: str) -> None:
        self.detections = [dict(item) for item in items]
        self.source = source


@pytest.mark.asyncio
async def test_watch_tick_records_detections_and_publishes_alert() -> None:
    hub = EventHub()
    queue = hub.subscribe()
    camera = _FakeCamera(
        CameraFrame(
            data=b"\xff\xd8\xff\xe0frame-a",
            content_type="image/jpeg",
            source="live",
            captured_at=1.0,
        )
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=SimulatedSensorBus(),
        event_hub=hub,
    )

    prediction = await watch.tick(now=50.0)

    assert prediction.risk_level == "HIGH"
    assert camera.source == "live"
    labels = {item["label"] for item in camera.detections}
    assert {"PET_ESCAPING", "GATE_OPEN"} <= labels

    event = queue.get_nowait()
    assert event["kind"] == "camera_alert"
    assert event["risk"] == "HIGH"
    assert event["announcement"] == prediction.announcement
    assert watch.last_state["smoke_density"] >= 0.0
    hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_watch_tick_does_not_repeat_identical_alert() -> None:
    hub = EventHub()
    queue = hub.subscribe()
    camera = _FakeCamera(
        CameraFrame(
            data=b"frame",
            content_type="image/jpeg",
            source="live",
            captured_at=1.0,
        )
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=SimulatedSensorBus(),
        event_hub=hub,
    )
    await watch.tick(now=50.0)
    assert queue.get_nowait()["kind"] == "camera_alert"
    await watch.tick(now=50.5)
    assert queue.empty()
    hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_state_route_exposes_latest_vision() -> None:
    class _FakeWatch:
        last_state = {"risk": "MEDIUM", "temperature_c": 27.5}

    app = FastAPI()
    mount_camera_routes(app, None, watch=_FakeWatch())
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/vivotek/state")
    assert response.status_code == 200
    assert response.json()["risk"] == "MEDIUM"
    assert response.json()["temperature_c"] == 27.5


def test_read_sensors_is_deterministic_per_phase() -> None:
    first = read_sensors(100.0)
    second = read_sensors(100.0)
    assert first == second
    third = read_sensors(100.0 + 120.0)
    assert third.timestamp != first.timestamp
    assert isinstance(first, SensorReading)
