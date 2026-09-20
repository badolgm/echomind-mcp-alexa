"""Default MCP tool resolvers wiring the domain agentic catalog.

Each resolver is an ``MCPServerPort`` tool handler that executes the business
logic behind a catalog tool. Media-aware resolvers (image analysis, document
summarization) delegate reasoning to any ``LLMServicePort``, so the same
infrastructure adapter serves both the tool registry and the multimodal flow.
"""

from __future__ import annotations

import base64
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from src.domain.models.intent import Modality
from src.domain.models.tools import AGENTIC_TOOL_CATALOG, MultimodalAttachment
from src.domain.ports.output.llm_port import LLMRequest, LLMServicePort
from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    InMemoryMCPServer,
    ToolHandler,
)

_MEDIA_PROMPTS: dict[str, str] = {
    "analyze_image_context": (
        "Describe this media in detail: objects, scene, text, and the most "
        "plausible user intent."
    ),
    "summarize_document": (
        "Summarize this document faithfully, extracting the key facts and any "
        "actionable items."
    ),
}

_REMINDER_TOOL_NAME = "schedule_reminder"

_DOCUMENT_MIME_HINTS = (
    "application/pdf",
    "application/vnd.oasis.opendocument",
    "wordprocessingml",
    "spreadsheetml",
)


def modality_for_mime(mime_type: str) -> Modality:
    """Best-effort mapping from a MIME type to a domain Modality."""
    normalized = mime_type.lower()
    if any(hint in normalized for hint in _DOCUMENT_MIME_HINTS):
        return Modality.DOCUMENT
    if normalized.startswith("image/"):
        return Modality.IMAGE
    if normalized.startswith("audio/"):
        return Modality.AUDIO
    if normalized.startswith("video/"):
        return Modality.VIDEO
    return Modality.TEXT


def build_media_resolver(
    llm_service: LLMServicePort, prompt_template: str
) -> ToolHandler:
    """Return a resolver that grounds a media analysis/summary through the LLM."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        raw_attachment = arguments.get("attachment")
        if not isinstance(raw_attachment, dict):
            return _error_response(
                "the 'attachment' argument is required and must be an object"
            )
        try:
            data = base64.b64decode(str(raw_attachment.get("dataBase64", "")))
        except Base64Error:
            return _error_response(
                "the attachment 'dataBase64' value is not valid base64"
            )
        if not data:
            return _error_response("the attachment is empty")
        mime_type = str(raw_attachment.get("mimeType", "text/plain"))
        instruction = str(arguments.get("instruction") or prompt_template)
        request = LLMRequest(
            system_prompt=prompt_template,
            user_prompt=instruction,
            temperature=0.2,
            max_tokens=512,
            attachments=(
                MultimodalAttachment(
                    kind=modality_for_mime(mime_type),
                    mime_type=mime_type,
                    data=data,
                ),
            ),
        )
        response = await llm_service.generate(request)
        return MCPResponse(content=(MCPContentItem(kind="text", data=response.text),))

    return resolve


@dataclass(frozen=True, slots=True)
class Reminder:
    """Immutable record of a scheduled reminder."""

    reminder_id: str
    title: str
    due_at: str
    note: str
    created_at: str


class ReminderBook:
    """Thread-safe in-memory store backing the schedule_reminder tool."""

    def __init__(self) -> None:
        self._reminders: list[Reminder] = []

    def add(self, *, title: str, due_at: str, note: str) -> str:
        reminder_id = str(uuid4())
        self._reminders.append(
            Reminder(
                reminder_id=reminder_id,
                title=title,
                due_at=due_at,
                note=note,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        return reminder_id

    def list(self) -> tuple[Reminder, ...]:
        return tuple(self._reminders)

    def __len__(self) -> int:
        return len(self._reminders)


def build_reminder_resolver(book: ReminderBook) -> ToolHandler:
    """Return a resolver that schedules reminders into the given store."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        title = str(arguments.get("title") or "").strip()
        due_at = str(arguments.get("dueAt") or "").strip()
        if not title or not due_at:
            return _error_response("'title' and 'dueAt' are required")
        reminder_id = book.add(
            title=title, due_at=due_at, note=str(arguments.get("note") or "").strip()
        )
        return MCPResponse(
            content=(
                MCPContentItem(
                    kind="text",
                    data=f"scheduled reminder {reminder_id}: {title} at {due_at}",
                ),
            ),
        )

    return resolve


def build_agentic_tool_registry(llm_service: LLMServicePort) -> InMemoryMCPServer:
    """Compose the default agentic tool registry for the ecosystem."""
    registry = InMemoryMCPServer()
    reminder_book = ReminderBook()
    for agent_tool in AGENTIC_TOOL_CATALOG:
        if agent_tool.name in _MEDIA_PROMPTS:
            registry.register_agent_tool(
                agent_tool,
                build_media_resolver(llm_service, _MEDIA_PROMPTS[agent_tool.name]),
            )
        elif agent_tool.name == _REMINDER_TOOL_NAME:
            registry.register_agent_tool(
                agent_tool, build_reminder_resolver(reminder_book)
            )
        else:
            registry.register_agent_tool(agent_tool, _echo_resolver)
    return registry


async def _echo_resolver(arguments: Mapping[str, Any]) -> MCPResponse:
    data = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    return MCPResponse(content=(MCPContentItem(kind="text", data=f"echo {data}"),))


def _error_response(message: str) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=message),), is_error=True
    )
