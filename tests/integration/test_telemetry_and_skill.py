"""Integration tests for telemetry exposure, /metrics and the Alexa+ skill manifest."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from botocore.exceptions import ClientError

import src.main
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse, MCPTool
from src.infrastructure.adapters.aws.fallback_llm_adapter import (
    ResilientLLMAdapter,
)
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    FastAPIMCPServer,
    InMemoryMCPServer,
)
from src.infrastructure.adapters.mcp.session_manager import SessionManager
from src.infrastructure.config.telemetry import Telemetry

SKILL_MANIFEST_PATH = "alexa_skill/skill.json"


def _quota_error() -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "ThrottlingException", "Message": "throttled"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation_name="Converse",
    )


class _FailingPrimary(LLMServicePort):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise _quota_error()


class _StaticFallback(LLMServicePort):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="local-ok", model_id="rule-engine")


async def _echo_handler(arguments: dict) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=json.dumps(arguments)),)
    )


def _build_instrumented_server() -> tuple[FastAPIMCPServer, Telemetry]:
    telemetry = Telemetry()
    registry = InMemoryMCPServer()
    registry.register_tool(
        MCPTool(
            name="echo",
            description="echo arguments back",
            input_schema={"type": "object", "properties": {}},
        ),
        _echo_handler,
    )
    server = FastAPIMCPServer(
        mcp_service=registry,
        session_manager=SessionManager(),
        telemetry=telemetry,
    )
    return server, telemetry


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.5, 50), (0.95, 95), (0.99, 99)],
)
def test_telemetry_percentiles(ratio: float, expected: float) -> None:
    from src.infrastructure.config.telemetry import percentile

    assert percentile(list(range(1, 101)), ratio) == expected


def test_telemetry_empty_snapshot() -> None:
    snapshot = Telemetry().snapshot()
    assert snapshot["total_tool_calls"] == 0
    assert snapshot["fallbacks_activated"] == 0
    assert snapshot["tool_calls"] == {}
    assert snapshot["latency_ms"] == {}
    assert snapshot["uptime_seconds"] >= 0


def test_telemetry_records_tools_and_latency() -> None:
    telemetry = Telemetry()
    for i in range(100):
        telemetry.record_latency("tools/call", i + 1)
        telemetry.record_tool_call("echo")
    telemetry.record_fallback()
    snapshot = telemetry.snapshot()
    assert snapshot["total_tool_calls"] == 100
    assert snapshot["tool_calls"] == {"echo": 100}
    assert snapshot["fallbacks_activated"] == 1
    metrics = snapshot["latency_ms"]["tools/call"]
    assert metrics["count"] == 100
    assert metrics["p50_ms"] == 50
    assert metrics["p95_ms"] == 95
    assert metrics["p99_ms"] == 99


@pytest.mark.asyncio
async def test_mcp_server_instruments_tool_calls() -> None:
    server, telemetry = _build_instrumented_server()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
        )
        session_id = init.headers.get("Mcp-Session-Id")
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"msg": "hello"}},
            },
            headers={"Mcp-Session-Id": session_id},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert json.loads(result["content"][0]["text"]) == {"msg": "hello"}

    snapshot = telemetry.snapshot()
    assert snapshot["tool_calls"] == {"echo": 1}
    assert snapshot["total_tool_calls"] == 1
    assert snapshot["fallbacks_activated"] == 0
    assert "tools/call" in snapshot["latency_ms"]
    assert snapshot["latency_ms"]["tools/call"]["count"] == 1
    assert snapshot["latency_ms"]["tools/call"]["p50_ms"] > 0
    assert "initialize" in snapshot["latency_ms"]


@pytest.mark.asyncio
async def test_resilient_adapter_reports_fallback_to_telemetry() -> None:
    telemetry = Telemetry()
    adapter = ResilientLLMAdapter(
        primary=_FailingPrimary(),
        fallback=_StaticFallback(),
        cooldown_seconds=0,
        on_fallback=telemetry.fallback_listener,
    )
    request = LLMRequest(system_prompt="system", user_prompt="user")
    response = await adapter.generate(request)
    assert response.text == "local-ok"
    snapshot = telemetry.snapshot()
    assert snapshot["fallbacks_activated"] == 1
    assert adapter.stats["failovers"] == 1


def test_metrics_endpoint_exposed_on_composed_app() -> None:
    handler = src.main._metrics(Telemetry())
    snapshot = asyncio.run(handler())
    assert set(snapshot) >= {
        "uptime_seconds",
        "tool_calls",
        "total_tool_calls",
        "fallbacks_activated",
        "latency_ms",
    }


def test_skill_manifest_is_valid_alexa_agent_skill() -> None:
    with open(SKILL_MANIFEST_PATH, encoding="utf-8") as handle:
        manifest = json.load(handle)

    skill = manifest["skill"]
    assert manifest["manifestVersion"] == "1.0"
    assert skill["apis"]["mcp"]["type"] == "agent"
    assert skill["apis"]["mcp"]["protocol"] == "streamable-http"
    assert skill["apis"]["mcp"]["protocolVersion"] == "2025-11-25"
    assert skill["apis"]["mcp"]["transport"]["uri"].endswith("/mcp")
    assert skill["apis"]["mcp"]["transport"]["session"]["header"] == "Mcp-Session-Id"
    assert "tools" in skill["apis"]["mcp"]["capabilities"]

    permissions = {item["name"] for item in skill["permissions"]}
    assert any("camera" in name for name in permissions)
    assert any("mediaStreaming" in name for name in permissions)

    inputs = set(skill["apis"]["mcp"]["modes"]["multimodal"]["input"])
    assert not inputs.issubset({"text"})
    assert "events" in skill
    assert "streamingResponses" in skill["apis"]["mcp"]["modes"]
