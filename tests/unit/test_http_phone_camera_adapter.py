"""Tests for the Android phone camera adapter (IP Webcam snapshot pipeline)."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import src.main
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.camera.http_phone_camera_adapter import (
    HttpPhoneCameraAdapter,
    mount_phone_camera_routes,
)
from src.infrastructure.adapters.iot.vivotek_adapter import VivotekCameraAdapter
from src.infrastructure.adapters.mcp.tool_resolvers import build_ambient_resolver

_LIVE_BYTES = b"\xff\xd8\xff\xe0android-phone-jpeg-frame"
_LIVE_CONTENT_TYPE = "image/jpeg"
_PHONE_URL = "http://192.168.1.20:8080/shot.jpg"


class _FakeLLM(LLMServicePort):
    def __init__(self, text: str = "phone narrative") -> None:
        self.text = text
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(text=self.text, model_id="fake-model")


def _live_transport() -> tuple[httpx.MockTransport, dict[str, int]]:
    count = {"fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["fetches"] += 1
        assert str(request.url) == _PHONE_URL
        return httpx.Response(
            200,
            headers={"content-type": _LIVE_CONTENT_TYPE},
            content=_LIVE_BYTES,
        )

    return httpx.MockTransport(handler), count


def _dead_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("phone unreachable", request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_frame_returns_live_frame_from_phone() -> None:
    transport, count = _live_transport()
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=transport)
    frame = await camera.get_frame()
    assert frame.source == "live"
    assert frame.data == _LIVE_BYTES
    assert frame.content_type == _LIVE_CONTENT_TYPE
    assert count["fetches"] == 1


@pytest.mark.asyncio
async def test_get_frame_falls_back_to_clean_frame_when_phone_down() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_dead_transport())
    frame = await camera.get_frame()
    assert frame.source == "fallback"
    assert frame.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert frame.content_type == "image/png"
    assert camera.last_error is not None


@pytest.mark.asyncio
async def test_get_frame_serves_cached_frame_within_ttl() -> None:
    transport, count = _live_transport()
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, cache_ttl=60.0, transport=transport)
    await camera.get_frame()
    await camera.get_frame()
    assert count["fetches"] == 1


@pytest.mark.asyncio
async def test_phone_adapter_feeds_ambient_resolver_as_camera_source() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_live_transport()[0])
    fake = _FakeLLM(text="A person is walking near the gate")
    resolver = build_ambient_resolver(fake, camera=camera)
    response = await resolver({"observation": "Phone frame of the entrance"})

    assert response.is_error is False
    assert fake.last_request is not None
    assert len(fake.last_request.attachments) == 1
    payload = fake.last_request.attachments[0]
    assert payload.mime_type == _LIVE_CONTENT_TYPE
    assert payload.kind.value == "image"
    assert payload.data == _LIVE_BYTES
    assert "predicted detections" in response.content[0].data
    assert camera.detections_source == "live"


@pytest.mark.asyncio
async def test_phone_resolver_skips_attachment_on_fallback_frame() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_dead_transport())
    fake = _FakeLLM(text="An unattended pet is crying in the living room")
    resolver = build_ambient_resolver(fake, camera=camera)
    response = await resolver({"observation": "Phone frame of the living room"})

    assert response.is_error is False
    assert fake.last_request is not None
    assert fake.last_request.attachments == ()
    assert any(item["label"] == "PET" for item in camera.last_detections)


@pytest.mark.asyncio
async def test_phone_snapshot_route_serves_live_frame() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_live_transport()[0])
    app = FastAPI()
    mount_phone_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/phone/snapshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == _LIVE_CONTENT_TYPE
    assert response.headers["x-source"] == "live"
    assert response.content == _LIVE_BYTES


@pytest.mark.asyncio
async def test_phone_snapshot_route_serves_base64_fallback() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_dead_transport())
    app = FastAPI()
    mount_phone_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/phone/snapshot?format=base64")
    payload = response.json()
    assert payload["live"] is False
    assert payload["source"] == "fallback"
    assert payload["contentType"] == "image/png"
    assert base64.b64decode(payload["dataBase64"]).startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_phone_detections_route_exposes_recorded_detections() -> None:
    camera = HttpPhoneCameraAdapter(url=_PHONE_URL, transport=_live_transport()[0])
    camera.record_detections([{"label": "PERSON", "confidence": 0.91}], source="live")
    app = FastAPI()
    mount_phone_camera_routes(app, camera)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/phone/detections")
    payload = response.json()
    assert payload["live"] is True
    assert payload["detections"][0]["label"] == "PERSON"


@pytest.mark.asyncio
async def test_phone_detections_route_returns_503_without_camera() -> None:
    app = FastAPI()
    mount_phone_camera_routes(app, None)
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/cam/phone/detections")
    assert response.status_code == 503


def test_build_camera_defaults_to_vivotek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAMERA", raising=False)
    monkeypatch.delenv("PHONE_CAM_URL", raising=False)
    camera = src.main._build_camera()
    assert isinstance(camera, VivotekCameraAdapter)


def test_build_camera_phone_mode_uses_env_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAMERA", "phone")
    monkeypatch.setenv("PHONE_CAM_URL", _PHONE_URL)
    monkeypatch.setenv("PHONE_TIMEOUT", "3.0")
    monkeypatch.setenv("PHONE_CACHE_TTL", "2.0")
    camera = src.main._build_camera()
    assert isinstance(camera, HttpPhoneCameraAdapter)
    assert camera.url == _PHONE_URL


def test_build_camera_autodetects_phone_from_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAMERA", raising=False)
    monkeypatch.setenv("PHONE_CAM_URL", _PHONE_URL)
    camera = src.main._build_camera()
    assert isinstance(camera, HttpPhoneCameraAdapter)
    assert camera.url == _PHONE_URL


def test_build_camera_simulation_never_uses_phone_or_hardware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAMERA", "simulation")
    monkeypatch.delenv("PHONE_CAM_URL", raising=False)
    camera = src.main._build_camera()
    assert isinstance(camera, VivotekCameraAdapter)
    assert "127.0.0.1" in camera.url
