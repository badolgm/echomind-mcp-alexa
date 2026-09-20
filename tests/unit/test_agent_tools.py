"""Unit tests for the agentic MCP tool catalog, registry and resolvers."""

from __future__ import annotations

import json
from typing import Any, Mapping

import httpx
import pytest

from src.domain.models.tools import (
    AGENTIC_TOOL_CATALOG,
    AgentTool,
    ToolCategory,
)
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    FastAPIMCPServer,
    InMemoryMCPServer,
)
from src.infrastructure.adapters.mcp.tool_resolvers import (
    ReminderBook,
    build_agentic_tool_registry,
    build_media_resolver,
    build_reminder_resolver,
)


def test_catalog_has_distinct_meaningful_tools() -> None:
    names = [tool.name for tool in AGENTIC_TOOL_CATALOG]
    assert "analyze_image_context" in names
    assert "summarize_document" in names
    assert "schedule_reminder" in names
    assert len(set(names)) == len(names)
    categories = {tool.category for tool in AGENTIC_TOOL_CATALOG}
    assert ToolCategory.ANALYSIS in categories
    assert ToolCategory.KNOWLEDGE in categories
    assert ToolCategory.PRODUCTIVITY in categories


def test_mandatory_schema_fields_are_validated_by_catalog() -> None:
    schedule = next(
        tool for tool in AGENTIC_TOOL_CATALOG if tool.name == "schedule_reminder"
    )
    assert schedule.required_fields == frozenset({"title", "dueAt"})
    assert (
        schedule.validate_arguments({"title": "meeting", "dueAt": "2026-01-01"}) == ()
    )
    assert schedule.validate_arguments({"title": "meeting"}) == ("dueAt",)


def test_agent_tool_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        AgentTool(
            name="bad_schema",
            description="Invalid schema",
            category=ToolCategory.PRODUCTIVITY,
            input_schema={"type": "object", "required": "not-a-list", "properties": {}},
        )


def test_duplicate_registration_is_rejected() -> None:
    registry = InMemoryMCPServer()
    first = AGENTIC_TOOL_CATALOG[0]
    registry.register_agent_tool(first, _tick_handler)
    with pytest.raises(ValueError):
        registry.register_agent_tool(first, _tick_handler)


@pytest.mark.asyncio
async def test_registry_projects_catalog_onto_mcp_tools() -> None:
    registry = build_agentic_tool_registry(_FakeLLM())
    tools = await registry.list_tools()
    assert sorted(tool.name for tool in tools) == sorted(
        tool.name for tool in AGENTIC_TOOL_CATALOG
    )
    analyze = next(tool for tool in tools if tool.name == "analyze_image_context")
    assert analyze.input_schema["required"] == ["attachment", "instruction"]


@pytest.mark.asyncio
async def test_schedule_reminder_tool_executes_through_registry() -> None:
    fake_llm = _FakeLLM()
    registry = build_agentic_tool_registry(fake_llm)
    response = await registry.call_tool(
        "schedule_reminder",
        {"title": "Standup", "dueAt": "2026-09-20T09:00:00+00:00", "note": "daily"},
    )
    assert response.is_error is False
    assert response.content[0].data.startswith("scheduled reminder ")
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_schedule_reminder_requires_title_and_due_at() -> None:
    registry = build_agentic_tool_registry(_FakeLLM())
    response = await registry.call_tool("schedule_reminder", {"title": "Standup"})
    assert response.is_error is True
    assert "required" in response.content[0].data


@pytest.mark.asyncio
async def test_media_resolver_forwards_attachment_to_llm() -> None:
    fake_llm = _FakeLLM()
    resolver = build_media_resolver(fake_llm, "Summarize this document.")

    response = await resolver(
        {
            "attachment": {
                "mimeType": "application/pdf",
                "dataBase64": "JVBERi0xLjQ=",
            },
            "instruction": "Extract actions.",
        }
    )

    assert response.is_error is False
    assert fake_llm.calls == 1
    sent = fake_llm.last_request
    assert sent.attachments[0].mime_type == "application/pdf"
    assert sent.attachments[0].data == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_media_resolver_rejects_invalid_base64() -> None:
    fake_llm = _FakeLLM()
    resolver = build_media_resolver(fake_llm, "Describe this.")
    response = await resolver(
        {"attachment": {"mimeType": "image/png", "dataBase64": "!!!not-base64!!!"}}
    )
    assert response.is_error is True
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_reminder_resolver_requires_title_and_due_at() -> None:
    book = ReminderBook()
    resolver = build_reminder_resolver(book)
    error = await resolver({"title": "Standup"})
    assert error.is_error is True
    ok = await resolver({"title": "Standup", "dueAt": "2026-09-20T09:00:00+00:00"})
    assert ok.is_error is False
    assert len(book) == 1


def test_reminder_book_returns_created_items() -> None:
    book = ReminderBook()
    reminder_id = book.add(
        title="Water plants", due_at="2026-09-21T08:00:00+00:00", note=""
    )
    assert len(book) == 1
    assert book.list()[0].reminder_id == reminder_id


@pytest.mark.asyncio
async def test_json_rpc_tools_call_reaches_agentic_registry() -> None:
    registry = build_agentic_tool_registry(_FakeLLM())
    server = FastAPIMCPServer(mcp_service=registry)
    app = server.app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        init = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        session_id = init.headers["Mcp-Session-Id"]
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Mcp-Session-Id": session_id},
        )
        called = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "schedule_reminder",
                    "arguments": {
                        "title": "Meditate",
                        "dueAt": "2026-09-22T07:00:00+00:00",
                    },
                },
            },
            headers={"Mcp-Session-Id": session_id},
        )

    listed_payload = _extract_payload(listed.text)
    assert {tool["name"] for tool in listed_payload["result"]["tools"]} >= {
        "analyze_image_context",
        "summarize_document",
        "schedule_reminder",
    }
    called_payload = _extract_payload(called.text)
    assert called_payload["result"]["isError"] is False
    assert "scheduled reminder" in called_payload["result"]["content"][0]["text"]


def _extract_payload(body: str) -> dict[str, Any]:
    data_lines = [line[5:] for line in body.splitlines() if line.startswith("data:")]
    raw = data_lines[0] if data_lines else body
    return json.loads(raw)


async def _tick_handler(arguments: Mapping[str, Any]) -> MCPResponse:
    return MCPResponse(content=(MCPContentItem(kind="text", data="ok"),))


class _FakeLLM(LLMServicePort):
    """Minimal LLMServicePort double used by resolver tests."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.last_request = request
        return LLMResponse(text="analyzed by fake", model_id="fake-model")
