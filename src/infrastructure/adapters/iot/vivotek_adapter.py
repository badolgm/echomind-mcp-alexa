"""Vivotek FD8367 camera adapter: live snapshots with graceful fallback.

Fetches the MJPEG snapshot endpoint over HTTP with ``httpx`` asynchronously,
caching the most recent frame so the Control Center can poll it without
hammering the camera. If the camera is unreachable, times out or returns an
invalid response, the adapter serves a deterministic clean test frame (a
generated PNG) so dashboards, tool resolvers and the Alexa+ MCP interface stay
operational 24/7.
"""

from __future__ import annotations

import base64
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

DEFAULT_HOST = "192.168.40.10"
DEFAULT_SNAPSHOT_PATH = "/cgi-bin/viewer/video.jpg"
DEFAULT_PORT = 80
_FALLBACK_WIDTH = 480
_FALLBACK_HEIGHT = 270


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def _generate_fallback_frame(
    width: int = _FALLBACK_WIDTH, height: int = _FALLBACK_HEIGHT
) -> bytes:
    """Build a deterministic clean test frame (dark slate + cyan frame grid)."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            on_border = (12 <= x < width - 12 and 12 <= y < height - 12) and (
                x in (12, width - 13) or y in (12, height - 13)
            )
            on_grid = x % 48 == 0 or y % 48 == 0
            if on_border:
                r, g, b = 34, 211, 238
            elif on_grid:
                r, g, b = 20, 28, 46
            else:
                r, g, b = 11, 15, 25
            rows += bytes((r, g, b))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(rows), 6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


@dataclass(frozen=True, slots=True)
class CameraFrame:
    """One immutable frame produced by the camera adapter."""

    data: bytes
    content_type: str
    source: str
    captured_at: float


class CameraFrameSource(Protocol):
    """Duck-typed contract consumed by the ambient resolver and routes."""

    async def get_frame(self) -> CameraFrame: ...

    def record_detections(self, items: list[dict[str, Any]], source: str) -> None: ...


class VivotekCameraAdapter:
    """Async client for the Vivotek FD8367 live snapshot endpoint."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        scheme: str = "http",
        snapshot_path: str = DEFAULT_SNAPSHOT_PATH,
        timeout: float = 2.5,
        cache_ttl: float = 1.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{scheme}://{host}:{port}{snapshot_path}"
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
        """Return the freshest frame, falling back to a clean test frame."""
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
        except Exception as exc:  # noqa: BLE001 - camera failures must never crash
            self._last_error = repr(exc)
        return self._fallback(now)

    def _fallback(self, now: float) -> CameraFrame:
        self._last_error = "camera unavailable; serving clean test frame"
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


def mount_camera_routes(app: FastAPI, camera: CameraFrameSource | None = None) -> None:
    """Register the Vivotek snapshot and detection endpoints on ``app``."""
    app.add_api_route("/api/cam/vivotek/snapshot", _snapshot(camera), methods=["GET"])
    app.add_api_route(
        "/api/cam/vivotek/detections", _detections(camera), methods=["GET"]
    )


def _snapshot(camera: CameraFrameSource | None):
    async def handler(format: str | None = None) -> Response:
        if camera is None:
            return JSONResponse(
                status_code=503, content={"error": "camera unconfigured"}
            )
        frame = await camera.get_frame()
        if format == "base64":
            return JSONResponse(
                content={
                    "source": frame.source,
                    "contentType": frame.content_type,
                    "dataBase64": base64.b64encode(frame.data).decode("ascii"),
                    "capturedAt": frame.captured_at,
                    "live": frame.source == "live",
                }
            )
        return Response(
            content=frame.data,
            media_type=frame.content_type,
            headers={
                "Cache-Control": "no-store",
                "X-Source": frame.source,
                "X-Captured-At": f"{frame.captured_at:.3f}",
            },
        )

    return handler


def _detections(camera: CameraFrameSource | None):
    async def handler() -> JSONResponse:
        if camera is None:
            return JSONResponse(
                status_code=503, content={"error": "camera unconfigured"}
            )
        return JSONResponse(
            content={
                "source": camera.detections_source,
                "live": camera.detections_source == "live",
                "detections": camera.last_detections,
            }
        )

    return handler
