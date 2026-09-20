"""Integration tests for the MCP Streamable HTTP session lifecycle.

Validates the full Alexa+ <-> MCP conversation cycle over the ASGI transport:
session negotiation, the GET SSE stream (endpoint + server-push events) and
session termination when the stream ends, plus session-manager lifecycle and
persistence restore.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

import httpx
import pytest
from fastapi import FastAPI

from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse, MCPTool
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    FastAPIMCPServer,
    InMemoryMCPServer,
    SESSION_HEADER,
)
from src.infrastructure.adapters.mcp.session_manager import (
    InMemorySessionPersistence,
    SessionManager,
)

_ALARM_TOOL = MCPTool(
    name="alarm_set",
    description="Set a smart-home alarm for the user.",
    input_schema={"type": "object", "properties": {"when": {"type": "string"}}},
)


@pytest.fixture
def mcp_environment() -> tuple[FastAPI, SessionManager]:
    mcp_service = InMemoryMCPServer()
    mcp_service.register_tool(_ALARM_TOOL, _echo_handler)
    session_manager = SessionManager()
    server = FastAPIMCPServer(
        mcp_service=mcp_service, session_manager=session_manager, keepalive_seconds=5
    )
    return server.app, session_manager


async def _echo_handler(arguments: Mapping[str, Any]) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=json.dumps(arguments)),)
    )


def _initialize() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


def _list_tools(request_id: int = 2) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}


def _notify_initialized() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": "notifications/initialized"}


def _extract_last_payload(body: str) -> dict[str, Any]:
    data_lines = [line[5:] for line in body.splitlines() if line.startswith("data:")]
    raw = data_lines[-1] if data_lines else body
    return json.loads(raw)


def _parse_sse_block(raw: str) -> tuple[str, str]:
    event = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    return event, "\n".join(data_lines)


async def _collect_sse_events(
    client: httpx.AsyncClient, session_id: str, events: list[dict[str, str]]
) -> None:
    async with client.stream(
        "GET", "/mcp", headers={SESSION_HEADER: session_id}
    ) as response:
        assert response.status_code == 200
        body = await response.aread()
    buffer = body.decode("utf-8")
    while "\n\n" in buffer:
        raw, buffer = buffer.split("\n\n", 1)
        if not raw.strip():
            continue
        event, data = _parse_sse_block(raw)
        events.append({"event": event, "data": data})


@pytest.mark.asyncio
async def test_session_negotiated_then_marked_ready(
    mcp_environment: tuple[FastAPI, SessionManager],
) -> None:
    app, _session_manager = mcp_environment
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp", json=_initialize(), headers={"Accept": "text/event-stream"}
        )
        assert init.status_code == 200
        session_id = init.headers[SESSION_HEADER]
        assert session_id
        assert "event: endpoint" in init.text
        payload = _extract_last_payload(init.text)
        assert payload["result"]["protocolVersion"] == "2025-11-25"
        assert payload["result"]["capabilities"]["tools"] == {"listChanged": False}

        ready = await client.post(
            "/mcp",
            json=_notify_initialized(),
            headers={SESSION_HEADER: session_id},
        )
        assert ready.status_code == 202

        listing = await client.post(
            "/mcp",
            json=_list_tools(),
            headers={SESSION_HEADER: session_id},
        )
        assert _extract_last_payload(listing.text)["result"]["tools"]


@pytest.mark.asyncio
async def test_get_stream_relays_endpoint_and_server_push(
    mcp_environment: tuple[FastAPI, SessionManager],
) -> None:
    app, session_manager = mcp_environment
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        init = await client.post("/mcp", json=_initialize())
        session_id = init.headers[SESSION_HEADER]

        events: list[dict[str, str]] = []
        reader = asyncio.create_task(_collect_sse_events(client, session_id, events))

        listing = await client.post(
            "/mcp",
            json=_list_tools(),
            headers={SESSION_HEADER: session_id},
        )
        assert _extract_last_payload(listing.text)["id"] == 2

        session_manager.publish(
            session_id,
            {
                "jsonrpc": "2.0",
                "id": None,
                "method": "notifications/tools/list_changed",
            },
        )
        session_manager.publish(session_id, {"close": True})

        await asyncio.wait_for(reader, timeout=5)

        assert [entry["event"] for entry in events] == ["endpoint", "message"]
        assert events[0]["event"] == "endpoint"
        assert json.loads(events[0]["data"])["endpoint"].endswith("/mcp")
        assert (
            json.loads(events[1]["data"])["method"]
            == "notifications/tools/list_changed"
        )

        ended = await client.post(
            "/mcp",
            json=_list_tools(request_id=7),
            headers={SESSION_HEADER: session_id},
        )
        assert _extract_last_payload(ended.text)["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_unknown_session_on_get_is_rejected(
    mcp_environment: tuple[FastAPI, SessionManager],
) -> None:
    app, _session_manager = mcp_environment
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/mcp", headers={SESSION_HEADER: "does-not-exist"})
    assert response.status_code == 404
    assert _extract_last_payload(response.text)["error"]["code"] == -32001


def test_session_manager_expires_idle_sessions() -> None:
    manager = SessionManager(idle_timeout_seconds=1)
    session = manager.create()
    session.last_active = "1970-01-01T00:00:00+00:00"
    assert manager.expire_stale() == 1
    assert manager.get(session.session_id) is None


def test_session_restored_from_persistence() -> None:
    persistence = InMemorySessionPersistence()
    first = SessionManager(persistence=persistence)
    session = first.create()
    session.mark_initialized("2025-11-25")
    first.touch(session)
    session_id = session.session_id

    restarted = SessionManager(persistence=persistence)
    restored = restarted.get(session_id)
    assert restored is not None
    assert restored.is_initialized
    assert restored.protocol_version == "2025-11-25"
    assert restarted.publish(session_id, {"wake": True}) is True

    restarted.destroy(session_id)
    assert restarted.get(session_id) is None
    assert persistence.load(session_id) is None
