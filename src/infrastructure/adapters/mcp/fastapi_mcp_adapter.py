"""MCP Streamable HTTP adapter built on FastAPI.

This module implements the Model Context Protocol HTTP *Streamable* transport
over a FastAPI application. It exposes the JSON-RPC 2.0 subset needed by an
MCP client: initialize, notifications/initialized, tools/list and tools/call,
following the 2025 session negotiation flow:

  1. The client POSTs ``initialize``; the server creates a persistent session,
     announces it through the ``Mcp-Session-Id`` header and answers with an
     SSE stream carrying an ``endpoint`` event plus the JSON-RPC result.
  2. The client POSTs ``notifications/initialized`` to mark the session ready.
  3. JSON-RPC requests travel over POST; server-initiated messages and the
     ``endpoint`` event are delivered over the GET SSE stream.

Two classes with a single responsibility each:
  - InMemoryMCPServer: in-memory MCPServerPort implementation (tool registry).
  - FastAPIMCPServer:  FastAPI application exposing the Streamable HTTP
                       transport on top of any MCPServerPort and any
                       SessionManager.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src.domain.models.tools import AgentTool
from src.domain.ports.output.mcp_port import (
    MCPContentItem,
    MCPServerPort,
    MCPResponse,
    MCPTool,
)
from src.infrastructure.adapters.mcp.session_manager import (
    McpSession,
    SessionManager,
    SessionStatus,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.config.telemetry import Telemetry

JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
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


def _as_endpoint_event(endpoint: str) -> str:
    return f"event: endpoint\ndata: {json.dumps({'endpoint': endpoint})}\n\n"


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

    Session lifecycle is delegated to a :class:`SessionManager`; sessions are
    created during ``initialize``, annotated via ``notifications/initialized``,
    kept warm by the GET SSE stream and finally destroyed when the stream ends
    or the session idles out::

        registry = build_agentic_tool_registry(llm_service)
        sessions = SessionManager()
        server = FastAPIMCPServer(
            mcp_service=registry, session_manager=sessions
        )
        app = server.app
    """

    def __init__(
        self,
        *,
        mcp_service: MCPServerPort,
        session_manager: SessionManager | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        keepalive_seconds: int = 15,
        telemetry: Telemetry | None = None,
        event_hub: EventHub | None = None,
    ) -> None:
        self._mcp_service = mcp_service
        self._session_manager = session_manager or SessionManager()
        self._endpoint = endpoint
        self._keepalive_seconds = keepalive_seconds
        self._telemetry = telemetry or Telemetry()
        self._event_hub = event_hub
        self.app = FastAPI(
            title=f"{SERVER_NAME} MCP Streamable HTTP", version=SERVER_VERSION
        )
        self.app.add_api_route(self._endpoint, self._read_stream, methods=["GET"])
        self.app.add_api_route(self._endpoint, self._post_message, methods=["POST"])

    def expire_stale_sessions(self) -> int:
        return self._session_manager.expire_stale()

    async def _read_stream(
        self,
        request: Request,
        session_id: str | None = None,
        mcp_session_id: str | None = Header(default=None, alias=SESSION_HEADER),
    ) -> Response:
        session = self._session_manager.get(session_id or mcp_session_id)
        if session is None or session.status is SessionStatus.CLOSED:
            return JSONResponse(
                status_code=404,
                content={
                    "jsonrpc": JSON_RPC_VERSION,
                    "error": {"code": -32001, "message": "unknown or expired session"},
                },
            )
        self._session_manager.touch(session)
        return StreamingResponse(
            self._stream_events(session),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                SESSION_HEADER: session.session_id,
            },
        )

    async def _stream_events(self, session: McpSession) -> AsyncIterator[str]:
        yield _as_endpoint_event(self._endpoint)
        try:
            while session.status is not SessionStatus.CLOSED:
                try:
                    payload = await asyncio.wait_for(
                        session.events.get(), timeout=self._keepalive_seconds
                    )
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if payload.get("close") is True:
                    break
                yield _as_sse_event(payload)
        finally:
            self._session_manager.destroy(session.session_id)

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
        method = payload.get("method") or "unknown"
        started = time.perf_counter()
        response = await self._dispatch(payload, mcp_session_id, request)
        milliseconds = (time.perf_counter() - started) * 1000
        self._telemetry.record_latency(method, milliseconds)
        return response

    async def _dispatch(
        self,
        payload: dict[str, Any],
        session_id: str | None,
        request: Request,
    ) -> Response:
        method = payload.get("method")

        if method == "initialize":
            return await self._initialize(payload, session_id, request)

        session = self._session_manager.get(session_id)
        if session is None:
            return self._json_error_response(payload.get("id"), -32000)
        if session.status is SessionStatus.CLOSED:
            return self._json_error_response(payload.get("id"), -32001)

        self._session_manager.touch(session)
        output = await self._handle(payload, session)
        session_id = session.session_id
        if output is None:
            return Response(status_code=202, headers={SESSION_HEADER: session_id})
        if "text/event-stream" in request.headers.get("accept", ""):
            return Response(
                content=_as_sse_event(output),
                media_type="text/event-stream",
                headers={SESSION_HEADER: session_id},
            )
        return Response(
            content=json.dumps(output),
            media_type="application/json",
            headers={SESSION_HEADER: session_id},
        )

    async def _initialize(
        self, payload: dict[str, Any], session_id: str | None, request: Request
    ) -> Response:
        session = self._session_manager.get(session_id) or (
            self._session_manager.create()
        )
        session.mark_initialized(MCP_PROTOCOL_VERSION)
        self._session_manager.touch(session)
        request_id = payload.get("id")
        result = _json_rpc_response(
            request_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
        base_url = str(request.base_url).rstrip("/")
        body = _as_endpoint_event(f"{base_url}{self._endpoint}") + _as_sse_event(result)
        return Response(
            content=body,
            media_type="text/event-stream",
            headers={SESSION_HEADER: session.session_id},
        )

    def _json_error_response(
        self, request_id: int | str, code: int, message: str | None = None
    ) -> JSONResponse:
        if code == -32000:
            message = "no active MCP session; call initialize first"
        elif code == -32001:
            message = "session has been terminated"
        return JSONResponse(content=_json_rpc_error(request_id, code, message))

    async def _handle(
        self, payload: dict[str, Any], session: McpSession
    ) -> dict[str, Any] | None:
        method = payload.get("method")
        request_id = payload.get("id")

        if method == "ping":
            return _json_rpc_response(request_id, {})

        if method == "notifications/initialized":
            session.mark_initialized(MCP_PROTOCOL_VERSION)
            self._session_manager.touch(session)
            return None
        if isinstance(method, str) and method.startswith("notifications/"):
            return None

        if method == "tools/list":
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in await self._mcp_service.list_tools()
            ]
            return _json_rpc_response(request_id, {"tools": tools})

        if method == "tools/call":
            return await self._call_tool(payload, request_id)

        return _json_rpc_error(request_id, -32601, f"method not found: {method}")

    async def _call_tool(
        self, payload: dict[str, Any], request_id: int | str | None
    ) -> dict[str, Any]:
        params = payload.get("params")
        if not isinstance(params, dict):
            return _json_rpc_error(
                request_id, -32602, "tools/call requires a params object"
            )
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return _json_rpc_error(
                request_id, -32602, "tools/call requires a string tool name"
            )
        if not isinstance(arguments, dict):
            return _json_rpc_error(
                request_id, -32602, "tool arguments must be an object"
            )
        self._publish_tool_event(name, "IN_PROGRESS")
        try:
            response = await self._mcp_service.call_tool(name, arguments)
        except Exception:
            self._publish_tool_event(name, "ERROR")
            raise
        self._telemetry.record_tool_call(name)
        status = "OK"
        if response.is_error:
            status = "ERROR"
        else:
            report = "".join(item.data for item in response.content)
            if "risk: CRITICAL" in report:
                status = "CRITICAL"
        self._publish_tool_event(name, status)
        result = {
            "content": [
                {"type": item.kind, "text": item.data} for item in response.content
            ],
            "isError": response.is_error,
        }
        return _json_rpc_response(request_id, result)

    def _publish_tool_event(self, tool_name: str, status: str) -> None:
        if self._event_hub is None:
            return
        self._event_hub.publish(
            {
                "kind": "tool_call",
                "tool": tool_name,
                "status": status,
                "ts": time.time(),
            }
        )
