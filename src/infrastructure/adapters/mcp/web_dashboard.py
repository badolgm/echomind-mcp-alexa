"""EchoMind MCP Control Center: web dashboard served by FastAPI.

Mounts three routes on any FastAPI app:

- ``/`` redirects to the dashboard.
- ``/dashboard`` renders the Control Center (Tailwind CSS via CDN, vanilla JS).
- ``/dashboard/events`` is an SSE stream of tool executions fed by the
  :class:`EventHub` broadcast from the MCP transport.

The dashboard polls ``/metrics`` every two seconds for latency, tool counts and
the Quota Fallback Protocol status, and consumes ``/dashboard/events`` through
``EventSource`` for the live tools log. No frontend framework ships with the
server image.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from src.infrastructure.config.event_hub import EventHub

DASHBOARD_ROUTE = "/dashboard"
STATIC_DIR = Path(__file__).resolve().parents[3] / "static"
_HTML_CACHE: str | None = None


def _dashboard_html() -> str:
    global _HTML_CACHE
    if _HTML_CACHE is None:
        template = STATIC_DIR / "dashboard.html"
        if not template.exists():
            raise RuntimeError(f"dashboard template missing: {template}")
        _HTML_CACHE = template.read_text(encoding="utf-8")
    return _HTML_CACHE


def mount_dashboard(
    app: FastAPI,
    event_hub: EventHub | None = None,
    *,
    keepalive_seconds: float = 15.0,
) -> None:
    """Register the Control Center routes on ``app``."""
    app.add_api_route("/", _root_redirect, methods=["GET"])
    app.add_api_route(DASHBOARD_ROUTE, _render_dashboard, methods=["GET"])
    if event_hub is not None:
        app.add_api_route(
            f"{DASHBOARD_ROUTE}/events",
            _event_stream(event_hub, keepalive_seconds),
            methods=["GET"],
        )


async def _root_redirect() -> RedirectResponse:
    return RedirectResponse(DASHBOARD_ROUTE, status_code=307)


async def _render_dashboard() -> HTMLResponse:
    return HTMLResponse(content=_dashboard_html())


async def stream_dashboard_events(
    event_hub: EventHub, keepalive_seconds: float = 15.0
) -> AsyncIterator[str]:
    """Yield SSE messages for every event broadcast by the transport."""
    queue = event_hub.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        event_hub.unsubscribe(queue)


def _event_stream(
    event_hub: EventHub, keepalive_seconds: float
) -> Callable[[], StreamingResponse]:
    def endpoint() -> StreamingResponse:
        return StreamingResponse(
            stream_dashboard_events(event_hub, keepalive_seconds),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return endpoint
