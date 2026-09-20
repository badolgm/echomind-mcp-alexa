"""Tests for the MCP Streamable HTTP adapter built on FastAPI."""

from __future__ import annotations

import json
from typing import Any, Mapping

import httpx
import pytest
from fastapi import FastAPI

from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse, MCPTool
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    FastAPIMCPServer,
    InMemoryMCPServer,
)


@pytest.fixture
def streamable_app() -> FastAPI:
    mcp_service = InMemoryMCPServer()
    mcp_service.register_tool(
        MCPTool(
            name="alarm_set",
            description="Set a smart-home alarm for the user.",
            input_schema={"type": "object", "properties": {"when": {"type": "string"}}},
        ),
        _echo_handler,
    )
    server = FastAPIMCPServer(mcp_service=mcp_service)
    return server.app


async def _echo_handler(arguments: Mapping[str, Any]) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=json.dumps(arguments)),)
    )


@pytest.mark.asyncio
async def test_initialize_returns_capabilities_and_session(
    streamable_app: FastAPI,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

    assert response.status_code == 200
    assert response.headers["Mcp-Session-Id"]
    assert "event: endpoint" in response.text
    payload = _extract_payload(response.text)
    assert payload["id"] == 1
    assert payload["result"]["protocolVersion"] == "2025-11-25"
    assert payload["result"]["serverInfo"]["name"] == "echosystem"


@pytest.mark.asyncio
async def test_tools_list_exposes_registered_tools(streamable_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        session_id = init.headers["Mcp-Session-Id"]
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Mcp-Session-Id": session_id},
        )

    payload = _extract_payload(response.text)
    tools = payload["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["alarm_set"]
    assert tools[0]["inputSchema"]["type"] == "object"


@pytest.mark.asyncio
async def test_tools_call_dispatches_to_registered_handler(
    streamable_app: FastAPI,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        session_id = init.headers["Mcp-Session-Id"]
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "alarm_set", "arguments": {"when": "07:00"}},
            },
            headers={"Mcp-Session-Id": session_id},
        )

    payload = _extract_payload(response.text)
    assert payload["id"] == 3
    assert payload["result"]["isError"] is False
    assert payload["result"]["content"][0]["text"] == json.dumps({"when": "07:00"})


@pytest.mark.asyncio
async def test_unsupported_method_returns_json_rpc_error(
    streamable_app: FastAPI,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        session_id = init.headers["Mcp-Session-Id"]
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "bogus/method"},
            headers={"Mcp-Session-Id": session_id},
        )

    payload = _extract_payload(response.text)
    assert payload["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_missing_session_is_rejected(streamable_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}},
        )

    payload = _extract_payload(response.text)
    assert payload["error"]["code"] == -32000


def _extract_payload(body: str) -> dict[str, Any]:
    data_lines = [line[5:] for line in body.splitlines() if line.startswith("data:")]
    raw = data_lines[-1] if data_lines else body
    return json.loads(raw)
