"""Android phone camera adapter: IP Webcam snapshots with graceful fallback.

Consumes the JPEG snapshot endpoint served by the free *IP Webcam* Android app
(``http://<phone-ip>:8080/shot.jpg``) over ``httpx`` asynchronously, caching the
most recent frame so the Control Center can poll it without hammering the phone.

The adapter implements the same duck-typed :class:`CameraFrameSource` contract as
the :class:`VivotekCameraAdapter`, so the watchdog, the MCP tool resolvers, the
``/api/cam/phone`` routes and the Control Center cannot tell whether the frame
came from a Vivotek FD8367 or an Android phone. If the phone is unreachable,
times out or returns an invalid response, it serves the identical deterministic
clean test frame so the system stays operational 24/7.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import FastAPI

from src.infrastructure.adapters.iot.vivotek_adapter import (
    CameraFrame,
    CameraFrameSource,
    _detections,
    _generate_fallback_frame,
    _snapshot,
    _vision_state,
)

DEFAULT_PHONE_URL = "http://192.168.1.20:8080/shot.jpg"
DEFAULT_PHONE_TIMEOUT = 2.5
DEFAULT_PHONE_CACHE_TTL = 1.5


class HttpPhoneCameraAdapter:
    """Async client for an Android phone exposing IP Webcam snapshots."""

    def __init__(
        self,
        *,
        url: str = DEFAULT_PHONE_URL,
        timeout: float = DEFAULT_PHONE_TIMEOUT,
        cache_ttl: float = DEFAULT_PHONE_CACHE_TTL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._cache_ttl = cache_ttl
        self._client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, transport=transport
        )
        self._cached: tuple[float, CameraFrame] | None = None
        self._last_error: str | None = None
        self._detections: list[dict[str, Any]] = []
        self._detections_source = "fallback"
        self._fallback_buffer = _generate_fallback_frame()

    @property
    def url(self) -> str:
        return self._url

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def last_detections(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._detections]

    @property
    def detections_source(self) -> str:
        return self._detections_source

    async def get_frame(self) -> CameraFrame:
        """Return the freshest phone frame, falling back to a clean test frame."""
        now = time.time()
        if self._cached is not None and now - self._cached[0] < self._cache_ttl:
            return self._cached[1]
        frame = await self._fetch_live(now)
        self._cached = (now, frame)
        return frame

    async def _fetch_live(self, now: float) -> CameraFrame:
        try:
            response = await self._client.get(self._url)
            if response.status_code == 200 and response.content:
                content_type = response.headers.get("content-type") or "image/jpeg"
                self._last_error = None
                return CameraFrame(
                    data=response.content,
                    content_type=(
                        content_type
                        if content_type.startswith("image/")
                        else "image/jpeg"
                    ),
                    source="live",
                    captured_at=now,
                )
        except Exception as exc:  # noqa: BLE001 - phone failures must never crash
            self._last_error = repr(exc)
        return self._fallback(now)

    def _fallback(self, now: float) -> CameraFrame:
        self._last_error = "phone camera unavailable; serving clean test frame"
        return CameraFrame(
            data=self._fallback_buffer,
            content_type="image/png",
            source="fallback",
            captured_at=now,
        )

    def record_detections(self, items: list[dict[str, Any]], source: str) -> None:
        self._detections = [dict(item) for item in items]
        self._detections_source = source

    async def aclose(self) -> None:
        await self._client.aclose()


def mount_phone_camera_routes(
    app: FastAPI,
    camera: CameraFrameSource | None = None,
    watch: object | None = None,
) -> None:
    """Register the Android phone snapshot and detection endpoints on ``app``."""
    app.add_api_route("/api/cam/phone/snapshot", _snapshot(camera), methods=["GET"])
    app.add_api_route("/api/cam/phone/detections", _detections(camera), methods=["GET"])
    if watch is not None:
        app.add_api_route("/api/cam/phone/state", _vision_state(watch), methods=["GET"])
