"""Default MCP tool resolvers wiring the domain agentic catalog.

Each resolver is an ``MCPServerPort`` tool handler that executes the business
logic behind a catalog tool. Media-aware resolvers (image analysis, document
summarization) delegate reasoning to any ``LLMServicePort``, so the same
infrastructure adapter serves both the tool registry and the multimodal flow.
"""

from __future__ import annotations

import base64
import re
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

from src.domain.models.intent import Modality
from src.domain.models.tools import AGENTIC_TOOL_CATALOG, MultimodalAttachment
from src.domain.ports.output.llm_port import LLMRequest, LLMServicePort
from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import (
    InMemoryMCPServer,
    ToolHandler,
)

if TYPE_CHECKING:
    from src.infrastructure.adapters.iot.vivotek_adapter import (
        CameraFrame,
        CameraFrameSource,
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

_AMBIENT_PROMPT = (
    "You are the Ambient Awareness module of a proactive care ecosystem for "
    "Alexa+. Analyze the given home snapshot looking for: elder falls or "
    "immobility, unattended pets, smoke or fire, intrusions and security "
    "anomalies. Answer with (1) a short narrative of what is happening, "
    "(2) a risk assessment in LOW/MEDIUM/HIGH/CRITICAL, and (3) a concrete "
    "recommended action for Alexa+."
)

_REMINDER_TOOL_NAME = "schedule_reminder"
_AMBIENT_TOOL_NAME = "analyze_ambient_stream"

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
class AmbientVerdict:
    """Deterministic safety-gate verdict computed without any LLM."""

    risk_level: str
    signals: tuple[str, ...]
    recommendation: str


_CRITICAL_RULES: tuple[tuple[str, str], ...] = (
    ("fall", "possible fall"),
    ("fell", "possible fall"),
    ("collapse", "collapse"),
    ("collapsed", "collapse"),
    ("lying on the floor", "person on the floor"),
    ("not moving", "immobility"),
    ("immobile", "immobility"),
    ("unconscious", "unconscious person"),
    ("does not respond", "person not responding"),
    ("smoke", "smoke indicators"),
    ("fire", "fire indicators"),
    ("flame", "flames"),
    ("burning", "burning"),
)
_HIGH_RULES: tuple[tuple[str, str], ...] = (
    ("intrusion", "intrusion"),
    ("intruder", "intruder"),
    ("stranger", "unknown person"),
    ("unknown person", "unknown person"),
    ("break-in", "forced entry"),
    ("forced entry", "forced entry"),
)
_MEDIUM_RULES: tuple[tuple[str, str], ...] = (
    ("unattended pet", "unattended pet"),
    ("whining", "pet distress"),
    ("pet", "pet condition"),
    ("dog", "dog condition"),
    ("cat", "cat condition"),
)

_RISK_RECOMMENDATIONS: dict[str, str] = {
    "CRITICAL": (
        "Contact emergency services immediately and open a voice escalation "
        "channel to a caregiver."
    ),
    "HIGH": ("Alert the household and capture additional context before acting."),
    "MEDIUM": "Schedule a follow-up check within 15 minutes.",
    "LOW": "No immediate action required; keep monitoring the snapshot stream.",
}

_DETECTION_TERMS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    (
        "FALL DETECTED",
        (
            "fallen",
            "fell",
            "falling",
            "immobile",
            "on the floor",
            "down on the floor",
        ),
        0.93,
    ),
    ("SMOKE", ("smoke", "smokey"), 0.95),
    ("FIRE", ("fire", "flame", "flaming", "burning"), 0.96),
    (
        "PERSON",
        (
            "person",
            "human",
            "someone",
            "elderly",
            "elder",
            "man",
            "woman",
            "grandma",
            "grandpa",
        ),
        0.88,
    ),
    ("PET", ("pet", "dog", "cat", "animal"), 0.90),
    ("PACKAGE", ("package", "parcel", "box"), 0.80),
    ("LAPTOP", ("laptop", "computer"), 0.75),
    (
        "INTRUDER",
        ("intruder", "stranger", "intrusion", "unknown person", "break-in"),
        0.90,
    ),
)


def extract_detections(text: str) -> tuple[dict[str, object], ...]:
    """Derive predicted detections from the ambient analysis text."""
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    detections = []
    for label, terms, confidence in _DETECTION_TERMS:
        if any(
            term in tokens if " " not in term else term in normalized for term in terms
        ):
            detections.append({"label": label, "confidence": confidence})
    return tuple(detections)


def scan_ambient_signals(text: str) -> AmbientVerdict:
    """Deterministically grade a snapshot against the safety rule base."""
    normalized = text.lower()
    for risk, rules in (
        ("CRITICAL", _CRITICAL_RULES),
        ("HIGH", _HIGH_RULES),
        ("MEDIUM", _MEDIUM_RULES),
    ):
        signals = tuple(label for keyword, label in rules if keyword in normalized)
        if signals:
            return AmbientVerdict(
                risk_level=risk,
                signals=signals,
                recommendation=_RISK_RECOMMENDATIONS[risk],
            )
    return AmbientVerdict(
        risk_level="LOW",
        signals=(),
        recommendation=_RISK_RECOMMENDATIONS["LOW"],
    )


def build_ambient_resolver(
    llm_service: LLMServicePort,
    camera: CameraFrameSource | None = None,
) -> ToolHandler:
    """Return the Ambient Awareness resolver for continuous home monitoring.

    A deterministic safety gate always grades the snapshot first; the LLM
    (primary or fallback) then provides the narrative. Critical signals are
    therefore reported even when the remote model is unavailable. When a
    camera frame source is supplied and no explicit media attachment is given,
    the latest live frame is attached automatically so Bedrock can ground its
    analysis on the current view.
    """

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        observation = str(arguments.get("observation") or "").strip()
        if not observation:
            return _error_response("the 'observation' argument is required")
        location = str(arguments.get("location") or "home").strip()
        timestamp = str(
            arguments.get("timestamp") or datetime.now(timezone.utc).isoformat()
        )
        verdict = scan_ambient_signals(f"{location} {observation}")
        grounding = (
            f"- location: {location}\n"
            f"- timestamp: {timestamp}\n"
            f"- observation: {observation}"
        )
        camera_frame = await _auto_attach_frame(camera, arguments.get("attachment"))
        request = _ambient_llm_request(
            grounding, arguments.get("attachment"), camera_frame
        )
        if request is None:
            return _error_response(
                "the attachment 'dataBase64' value is not valid base64"
            )
        response = await llm_service.generate(request)
        report = (
            "AMBIENT AWARENESS REPORT\n"
            f"- location: {location}\n"
            f"- timestamp: {timestamp}\n"
            f"- observation: {observation}\n"
            f"- safety gate risk: {verdict.risk_level}\n"
            f"- safety signals: {', '.join(verdict.signals) or 'none detected'}\n"
            f"- safety gate recommendation: {verdict.recommendation}\n"
            f"- model analysis: {response.text}"
        )
        detections = extract_detections(report)
        if detections:
            labels = ", ".join(
                f"{item['label']} [{item['confidence']:.2f}]" for item in detections
            )
            report = f"{report}\n- predicted detections: {labels}"
        if camera is not None:
            source = camera_frame.source if camera_frame is not None else "live"
            camera.record_detections([dict(item) for item in detections], source)
        return MCPResponse(content=(MCPContentItem(kind="text", data=report),))

    return resolve


async def _auto_attach_frame(
    camera: CameraFrameSource | None, raw_attachment: object
) -> CameraFrame | None:
    """Fetch the latest camera frame when no explicit attachment is provided.

    Only live frames are used as multimodal grounding so the model is never
    fed a synthetic fallback frame.
    """
    if camera is None or isinstance(raw_attachment, dict):
        return None
    frame = await camera.get_frame()
    if frame is None or frame.source != "live":
        return None
    return frame


def _ambient_llm_request(
    grounding: str,
    raw_attachment: object,
    camera_frame: CameraFrame | None = None,
) -> LLMRequest | None:
    attachments: list[MultimodalAttachment] = []
    if isinstance(raw_attachment, dict):
        try:
            data = base64.b64decode(str(raw_attachment.get("dataBase64", "")))
        except Base64Error:
            return None
        if not data:
            return None
        mime_type = str(raw_attachment.get("mimeType", "application/octet-stream"))
        attachments.append(
            MultimodalAttachment(
                kind=modality_for_mime(mime_type),
                mime_type=mime_type,
                data=data,
            )
        )
    elif camera_frame is not None:
        mime_type = camera_frame.content_type or "image/jpeg"
        attachments.append(
            MultimodalAttachment(
                kind=modality_for_mime(mime_type),
                mime_type=mime_type,
                data=camera_frame.data,
            )
        )
    return LLMRequest(
        system_prompt=_AMBIENT_PROMPT,
        user_prompt=grounding,
        temperature=0.2,
        max_tokens=512,
        attachments=tuple(attachments),
    )


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


def build_agentic_tool_registry(
    llm_service: LLMServicePort, camera: CameraFrameSource | None = None
) -> InMemoryMCPServer:
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
        elif agent_tool.name == _AMBIENT_TOOL_NAME:
            registry.register_agent_tool(
                agent_tool, build_ambient_resolver(llm_service, camera)
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
