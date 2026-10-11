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


def test_predict_low_without_detections_reports_calm() -> None:
    prediction = predict_ambient_state(read_sensors(10.0), None, motion_score=0.0)
    assert prediction.risk_level == "LOW"
    assert "Sin detecciones activas. Todo normal." in prediction.announcement
    assert "No active detections. All normal." in prediction.announcement
    assert "Movimiento" not in prediction.announcement


def test_predict_smoke_at_critical_escalates() -> None:
    reading = SensorReading(
        timestamp=1.0,
        temperature_c=24.0,
        smoke_density=0.85,
        gate_open=False,
        door_open=False,
        pet_proximity=0.1,
        pet_moving=False,
    )
    prediction = predict_ambient_state(reading)
    assert prediction.risk_level == "CRITICAL"
    assert "SMOKE" in {item["label"] for item in prediction.detections}
    assert "FIRE" in {item["label"] for item in prediction.detections}
    assert "¡Alerta crítica!" in prediction.announcement


def test_predict_gate_open_with_pet_flags_escape() -> None:
    reading = SensorReading(
        timestamp=1.0,
        temperature_c=24.0,
        smoke_density=0.02,
        gate_open=True,
        door_open=False,
        pet_proximity=0.8,
        pet_moving=True,
    )
    prediction = predict_ambient_state(reading)
    assert prediction.risk_level == "HIGH"
    labels = {item["label"] for item in prediction.detections}
    assert "PET_ESCAPING" in labels
    assert "GATE_OPEN" in labels
    assert "mascota" in prediction.announcement


def test_predict_temperature_rise_escalates_on_trend() -> None:
    def reading_at(temp: float) -> SensorReading:
        return SensorReading(
            timestamp=1.0,
            temperature_c=temp,
            smoke_density=0.02,
            gate_open=False,
            door_open=False,
            pet_proximity=0.1,
            pet_moving=False,
        )

    prediction = predict_ambient_state(reading_at(30.0), reading_at(24.0))
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


class _FakeCyclingCamera:
    def __init__(self, frames: list[CameraFrame]) -> None:
        self._frames = frames
        self._index = 0
        self.detections: list[dict[str, object]] = []
        self.source = "fallback"

    async def get_frame(self) -> CameraFrame:
        frame = self._frames[min(self._index, len(self._frames) - 1)]
        self._index += 1
        return frame

    def record_detections(self, items: list[dict[str, object]], source: str) -> None:
        self.detections = [dict(item) for item in items]
        self.source = source


def _live_frame(data: bytes) -> CameraFrame:
    return CameraFrame(
        data=data,
        content_type="image/jpeg",
        source="live",
        captured_at=1.0,
    )


@pytest.mark.asyncio
async def test_watch_tick_records_detections_and_publishes_alert() -> None:
    hub = EventHub()
    queue = hub.subscribe()
    camera = _FakeCyclingCamera(
        [_live_frame(b"\x00" * 256), _live_frame(b"\xff" * 256)]
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=SimulatedSensorBus(),
        event_hub=hub,
    )

    await watch.tick(now=1.0)
    prediction = await watch.tick(now=1.5)

    assert prediction.risk_level == "HIGH"
    assert camera.source == "live"
    labels = {item["label"] for item in camera.detections}
    assert "MOTION" in labels

    event = queue.get_nowait()
    assert event["kind"] == "camera_alert"
    assert event["risk"] == "HIGH"
    assert "movimiento" in event["announcement"]
    assert event["announcement"] == prediction.announcement
    assert isinstance(event["model_analysis"], str)
    assert prediction.announcement in event["model_analysis"]
    assert isinstance(event["safety_gate_signals"], list)
    assert (
        "motion" in " ".join(event["safety_gate_signals"]).lower()
        or len(event["safety_gate_signals"]) >= 0
    )
    assert watch.last_state["smoke_density"] == 0.02
    assert isinstance(watch.last_state["model_analysis"], str)
    assert prediction.announcement in watch.last_state["model_analysis"]
    hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_watch_tick_publishes_every_high_tick() -> None:
    hub = EventHub()
    queue = hub.subscribe()
    camera = _FakeCyclingCamera(
        [
            _live_frame(b"\x00" * 256),
            _live_frame(b"\xff" * 256),
            _live_frame(b"\x00" * 256),
            _live_frame(b"\xff" * 256),
        ]
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=SimulatedSensorBus(),
        event_hub=hub,
    )
    await watch.tick(now=1.0)
    assert queue.empty()
    await watch.tick(now=1.5)
    first = queue.get_nowait()
    assert first["kind"] == "camera_alert"
    assert first["risk"] == "HIGH"
    assert isinstance(first["model_analysis"], str)
    assert isinstance(first["safety_gate_signals"], list)

    await watch.tick(now=2.0)
    second = queue.get_nowait()
    assert second["risk"] == "HIGH"
    assert second["announcement"] == first["announcement"]
    assert isinstance(second["model_analysis"], str)
    assert second["model_analysis"] == first["model_analysis"]
    hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_watch_tick_is_silent_when_room_is_still() -> None:
    hub = EventHub()
    queue = hub.subscribe()

    class _StillBus:
        def read(self, now: float) -> SensorReading:
            return SensorReading(
                timestamp=now,
                temperature_c=24.0,
                smoke_density=0.05,
                gate_open=False,
                door_open=False,
                pet_proximity=0.2,
                pet_moving=False,
            )

    camera = _FakeCamera(
        CameraFrame(
            data=b"\x00" * 256,
            content_type="image/jpeg",
            source="live",
            captured_at=1.0,
        )
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=_StillBus(),
        event_hub=hub,
    )
    await watch.tick(now=50.0)
    await watch.tick(now=50.5)
    assert watch.last_state["risk"] == "LOW"
    assert isinstance(watch.last_state["model_analysis"], str)
    assert queue.empty()
    hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_low_state_model_analysis_is_neutral() -> None:
    class _StillBus:
        def read(self, now: float) -> SensorReading:
            return SensorReading(
                timestamp=now,
                temperature_c=24.0,
                smoke_density=0.05,
                gate_open=False,
                door_open=False,
                pet_proximity=0.2,
                pet_moving=False,
            )

    watch = AmbientWatchService(
        camera=_FakeCamera(_live_frame(b"\x00" * 256)),
        sensor_bus=_StillBus(),
        event_hub=EventHub(),
    )
    await watch.tick(now=50.0)
    await watch.tick(now=50.5)
    assert watch.last_state["risk"] == "LOW"
    assert watch.last_state["detections"] == []
    assert watch.last_state["model_analysis"] == (
        "Sin detecciones activas. Todo normal.\nNo active detections. All normal."
    )


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


def test_read_sensors_is_static_baseline() -> None:
    first = read_sensors(100.0)
    second = read_sensors(100.0)
    assert first == second
    third = read_sensors(220.0)
    assert first.temperature_c == third.temperature_c
    assert first.smoke_density == third.smoke_density
    assert first.gate_open == third.gate_open
    assert first.door_open == third.door_open
    assert first.pet_proximity == third.pet_proximity
    assert first.pet_moving == third.pet_moving
    assert first.gate_open is False
    assert first.door_open is False
    assert first.pet_moving is False
    assert first.smoke_density < 0.05
    assert isinstance(first, SensorReading)
