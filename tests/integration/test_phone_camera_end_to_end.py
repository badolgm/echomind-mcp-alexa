"""End-to-end: Android phone frames -> watchdog -> memory -> conversation.

Drives the exact production wiring (HttpPhoneCameraAdapter -> AmbientWatchService
-> EventHub -> MemoryBridge -> memory_converse) with a mocked phone HTTP
transport, so the full chain is verified without a physical IP Webcam. The only
difference in the live demo is replacing the MockTransport with the real phone
URL in ``PHONE_CAM_URL``.
"""

from __future__ import annotations

import httpx
import pytest

from src.infrastructure.adapters.camera.http_phone_camera_adapter import (
    HttpPhoneCameraAdapter,
)
from src.infrastructure.adapters.mcp.memory_resolvers import (
    build_memory_converse_resolver,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.ambient_watch_service import AmbientWatchService
from src.infrastructure.services.memory_bridge import MemoryBridge
from src.infrastructure.services.memory_service import VectorMemoryService
from src.infrastructure.services.sensor_bus import SensorReading

_PHONE_URL = "http://192.168.1.20:8080/shot.jpg"


class _CalmSensorBus:
    """Deterministic quiet home: only the camera can raise the risk."""

    def read(self, now: float) -> SensorReading:
        return SensorReading(
            timestamp=now,
            temperature_c=22.0,
            smoke_density=0.02,
            gate_open=False,
            door_open=False,
            pet_proximity=0.1,
            pet_moving=False,
        )


def _moving_phone_transport() -> httpx.MockTransport:
    """Serve two visually different frames so real motion is detected."""
    frames = [b"\x00" * 4096, b"\xff" * 4096]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(frames) - 1)
        calls["n"] += 1
        return httpx.Response(
            200, headers={"content-type": "image/jpeg"}, content=frames[index]
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_phone_motion_flows_to_memory_and_conversation() -> None:
    camera = HttpPhoneCameraAdapter(
        url=_PHONE_URL, cache_ttl=0.0, transport=_moving_phone_transport()
    )
    hub = EventHub()
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=hub, memory=memory)
    bridge.attach()
    watch = AmbientWatchService(
        camera=camera, sensor_bus=_CalmSensorBus(), event_hub=hub, interval=0.05
    )

    await watch.tick()  # baseline frame: no motion yet
    prediction = await watch.tick()  # different frame -> motion -> HIGH alert

    assert prediction.risk_level == "HIGH"
    assert any(item["label"] == "MOTION" for item in prediction.detections)
    assert watch.last_state["source"] == "live"

    record = await bridge.consume_next()
    assert record is not None
    assert record.source == "live"
    assert memory.size == 1
    assert memory.last_seen(label="MOTION") is not None

    converse = build_memory_converse_resolver(
        memory, current_state=lambda: watch.last_state
    )

    now_answer = await converse({"query": "¿Qué ocurre ahora?"})
    assert now_answer.is_error is False
    assert "Actualmente detecto movimiento" in now_answer.content[0].data
    assert "durante las últimas 24 horas" in now_answer.content[0].data

    history_answer = await converse({"query": "¿Qué recuerdas de hoy?"})
    assert history_answer.is_error is False
    assert "movimiento" in history_answer.content[0].data
