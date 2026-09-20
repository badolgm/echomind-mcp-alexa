"""Multimodal intent processing use case.

Coordinates the full multimodal pipeline: media-aware LLM classification,
selection of an agentic MCP tool from the domain catalog, and invocation of
that tool through the MCP output port.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.application.dtos.intent_dto import (
    ProcessMultimodalIntentRequest,
    ProcessMultimodalIntentResult,
    ToolCallOutcome,
)
from src.application.use_cases.process_intent import (
    extract_json_object,
    parse_classification,
    tokenize_label,
)
from src.domain.models.intent import (
    IntentConfidence,
    IntentStatus,
    IntentTarget,
    UserIntent,
)
from src.domain.models.tools import (
    AGENTIC_TOOL_CATALOG,
    AgentTool,
    MultimodalAttachment,
    ToolCategory,
)
from src.domain.ports.output.llm_port import LLMRequest, LLMServicePort
from src.domain.ports.output.mcp_port import MCPServerPort, MCPResponse

_MULTIMODAL_SYSTEM_PROMPT = (
    "You are the multimodal intent router of an agentic ecosystem for Alexa+. "
    "The user message may include media (image, document, audio, video). "
    "Analyze the media together with the text. Classify the user intent and "
    "return exactly one JSON object with no extra commentary of the form "
    '{{"label": string, "confidence": number, "analysis": object}}.\n'
    "Use one of these tool labels whenever it fits the request:\n"
    "{available_tools}"
)

_MULTIMODAL_ANSWER_PROMPT = (
    "You are the conversational core of a multimodal agentic ecosystem for "
    "Alexa+. The user intent has been classified as '{label}'. Answer the "
    "user's request naturally and succinctly, using the media you saw."
)


@dataclass(frozen=True, slots=True)
class MultimodalClassification:
    """Parsed result of a multimodal intent classification."""

    label: str
    confidence: float
    analysis: Mapping[str, object] | None = None


def parse_multimodal_classification(raw_text: str) -> MultimodalClassification:
    """Extract a multimodal classification (label, confidence, analysis)."""
    payload = extract_json_object(raw_text)
    if payload is not None and "label" in payload:
        try:
            label = str(payload["label"]).strip().lower()
            confidence = float(payload["confidence"])
            analysis = payload.get("analysis")
            normalized = analysis if isinstance(analysis, dict) else None
            return MultimodalClassification(
                label=label, confidence=confidence, analysis=normalized
            )
        except (TypeError, ValueError):
            pass
    label, confidence = parse_classification(raw_text)
    return MultimodalClassification(label=label, confidence=confidence)


def _default_due_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


class ProcessMultimodalIntentUseCase:
    """Entry point for multimodal user interactions in the ecosystem.

    Pipeline:
        1. Build the UserIntent aggregate from the input DTO.
        2. Classify intent + media through the LLM port unless a label is given.
        3. Select an agentic tool from the catalog and invoke it via the MCP
           port; fall back to a plain LLM answer when no tool fits.
    """

    def __init__(
        self,
        llm_service: LLMServicePort,
        mcp_service: MCPServerPort,
        agentic_catalog: tuple[AgentTool, ...] = AGENTIC_TOOL_CATALOG,
    ) -> None:
        self._llm_service = llm_service
        self._mcp_service = mcp_service
        self._catalog = agentic_catalog

    async def execute(
        self, request: ProcessMultimodalIntentRequest
    ) -> ProcessMultimodalIntentResult:
        intent = self._build_intent(request)
        classification: MultimodalClassification | None = None
        if intent.status is IntentStatus.UNCLASSIFIED:
            classification = await self._classify(intent, request.attachments)
            intent = intent.classify(
                classification.label, IntentConfidence(classification.confidence)
            )

        agent_tool = await self._select_tool(intent)
        if agent_tool is None:
            text = await self._complete(intent, request, classification)
            return self._build_result(intent, text, None, None, classification)

        arguments = self._build_tool_arguments(
            intent, request, agent_tool, classification
        )
        missing = agent_tool.validate_arguments(arguments)
        if missing:
            note = (
                "Request could not be fulfilled: missing arguments "
                f"{', '.join(missing)}."
            )
            text = await self._complete(intent, request, classification, note=note)
            return self._build_result(intent, text, None, None, classification)

        intent = intent.with_target(
            IntentTarget(tool_name=agent_tool.name, arguments=arguments)
        )
        mcp_response = await self._mcp_service.call_tool(agent_tool.name, arguments)
        return self._build_result(
            intent,
            self._summary(mcp_response),
            agent_tool.name,
            mcp_response,
            classification,
        )

    def _build_intent(self, request: ProcessMultimodalIntentRequest) -> UserIntent:
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

    async def _classify(
        self,
        intent: UserIntent,
        attachments: tuple[MultimodalAttachment, ...],
    ) -> MultimodalClassification:
        catalog = (
            "\n".join(f"- {tool.name}: {tool.description}" for tool in self._catalog)
            or "(none)"
        )
        llm_request = LLMRequest(
            system_prompt=_MULTIMODAL_SYSTEM_PROMPT.format(available_tools=catalog),
            user_prompt=intent.utterance,
            temperature=0.0,
            max_tokens=256,
            attachments=attachments,
        )
        raw = (await self._llm_service.generate(llm_request)).text
        return parse_multimodal_classification(raw)

    async def _select_tool(self, intent: UserIntent) -> AgentTool | None:
        available = {tool.name for tool in await self._mcp_service.list_tools()}
        tokens = tokenize_label(intent.label or "")
        for agent_tool in self._catalog:
            if agent_tool.name not in available:
                continue
            haystack = f"{agent_tool.name} {agent_tool.description}".lower()
            if intent.label == agent_tool.name or any(
                token and token in haystack for token in tokens
            ):
                return agent_tool
        return None

    def _build_tool_arguments(
        self,
        intent: UserIntent,
        request: ProcessMultimodalIntentRequest,
        agent_tool: AgentTool,
        classification: MultimodalClassification | None,
    ) -> dict[str, object]:
        base: dict[str, object] = {
            "utterance": intent.utterance,
            "session_id": request.session_id or "",
        }
        if agent_tool.category in {ToolCategory.ANALYSIS, ToolCategory.KNOWLEDGE}:
            attachment = self._select_attachment(request.attachments, agent_tool)
            if attachment is not None:
                base.update(
                    {
                        "attachment": {
                            "mimeType": attachment.mime_type,
                            "dataBase64": base64.b64encode(attachment.data).decode(
                                "ascii"
                            ),
                        },
                        "instruction": request.utterance,
                    }
                )
            return base
        if agent_tool.category is ToolCategory.PRODUCTIVITY:
            metadata = classification.analysis if classification is not None else None
            metadata = metadata or {}
            due_at = metadata.get("dueAt") or metadata.get("due_at")
            base.update(
                {
                    "title": str(metadata.get("title") or intent.label),
                    "dueAt": str(due_at) if due_at else _default_due_at(),
                    "note": request.utterance,
                }
            )
            return base
        return base

    def _select_attachment(
        self,
        attachments: tuple[MultimodalAttachment, ...],
        agent_tool: AgentTool,
    ) -> MultimodalAttachment | None:
        for attachment in attachments:
            if attachment.kind in agent_tool.supported_modalities:
                return attachment
        return None

    async def _complete(
        self,
        intent: UserIntent,
        request: ProcessMultimodalIntentRequest,
        classification: MultimodalClassification | None,
        note: str | None = None,
    ) -> str:
        llm_request = LLMRequest(
            system_prompt=_MULTIMODAL_ANSWER_PROMPT.format(label=intent.label),
            user_prompt=request.utterance,
            temperature=0.3,
            max_tokens=512,
            attachments=request.attachments,
        )
        text = (await self._llm_service.generate(llm_request)).text
        return f"{text}\n{note}" if note else text

    def _summary(self, mcp_response: MCPResponse) -> str:
        return (
            "\n".join(item.data for item in mcp_response.content if item.kind == "text")
            or "Executed strategy successfully."
        )

    def _build_result(
        self,
        intent: UserIntent,
        response_text: str,
        tool_name: str | None,
        mcp_response: MCPResponse | None,
        classification: MultimodalClassification | None,
    ) -> ProcessMultimodalIntentResult:
        outcomes: tuple[ToolCallOutcome, ...] = ()
        if mcp_response is not None and tool_name is not None:
            outcomes = (
                ToolCallOutcome(
                    tool_name=tool_name,
                    success=not mcp_response.is_error,
                    summary=self._summary(mcp_response),
                ),
            )
        return ProcessMultimodalIntentResult(
            request_id=intent.intent_id,
            label=intent.label or "unclassified",
            confidence=intent.confidence.value,
            response_text=response_text,
            tool_outcomes=outcomes,
            analysis=classification.analysis if classification is not None else None,
        )
