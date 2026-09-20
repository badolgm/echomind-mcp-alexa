"""MCP Streamable HTTP adapter built on FastAPI.

This module implements the Model Context Protocol HTTP *Streamable* transport
over a FastAPI application. It exposes the JSON-RPC 2.0 subset needed by an
MCP client: initialize, notifications/initialized, tools/list and tools/call.

Two classes with a single responsibility each:
  - InMemoryMCPServer: in-memory MCPServerPort implementation (tool registry).
  - FastAPIMCPServer:      FastAPI application exposing the Streamable HTTP
                            transport on top of any MCPServerPort.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import StreamingResponse

from src.domain.models.tools import AgentTool
from src.domain.ports.output.mcp_port import (
    MCPContentItem,
    MCPServerPort,
    MCPResponse,
    MCPTool,
)

JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "echosystem"
SERVER_VERSION = "0.1.0"
SESSION_HEADER = "Mcp-Session-Id"
DEFAULT_ENDPOINT = "/mcp"

ToolHandler = Callable[[Mapping[str, Any]], Awaitable[MCPResponse]]


def agent_tool_to_mcp_tool(agent_tool: AgentTool) -> MCPTool:
    """Project a domain AgentTool onto the MCP transport descriptor."""
    return MCPTool(
        name=agent_tool.name,
        description=agent_tool.description,
        input_schema=agent_tool.input_schema,
    )


def _json_rpc_response(
    request_id: int | str, result: Mapping[str, Any]
) -> dict[str, Any]:
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": dict(result)}


def _json_rpc_error(
    request_id: int | str, code: int, message: str, data: object | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": error}


def _as_sse_event(payload: Mapping[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


@dataclass
class _McpSession:
    """Transport-level session holding a per-client event queue."""

    session_id: str
    events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


class InMemoryMCPServer(MCPServerPort):
    """MCPServerPort implementation backed by an in-memory tool registry.

    The registry maps JSON-RPC ``tools/call`` names directly to async tool
    handlers (resolvers), which may close over application use cases.
    """

    def __init__(self) -> None:
        self._registry: dict[str, tuple[MCPTool, ToolHandler]] = {}

    def register_tool(self, tool: MCPTool, handler: ToolHandler) -> None:
        self._register(tool.name, tool, handler)

    def register_agent_tool(self, agent_tool: AgentTool, handler: ToolHandler) -> None:
        self._register(agent_tool.name, agent_tool_to_mcp_tool(agent_tool), handler)

    def _register(self, name: str, tool: MCPTool, handler: ToolHandler) -> None:
        if name in self._registry:
            raise ValueError(f"tool already registered: {name}")
        self._registry[name] = (tool, handler)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return tuple(tool for tool, _handler in self._registry.values())

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> MCPResponse:
        entry = self._registry.get(name)
        if entry is None:
            return MCPResponse(
                content=(MCPContentItem(kind="text", data=f"tool not found: {name}"),),
                is_error=True,
            )
        _tool, handler = entry
        return await handler(dict(arguments))


class FastAPIMCPServer:
    """Exposes any MCPServerPort over MCP Streamable HTTP using FastAPI.

    The resulting ``app`` attribute can be served with uvicorn or mounted in a
    larger FastAPI application::

        server = FastAPIMCPServer(mcp_service=my_port)
        app = server.app
    """

    def __init__(
        self, *, mcp_service: MCPServerPort, endpoint: str = DEFAULT_ENDPOINT
    ) -> None:
        self._mcp_service = mcp_service
        self._endpoint = endpoint
        self._sessions: dict[str, _McpSession] = {}
        self.app = FastAPI(
            title=f"{SERVER_NAME} MCP Streamable HTTP", version=SERVER_VERSION
        )
        self._register_routes()

    def _register_routes(self) -> None:
        self.app.add_api_route(self._endpoint, self._read_stream, methods=["GET"])
        self.app.add_api_route(self._endpoint, self._post_message, methods=["POST"])

    async def _read_stream(self, request: Request) -> StreamingResponse:
        session_id = str(uuid.uuid4())
        session = _McpSession(session_id=session_id)
        self._sessions[session_id] = session
        return StreamingResponse(
            self._stream_events(session),
            media_type="text/event-stream",
            headers={SESSION_HEADER: session_id},
        )

    async def _stream_events(self, session: _McpSession) -> AsyncIterator[str]:
        try:
            while True:
                payload = await session.events.get()
                if payload.get("close") is True:
                    break
                yield _as_sse_event(payload)
        finally:
            self._sessions.pop(session.session_id, None)

    async def _post_message(
        self,
        request: Request,
        mcp_session_id: str | None = Header(default=None, alias=SESSION_HEADER),
    ) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            return Response(status_code=400, content="Invalid JSON payload.")
        if not isinstance(payload, dict):
            return Response(
                status_code=400, content="JSON-RPC payload must be an object."
            )

        output, session_id = await self._handle(payload, mcp_session_id)
        headers = {SESSION_HEADER: session_id} if session_id else {}
        if output is None:
            return Response(status_code=202, headers=headers)
        if "text/event-stream" in request.headers.get("accept", ""):
            return Response(
                content=_as_sse_event(output),
                media_type="text/event-stream",
                headers=headers,
            )
        return Response(
            content=json.dumps(output), media_type="application/json", headers=headers
        )

    async def _handle(
        self, payload: dict[str, Any], session_id: str | None
    ) -> tuple[dict[str, Any] | None, str | None]:
        method = payload.get("method")
        request_id = payload.get("id")
        session = self._sessions.get(session_id or "")

        if method == "initialize":
            if session is None:
                session_id = str(uuid.uuid4())
                self._sessions[session_id] = _McpSession(session_id=session_id)
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
            return _json_rpc_response(request_id, result), session_id

        if session is None:
            return (
                _json_rpc_error(
                    request_id, -32000, "no active MCP session; call initialize first"
                ),
                None,
            )

        if method == "ping":
            return _json_rpc_response(request_id, {}), session_id

        if method == "notifications/initialized" or (
            isinstance(method, str) and method.startswith("notifications/")
        ):
            return None, session_id

        if method == "tools/list":
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in await self._mcp_service.list_tools()
            ]
            return _json_rpc_response(request_id, {"tools": tools}), session_id

        if method == "tools/call":
            params = payload.get("params")
            if not isinstance(params, dict):
                return (
                    _json_rpc_error(
                        request_id, -32602, "tools/call requires a params object"
                    ),
                    session_id,
                )
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return (
                    _json_rpc_error(
                        request_id, -32602, "tools/call requires a string tool name"
                    ),
                    session_id,
                )
            if not isinstance(arguments, dict):
                return (
                    _json_rpc_error(
                        request_id, -32602, "tool arguments must be an object"
                    ),
                    session_id,
                )
            response = await self._mcp_service.call_tool(name, arguments)
            result = {
                "content": [
                    {"type": item.kind, "text": item.data} for item in response.content
                ],
                "isError": response.is_error,
            }
            return _json_rpc_response(request_id, result), session_id

        return (
            _json_rpc_error(request_id, -32601, f"method not found: {method}"),
            session_id,
        )
