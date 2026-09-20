"""Unit tests for the ProcessIntentUseCase with mocked domain ports."""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping

import pytest

from src.application.dtos.intent_dto import ProcessIntentRequest
from src.application.use_cases.process_intent import (
    ProcessIntentUseCase,
    parse_classification,
)
from src.domain.models.intent import IntentConfidence, Modality
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.domain.ports.output.mcp_port import (
    MCPContentItem,
    MCPServerPort,
    MCPResponse,
    MCPTool,
)


class FakeLLMService(LLMServicePort):
    """In-memory double of LLMServicePort replaying a fixed response queue."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._queue: deque[LLMResponse] = deque(responses or [])
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._queue:
            return self._queue.popleft()
        return LLMResponse(
            text='{"label": "generic", "confidence": 0.5}',
            model_id="fake-model",
        )


class FakeMCPService(MCPServerPort):
    """In-memory double of MCPServerPort exposing a fixed tool set."""

    def __init__(self, tools: tuple[MCPTool, ...] = ()) -> None:
        self._tools = tools
        self.called: list[tuple[str, Mapping[str, Any]]] = []

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return self._tools

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> MCPResponse:
        self.called.append((name, arguments))
        return MCPResponse(
            content=(MCPContentItem(kind="text", data=f"{name} executed ok"),),
            is_error=False,
        )


@pytest.fixture
def alarm_tool() -> MCPTool:
    return MCPTool(
        name="alarm_set",
        description="Set a smart-home alarm for the user.",
        input_schema={"type": "object", "properties": {}},
    )


async def test_hint_label_skips_classification_and_routes_to_tool(
    alarm_tool: MCPTool,
) -> None:
    llm = FakeLLMService()
    mcp = FakeMCPService(tools=(alarm_tool,))
    use_case = ProcessIntentUseCase(llm_service=llm, mcp_service=mcp)

    result = await use_case.execute(
        ProcessIntentRequest(utterance="Set an alarm for 7am", hint_label="set_alarm")
    )

    assert llm.calls == []
    assert result.label == "set_alarm"
    assert result.confidence == pytest.approx(0.5)
    assert len(result.tool_outcomes) == 1
    assert result.tool_outcomes[0].tool_name == "alarm_set"
    assert result.tool_outcomes[0].success is True
    assert mcp.called[0][0] == "alarm_set"
    assert "utterance" in mcp.called[0][1]


async def test_classification_invokes_llm_before_route(alarm_tool: MCPTool) -> None:
    llm = FakeLLMService(
        responses=[
            LLMResponse(
                text='{"label": "set_alarm", "confidence": 0.98}',
                model_id="fake-model",
            )
        ]
    )
    mcp = FakeMCPService(tools=(alarm_tool,))
    use_case = ProcessIntentUseCase(llm_service=llm, mcp_service=mcp)

    result = await use_case.execute(ProcessIntentRequest(utterance="Wake me at seven"))

    assert len(llm.calls) == 1
    assert result.label == "set_alarm"
    assert result.confidence == pytest.approx(0.98)
    assert len(result.tool_outcomes) == 1
    assert mcp.called and mcp.called[0][0] == "alarm_set"


async def test_no_matching_tool_falls_back_to_llm_answer(alarm_tool: MCPTool) -> None:
    llm = FakeLLMService(
        responses=[
            LLMResponse(
                text='{"label": "entertainment", "confidence": 0.61}',
                model_id="fake-model",
            ),
            LLMResponse(text="Why did the developer go broke?", model_id="fake-model"),
        ]
    )
    mcp = FakeMCPService(tools=(alarm_tool,))
    use_case = ProcessIntentUseCase(llm_service=llm, mcp_service=mcp)

    result = await use_case.execute(ProcessIntentRequest(utterance="Tell me a joke"))

    assert len(llm.calls) == 2
    assert result.label == "entertainment"
    assert result.response_text.startswith("Why did the developer")
    assert result.tool_outcomes == ()


@pytest.mark.parametrize(
    ("raw", "expected_label"),
    [
        ('{"label": "set_alarm", "confidence": 0.9}', "set_alarm"),
        ('Sure! {"label": "play_music", "confidence": 0.7}', "play_music"),
        ("nothing useful here", "nothing-useful-here"),
    ],
)
def test_parse_classification_normalizes_model_output(
    raw: str, expected_label: str
) -> None:
    label, confidence = parse_classification(raw)
    assert label == expected_label
    assert 0.0 <= confidence <= 1.0


def test_domain_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        IntentConfidence(1.5)


def test_dto_rejects_blank_utterance() -> None:
    with pytest.raises(ValueError):
        ProcessIntentRequest(utterance="   ")


async def test_multimodal_modalities_are_preserved(alarm_tool: MCPTool) -> None:
    llm = FakeLLMService()
    mcp = FakeMCPService(tools=(alarm_tool,))
    use_case = ProcessIntentUseCase(llm_service=llm, mcp_service=mcp)
    modalities = frozenset({Modality.TEXT, Modality.IMAGE})

    result = await use_case.execute(
        ProcessIntentRequest(
            utterance="Set an alarm", hint_label="set_alarm", modalities=modalities
        )
    )

    assert result.tool_outcomes
    assert result.tool_outcomes[0].tool_name == "alarm_set"
