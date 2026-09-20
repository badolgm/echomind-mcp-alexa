"""Tests for the Ambient Awareness tool, resolver and safety gate."""

from __future__ import annotations

import base64

import pytest

from src.domain.models.tools import AGENTIC_TOOL_CATALOG, AgentTool, ToolCategory
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.mcp.tool_resolvers import (
    build_agentic_tool_registry,
    build_ambient_resolver,
    scan_ambient_signals,
)

_AMBIENT_TOOL_NAME = "analyze_ambient_stream"


def _ambient_tool() -> AgentTool:
    return next(
        tool for tool in AGENTIC_TOOL_CATALOG if tool.name == _AMBIENT_TOOL_NAME
    )


class _FakeLLM(LLMServicePort):
    def __init__(self, text: str = "model narrative") -> None:
        self.text = text
        self.calls = 0
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.last_request = request
        return LLMResponse(text=self.text, model_id="fake-model")


def test_catalog_registers_ambient_tool() -> None:
    tool = _ambient_tool()
    assert tool.category is ToolCategory.SAFETY
    assert "observation" in tool.required_fields
    assert "location" in tool.input_schema["properties"]
    assert "attachment" in tool.input_schema["properties"]


def test_scan_ambient_signals_grades_snapshots() -> None:
    critical = scan_ambient_signals("Grandma fell in the kitchen")
    assert critical.risk_level == "CRITICAL"
    assert "possible fall" in critical.signals
    assert critical.recommendation

    medium = scan_ambient_signals("the cat is alone and crying")
    assert medium.risk_level == "MEDIUM"
    assert "cat condition" in medium.signals

    low = scan_ambient_signals("Everything looks completely normal today")
    assert low.risk_level == "LOW"
    assert low.signals == ()


@pytest.mark.asyncio
async def test_resolver_rejects_missing_observation() -> None:
    resolver = build_ambient_resolver(_FakeLLM())
    response = await resolver({"location": "living room"})
    assert response.is_error is True
    assert "observation" in response.content[0].data


@pytest.mark.asyncio
async def test_resolver_reports_critical_safety_gate() -> None:
    fake = _FakeLLM()
    resolver = build_ambient_resolver(fake)
    response = await resolver(
        {
            "location": "kitchen",
            "timestamp": "2026-09-19T12:00:00+00:00",
            "observation": "Smoke is coming out of the oven",
        }
    )

    assert response.is_error is False
    text = response.content[0].data
    assert "safety gate risk: CRITICAL" in text
    assert "location: kitchen" in text
    assert "timestamp: 2026-09-19T12:00:00+00:00" in text
    assert "model analysis: model narrative" in text
    assert fake.calls == 1
    assert fake.last_request is not None
    assert "kitchen" in fake.last_request.user_prompt


@pytest.mark.asyncio
async def test_resolver_sends_attachment_to_llm() -> None:
    fake = _FakeLLM()
    resolver = build_ambient_resolver(fake)
    attachment = {
        "mimeType": "image/jpeg",
        "dataBase64": base64.b64encode(b"fake-image-bytes").decode("ascii"),
    }
    response = await resolver(
        {"observation": "Camera frame of the hallway", "attachment": attachment}
    )

    assert response.is_error is False
    assert fake.last_request is not None
    assert len(fake.last_request.attachments) == 1
    payload = fake.last_request.attachments[0]
    assert payload.mime_type == "image/jpeg"
    assert payload.kind.value == "image"
    assert payload.data == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_resolver_rejects_invalid_base64() -> None:
    resolver = build_ambient_resolver(_FakeLLM())
    response = await resolver(
        {"observation": "frame", "attachment": {"dataBase64": "!!!not-base64!!!"}}
    )
    assert response.is_error is True


@pytest.mark.asyncio
async def test_ambient_tool_exposed_through_mcp_registry() -> None:
    registry = build_agentic_tool_registry(_FakeLLM())
    tools = await registry.list_tools()
    assert _AMBIENT_TOOL_NAME in {tool.name for tool in tools}
