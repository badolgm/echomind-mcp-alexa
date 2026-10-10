"""Tests for the Vivotek camera adapter (live/failover snapshot pipeline)."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.mcp.tool_resolvers import (
    build_ambient_resolver,
    combine_vision_with_baseline,
    extract_detections,
)
from src.infrastructure.adapters.iot.vivotek_adapter import (
    VivotekCameraAdapter,
    mount_camera_routes,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.sensor_bus import SensorReading

_LIVE_BYTES = b"\xff\xd8\xff\xe0live-jpeg-frame"
_LIVE_CONTENT_TYPE = "image/jpeg"


class _FakeLLM(LLMServicePort):
    def __init__(self, text: str = "model narrative") -> None:
        self.text = text
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(text=self.text, model_id="fake-model")


def _live_transport() -> httpx.MockTransport:
    count = {"fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["fetches"] += 1
        return httpx.Response(
            200,
            headers={"content-type": _LIVE_CONTENT_TYPE},
            content=_LIVE_BYTES,
        )

    return httpx.MockTransport(handler), count


def _dead_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("camera unreachable", request=request)

    return httpx.MockTransport(handler)


def test_extract_detections_labels_fall_and_person() -> None:
    detections = extract_detections("A person fell in the kitchen and is not moving")
    labels = {item["label"] for item in detections}
    assert "FALL DETECTED" in labels
    assert "PERSON" in labels


def test_extract_detections_maps_canonical_awsvision_taxonomy() -> None:
    elderly = extract_detections("the elderly grandpa needs help in the living room")
    assert "PERSON_ELDERLY" in {item["label"] for item in elderly}
    assert "PERSON" not in {item["label"] for item in elderly}
    assert "GATE_OPEN" in {
        item["label"] for item in extract_detections("the gate is open")
    }
    assert "DOOR_OPEN" in {
        item["label"] for item in extract_detections("la puerta está abierta")
    }


def test_combine_vision_never_crosses_gate_and_door() -> None:
    def reading(*, gate: bool, door: bool) -> SensorReading:
        return SensorReading(
            timestamp=1.0,
            temperature_c=22.4,
            smoke_density=0.02,
            gate_open=gate,
            door_open=door,
            pet_proximity=0.8 if gate else 0.1,
            pet_moving=True,
        )

    escape = combine_vision_with_baseline(
        extract_detections("the gate is open and the pet is near the exit"),
        reading(gate=True, door=False),
    )
    escape_labels = {item["label"] for item in escape}
    assert "GATE_OPEN" in escape_labels
    assert "DOOR_OPEN" not in escape_labels
    assert "PET_ESCAPING" in escape_labels

    crossed = combine_vision_with_baseline(
        extract_detections("the door is open and the gate is open"),
        reading(gate=False, door=True),
    )
    crossed_labels = {item["label"] for item in crossed}
    assert "DOOR_OPEN" in crossed_labels
    assert "GATE_OPEN" not in crossed_labels


@pytest.mark.asyncio
async def test_get_frame_returns_live_frame_from_camera() -> None:
    transport, count = _live_transport()
    camera = VivotekCameraAdapter(transport=transport)
    frame = await camera.get_frame()
    assert frame.source == "live"
    assert frame.data == _LIVE_BYTES
    assert frame.content_type == _LIVE_CONTENT_TYPE
    assert count["fetches"] == 1


@pytest.mark.asyncio
async def test_get_frame_falls_back_to_clean_frame_when_camera_down() -> None:
    camera = VivotekCameraAdapter(transport=_dead_transport())
    frame = await camera.get_frame()
    assert frame.source == "fallback"
    assert frame.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert frame.content_type == "image/png"
    assert camera.last_error is not None


@pytest.mark.asyncio
async def test_get_frame_serves_cached_frame_within_ttl() -> None:
    transport, count = _live_transport()
    camera = VivotekCameraAdapter(transport=transport, cache_ttl=60.0)
    await camera.get_frame()
    await camera.get_frame()
    assert count["fetches"] == 1


def test_extract_detections_empty_when_normal() -> None:
    assert extract_detections("Everything looks completely normal today") == ()


def test_extract_detections_ignores_embedded_keyword_tokens() -> None:
    detections = extract_detections(
        "package dropped by a delivery box in the living room location"
    )
    labels = {item["label"] for item in detections}
    assert "PACKAGE" in labels
    assert "PET" not in labels


@pytest.mark.asyncio
async def test_ambient_resolver_auto_attaches_live_camera_frame() -> None:
    camera = VivotekCameraAdapter(transport=_live_transport()[0])
    fake = _FakeLLM(text="An elderly person is lying on the floor and smoke")
    resolver = build_ambient_resolver(fake, camera=camera)
    response = await resolver({"observation": "Camera frame of the hallway"})

    assert response.is_error is False
    assert fake.last_request is not None
    assert len(fake.last_request.attachments) == 1
    payload = fake.last_request.attachments[0]
    assert payload.mime_type == _LIVE_CONTENT_TYPE
    assert payload.kind.value == "image"
    assert payload.data == _LIVE_BYTES
    assert "predicted detections" in response.content[0].data
    assert camera.detections_source == "live"
    assert any(item["label"] == "PERSON" for item in camera.last_detections)


@pytest.mark.asyncio
async def test_ambient_resolver_skips_attachment_on_fallback_frame() -> None:
    camera = VivotekCameraAdapter(transport=_dead_transport())
    fake = _FakeLLM(text="An unattended pet is crying in the living room")
    resolver = build_ambient_resolver(fake, camera=camera)
    response = await resolver({"observation": "Camera frame of the living room"})

    assert response.is_error is False
    assert fake.last_request is not None
    assert fake.last_request.attachments == ()
    assert any(item["label"] == "PET" for item in camera.last_detections)


@pytest.mark.asyncio
async def test_snapshot_route_serves_live_frame() -> None:
    camera = VivotekCameraAdapter(transport=_live_transport()[0])
    app = FastAPI()
    mount_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/vivotek/snapshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == _LIVE_CONTENT_TYPE
    assert response.headers["x-source"] == "live"
    assert response.content == _LIVE_BYTES


@pytest.mark.asyncio
async def test_snapshot_route_serves_base64_fallback_when_camera_down() -> None:
    camera = VivotekCameraAdapter(transport=_dead_transport())
    app = FastAPI()
    mount_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/vivotek/snapshot?format=base64")
    payload = response.json()
    assert payload["live"] is False
    assert payload["source"] == "fallback"
    assert payload["contentType"] == "image/png"
    assert base64.b64decode(payload["dataBase64"]).startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_detections_route_exposes_recorded_detections() -> None:
    camera = VivotekCameraAdapter(transport=_live_transport()[0])
    camera.record_detections(
        [{"label": "FALL DETECTED", "confidence": 0.93}], source="live"
    )
    app = FastAPI()
    mount_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/vivotek/detections")
    payload = response.json()
    assert payload["live"] is True
    assert payload["detections"][0]["label"] == "FALL DETECTED"


@pytest.mark.asyncio
async def test_detections_route_returns_503_without_camera() -> None:
    app = FastAPI()
    mount_camera_routes(app, None)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/vivotek/detections")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_ambient_resolver_publishes_model_analysis_to_event_hub() -> None:
    narrative = (
        "The elderly person is on the floor in the living room, gate is open, "
        "and the pet is moving toward the exit."
    )
    hub = EventHub()
    queue = hub.subscribe()
    resolver = build_ambient_resolver(_FakeLLM(text=narrative), event_hub=hub)
    response = await resolver(
        {"observation": "alarm in the patio", "location": "patio"}
    )
    assert response.is_error is False
    assert not queue.empty()
    event = queue.get_nowait()
    assert event["kind"] == "camera_alert"
    assert event["tool"] == "analyze_ambient_stream"
    assert isinstance(event["model_analysis"], str)
    assert event["model_analysis"] == narrative
    assert isinstance(event["safety_gate_signals"], list)
    assert isinstance(event["safety_gate_recommendation"], str)
    hub.unsubscribe(queue)
