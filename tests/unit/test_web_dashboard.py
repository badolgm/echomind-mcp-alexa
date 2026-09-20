"""Tests for the EchoMind MCP Control Center web dashboard."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

import src.main
from src.infrastructure.adapters.mcp.web_dashboard import (
    DASHBOARD_ROUTE,
    mount_dashboard,
    stream_dashboard_events,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.config.telemetry import Telemetry


def _build_app(hub: EventHub | None = None) -> object:
    import fastapi

    app = fastapi.FastAPI()
    mount_dashboard(app, hub)
    return app


@pytest.mark.asyncio
async def test_root_redirects_to_dashboard() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_build_app()), base_url="http://test"
    ) as client:
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == DASHBOARD_ROUTE


@pytest.mark.asyncio
async def test_dashboard_renders_control_center_html() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_build_app()), base_url="http://test"
    ) as client:
        response = await client.get(DASHBOARD_ROUTE)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        html = response.text
        assert "<!DOCTYPE html>" in html
        assert "EchoMind MCP Control Center" in html
        for marker in (
            "QUOTA FALLBACK MODE ACTIVE",
            "Active Multimodal Analytics",
            "Agent Metrics",
            "Live Tools Log",
            "AWS Bedrock &amp; Utilization",
            "Context Enrichment (MCP)",
            "/dashboard/events",
            "/metrics",
            "cdn.tailwindcss.com",
        ):
            assert marker in html


@pytest.mark.asyncio
async def test_dashboard_events_stream_fans_out_tool_events() -> None:
    hub = EventHub()
    stream = stream_dashboard_events(hub, keepalive_seconds=5.0)
    first = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0.02)
    hub.publish({"kind": "tool_call", "tool": "echo", "status": "OK", "ts": 1.5})
    chunk = await asyncio.wait_for(first, timeout=2)
    assert "data: " in chunk
    assert '"tool": "echo"' in chunk
    assert '"status": "OK"' in chunk
    await stream.aclose()


def test_metrics_handler_includes_provider_status() -> None:
    fake_llm = SimpleNamespace(
        active_provider="fallback", is_degraded=True, stats={"failovers": 3}
    )
    handler = src.main._metrics(Telemetry(), fake_llm)
    snapshot = asyncio.run(handler())
    assert snapshot["provider"]["active_provider"] == "fallback"
    assert snapshot["provider"]["is_degraded"] is True
    assert snapshot["provider"]["stats"] == {"failovers": 3}


def test_metrics_handler_omits_provider_when_not_wired() -> None:
    handler = src.main._metrics(Telemetry())
    snapshot = asyncio.run(handler())
    assert "provider" not in snapshot
