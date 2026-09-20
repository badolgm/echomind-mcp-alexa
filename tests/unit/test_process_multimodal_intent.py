"""Unit tests for the ProcessMultimodalIntentUseCase with mocked ports."""

from __future__ import annotations

import base64
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from src.application.dtos.intent_dto import ProcessMultimodalIntentRequest
from src.application.use_cases.process_multimodal_intent import (
    ProcessMultimodalIntentUseCase,
    parse_multimodal_classification,
)
from src.domain.models.intent import Modality
from src.domain.models.tools import (
    AGENTIC_TOOL_CATALOG,
    AgentTool,
    MultimodalAttachment,
    ToolCategory,
)
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import InMemoryMCPServer


class FakeMultimodalLLM(LLMServicePort):
    """LLMServicePort double replaying a queue of multimodal responses."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._queue: deque[LLMResponse] = deque(responses or [])
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._queue:
            return self._queue.popleft()
        raise AssertionError("unexpected LLM call")

    def classification(
        self, label: str, confidence: float, analysis: Mapping[str, object]
    ) -> None:
        self._queue.append(
            LLMResponse(
                text=json.dumps(
                    {"label": label, "confidence": confidence, "analysis": analysis}
                ),
                model_id="fake-model",
            )
        )

    def answer(self, text: str) -> None:
        self._queue.append(LLMResponse(text=text, model_id="fake-model"))


@dataclass
class MCPHarness:
    """Registry double that records every tool invocation."""

    registry: InMemoryMCPServer = field(default_factory=InMemoryMCPServer)
    calls: dict[str, list[Mapping[str, Any]]] = field(default_factory=dict)

    def register(self, agent_tool: AgentTool, handler: Any | None = None) -> None:
        async def capture(arguments: Mapping[str, Any]) -> MCPResponse:
            self.calls.setdefault(agent_tool.name, []).append(arguments)
            if handler is not None:
                return await handler(arguments)
            return MCPResponse(
                content=(
                    MCPContentItem(
                        kind="text", data=f"handled: {arguments.get('utterance')}"
                    ),
                ),
            )

        self.registry.register_agent_tool(agent_tool, capture)

    def last_arguments(self, tool_name: str) -> Mapping[str, Any]:
        return self.calls[tool_name][-1]


@pytest.fixture
def harness() -> MCPHarness:
    book = MCPHarness()
    for agent_tool in AGENTIC_TOOL_CATALOG:
        book.register(agent_tool)
    return book


@pytest.fixture
def image_attachment() -> MultimodalAttachment:
    return MultimodalAttachment(
        kind=Modality.IMAGE, mime_type="image/png", data=b"\x89PNG\r\n\x1a\n"
    )


@pytest.fixture
def pdf_attachment() -> MultimodalAttachment:
    return MultimodalAttachment(
        kind=Modality.DOCUMENT, mime_type="application/pdf", data=b"%PDF-1.4"
    )


async def test_image_analysis_classifies_and_invokes_vision_tool(
    harness: MCPHarness, image_attachment: MultimodalAttachment
) -> None:
    llm = FakeMultimodalLLM()
    llm.classification(
        "analyze_image_context",
        0.94,
        {"description": "a beach at sunset", "objects": ["sun", "sea"]},
    )
    use_case = ProcessMultimodalIntentUseCase(
        llm_service=llm, mcp_service=harness.registry
    )

    result = await use_case.execute(
        ProcessMultimodalIntentRequest(
            utterance="What can you see in this image?", attachments=(image_attachment,)
        )
    )

    assert len(llm.calls) == 1
    assert result.label == "analyze_image_context"
    assert result.confidence == pytest.approx(0.94)
    assert result.analysis == {
        "description": "a beach at sunset",
        "objects": ["sun", "sea"],
    }
    assert len(result.tool_outcomes) == 1
    assert result.tool_outcomes[0].tool_name == "analyze_image_context"
    assert result.tool_outcomes[0].success is True
    assert llm.calls[0].attachments[0].kind is Modality.IMAGE


async def test_document_summarization_routes_with_attachment_serialization(
    harness: MCPHarness, pdf_attachment: MultimodalAttachment
) -> None:
    llm = FakeMultimodalLLM()
    llm.classification("summarize_document", 0.91, {"topics": ["budget"]})
    use_case = ProcessMultimodalIntentUseCase(
        llm_service=llm, mcp_service=harness.registry
    )

    result = await use_case.execute(
        ProcessMultimodalIntentRequest(
            utterance="Summarize this PDF", attachments=(pdf_attachment,)
        )
    )

    assert result.label == "summarize_document"
    assert result.tool_outcomes[0].tool_name == "summarize_document"
    arguments = harness.last_arguments("summarize_document")
    assert arguments["attachment"]["mimeType"] == "application/pdf"
    assert base64.b64decode(arguments["attachment"]["dataBase64"]) == b"%PDF-1.4"


async def test_schedule_reminder_from_hint_label_skips_classification(
    harness: MCPHarness,
) -> None:
    llm = FakeMultimodalLLM()
    use_case = ProcessMultimodalIntentUseCase(
        llm_service=llm, mcp_service=harness.registry
    )

    result = await use_case.execute(
        ProcessMultimodalIntentRequest(
            utterance="Remind me to water the plants", hint_label="schedule_reminder"
        )
    )

    assert llm.calls == []
    assert result.label == "schedule_reminder"
    assert result.analysis is None
    assert len(result.tool_outcomes) == 1
    assert result.tool_outcomes[0].success is True
    arguments = harness.last_arguments("schedule_reminder")
    assert arguments["title"] == "schedule_reminder"
    assert "dueAt" in arguments


async def test_no_matching_tool_falls_back_to_llm_answer(harness: MCPHarness) -> None:
    llm = FakeMultimodalLLM()
    llm.classification("storytelling", 0.8, {"tone": "funny"})
    llm.answer("Once upon a time...")
    use_case = ProcessMultimodalIntentUseCase(
        llm_service=llm, mcp_service=harness.registry
    )

    result = await use_case.execute(
        ProcessMultimodalIntentRequest(utterance="Tell me a story")
    )

    assert len(llm.calls) == 2
    assert result.label == "storytelling"
    assert result.analysis == {"tone": "funny"}
    assert result.tool_outcomes == ()
    assert result.response_text.startswith("Once upon a time")


async def test_missing_required_arguments_fall_back_to_llm() -> None:
    device_tool = AgentTool(
        name="toggle_device",
        description="Toggle a smart-device powered state.",
        category=ToolCategory.PRODUCTIVITY,
        input_schema={
            "type": "object",
            "required": ["deviceId"],
            "properties": {"deviceId": {"type": "string"}},
        },
    )
    harness = MCPHarness()
    harness.register(device_tool)
    llm = FakeMultimodalLLM()
    llm.answer("I cannot switch the device without its id.")
    use_case = ProcessMultimodalIntentUseCase(
        llm_service=llm, mcp_service=harness.registry, agentic_catalog=(device_tool,)
    )

    result = await use_case.execute(
        ProcessMultimodalIntentRequest(
            utterance="Turn on the lamp", hint_label="toggle_device"
        )
    )

    assert len(llm.calls) == 1
    assert result.tool_outcomes == ()
    assert "missing arguments deviceId" in result.response_text


async def test_dto_derives_modalities_from_attachments(
    pdf_attachment: MultimodalAttachment,
) -> None:
    request = ProcessMultimodalIntentRequest(
        utterance="Read this", attachments=(pdf_attachment,)
    )
    assert Modality.DOCUMENT in request.modalities
    assert Modality.TEXT in request.modalities


@pytest.mark.parametrize(
    ("raw", "expected_label", "expected_analysis"),
    [
        (
            '{"label": "analyze_image_context", "confidence": 0.9, '
            '"analysis": {"a": 1}}',
            "analyze_image_context",
            {"a": 1},
        ),
        (
            '{"label": "schedule_reminder", "confidence": 0.8}',
            "schedule_reminder",
            None,
        ),
        ("garbage text", "garbage-text", None),
    ],
)
def test_parse_multimodal_classification(
    raw: str, expected_label: str, expected_analysis: Mapping[str, object] | None
) -> None:
    parsed = parse_multimodal_classification(raw)
    assert parsed.label == expected_label
    assert 0.0 <= parsed.confidence <= 1.0
    assert parsed.analysis == expected_analysis
