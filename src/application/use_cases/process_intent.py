"""Primary use case: orchestrate the processing of a raw user intent.

The use case depends exclusively on domain ports, domain models and its own
DTOs. It knows nothing about FastAPI, boto3 or the MCP SDK.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from uuid import uuid4

from src.application.dtos.intent_dto import (
    ProcessIntentRequest,
    ProcessIntentResult,
    ToolCallOutcome,
)
from src.domain.models.intent import (
    IntentConfidence,
    IntentStatus,
    IntentTarget,
    UserIntent,
)
from src.domain.ports.output.llm_port import LLMRequest, LLMServicePort
from src.domain.ports.output.mcp_port import MCPServerPort, MCPTool

_RECOGNITION_SYSTEM_PROMPT = (
    "You are the intent router of a multimodal agentic ecosystem for Alexa+. "
    "Classify the user utterance into a short, lowercase, hyphenated intent "
    "label. Answer with exactly one JSON object of the form "
    '{{"label": string, "confidence": number}} and nothing else.\n'
    "MCP tools currently available:\n{available_tools}"
)

_ANSWER_SYSTEM_PROMPT = (
    "You are the conversational core of a multimodal agentic ecosystem for "
    "Alexa+. The user intent has been classified as '{label}'. Answer the "
    "user's request naturally and succinctly. If you have no factual answer, "
    "say so honestly."
)

_CLASSIFICATION_FRAGMENT = re.compile(
    r'"label"\s*:\s*"([^"]+)"[^\n]*"confidence"\s*:\s*([0-9.]+)',
    re.IGNORECASE,
)


def _parse_classification(raw_text: str) -> tuple[str, float]:
    """Extract a (label, confidence) pair from model output.

    Prefers a complete JSON document but degrades gracefully to regex
    scanning, then to a normalized fallback label.
    """
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end > start:
        try:
            payload = json.loads(raw_text[start : end + 1])
            label = str(payload["label"]).strip().lower()
            confidence = float(payload["confidence"])
            return label, confidence
        except (KeyError, TypeError, ValueError):
            pass
    match = _CLASSIFICATION_FRAGMENT.search(raw_text)
    if match is not None:
        return match.group(1).strip().lower(), float(match.group(2))
    fallback = raw_text.strip().lower().replace(" ", "-")[:64]
    return (fallback or "unclassified"), 0.5


def _tokenize(label: str) -> Sequence[str]:
    """Split an intent label into tokens usable for MCP tool matching."""
    tokens = [token for token in re.split(r"[_\-.\s]+", label) if token]
    return tuple({label, *tokens})


class ProcessIntentUseCase:
    """Single entry point for transforming raw utterances into responses.

    Pipeline:
        1. Build the UserIntent aggregate from the input DTO.
        2. Classify the intent through the LLM port unless a label is given.
        3. Select and invoke a matching MCP tool, or answer via the LLM.
    """

    def __init__(self, llm_service: LLMServicePort, mcp_service: MCPServerPort) -> None:
        self._llm_service = llm_service
        self._mcp_service = mcp_service

    async def execute(self, request: ProcessIntentRequest) -> ProcessIntentResult:
        intent = self._build_intent(request)
        if intent.status is IntentStatus.UNCLASSIFIED:
            intent = await self._classify_intent(intent)
        selected_tool = await self._select_tool(intent)
        if selected_tool is None:
            return await self._complete_via_llm(intent, request)
        intent = intent.with_target(
            IntentTarget(
                tool_name=selected_tool.name,
                arguments={
                    "utterance": intent.utterance,
                    "session_id": request.session_id or "",
                },
            )
        )
        return await self._invoke_tools(intent)

    def _build_intent(self, request: ProcessIntentRequest) -> UserIntent:
        label = request.hint_label.strip().lower() if request.hint_label else None
        return UserIntent(
            intent_id=uuid4(),
            utterance=request.utterance.strip(),
            label=label,
            confidence=IntentConfidence(0.5),
            targets=(),
            modalities=request.modalities,
            status=(
                IntentStatus.CLASSIFIED
                if label is not None
                else IntentStatus.UNCLASSIFIED
            ),
        )

    async def _classify_intent(self, intent: UserIntent) -> UserIntent:
        tools = await self._mcp_service.list_tools()
        catalog = (
            "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
            or "(none)"
        )
        llm_request = LLMRequest(
            system_prompt=_RECOGNITION_SYSTEM_PROMPT.format(available_tools=catalog),
            user_prompt=intent.utterance,
            temperature=0.0,
            max_tokens=128,
        )
        raw = (await self._llm_service.generate(llm_request)).text
        label, confidence = _parse_classification(raw)
        return intent.classify(label, IntentConfidence(confidence))

    async def _select_tool(self, intent: UserIntent) -> MCPTool | None:
        tokens = _tokenize(intent.label or "")
        for tool in await self._mcp_service.list_tools():
            haystack = f"{tool.name} {tool.description}".lower()
            if any(token and token in haystack for token in tokens):
                return tool
        return None

    async def _invoke_tools(self, intent: UserIntent) -> ProcessIntentResult:
        outcomes: list[ToolCallOutcome] = []
        for target in intent.targets:
            mcp_response = await self._mcp_service.call_tool(
                target.tool_name, target.arguments
            )
            summary = (
                "\n".join(
                    item.data for item in mcp_response.content if item.kind == "text"
                )
                or f"Executed {target.tool_name}"
            )
            outcomes.append(
                ToolCallOutcome(
                    tool_name=target.tool_name,
                    success=not mcp_response.is_error,
                    summary=summary,
                )
            )
        return ProcessIntentResult(
            request_id=intent.intent_id,
            label=intent.label or "unclassified",
            confidence=intent.confidence.value,
            response_text=(
                outcomes[-1].summary if outcomes else "No tools were executed."
            ),
            tool_outcomes=tuple(outcomes),
        )

    async def _complete_via_llm(
        self, intent: UserIntent, request: ProcessIntentRequest
    ) -> ProcessIntentResult:
        llm_request = LLMRequest(
            system_prompt=_ANSWER_SYSTEM_PROMPT.format(label=intent.label),
            user_prompt=intent.utterance,
            temperature=0.4,
            max_tokens=512,
        )
        response = await self._llm_service.generate(llm_request)
        return ProcessIntentResult(
            request_id=intent.intent_id,
            label=intent.label or "unclassified",
            confidence=intent.confidence.value,
            response_text=response.text,
            tool_outcomes=(),
        )
