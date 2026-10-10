"""Domain catalog of agentic (multimodal & productivity) MCP tools.

This module belongs to the pure domain hexagon: only the standard library is
used and no framework, SDK or IO is touched. It defines the business-facing
descriptions of the tools the ecosystem can expose to Alexa+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from src.domain.models.intent import Modality


class ToolCategory(Enum):
    """Business category of an agentic tool."""

    ANALYSIS = "analysis"
    PRODUCTIVITY = "productivity"
    KNOWLEDGE = "knowledge"
    COMMUNICATION = "communication"
    SAFETY = "safety"


@dataclass(frozen=True, slots=True)
class MultimodalAttachment:
    """Immutable media payload attached to an intent or a generation request."""

    kind: Modality
    mime_type: str
    data: bytes
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.mime_type.strip():
            raise ValueError("mime_type must not be empty")
        if not isinstance(self.data, bytes):
            raise TypeError("attachment data must be bytes")


@dataclass(frozen=True, slots=True)
class AgentTool:
    """Domain descriptor of an MCP tool exposed by the ecosystem.

    The JSON-Schema-like ``input_schema`` is carried as opaque data; the only
    validation behaviour needed by the domain is computing/checking the
    presence of the required fields it declares.
    """

    name: str
    description: str
    category: ToolCategory
    input_schema: Mapping[str, object]
    supported_modalities: frozenset[Modality] = field(
        default_factory=lambda: frozenset({Modality.TEXT})
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if "required" in self.input_schema:
            required = self.input_schema["required"]
            if not isinstance(required, list) or not all(
                isinstance(item, str) for item in required
            ):
                raise ValueError(
                    "input_schema 'required' must be a list of field names"
                )

    @property
    def required_fields(self) -> frozenset[str]:
        required = self.input_schema.get("required", [])
        fields = required if isinstance(required, list) else []
        return frozenset(str(item) for item in fields)

    def validate_arguments(self, arguments: Mapping[str, object]) -> tuple[str, ...]:
        """Return the required argument names missing from the given mapping."""
        missing = self.required_fields.difference(arguments.keys())
        return tuple(sorted(missing))


def _schema(
    required: list[str], properties: Mapping[str, object]
) -> Mapping[str, object]:
    return {
        "type": "object",
        "required": required,
        "properties": dict(properties),
    }


ANALYZE_IMAGE_CONTEXT = AgentTool(
    name="analyze_image_context",
    description="Analyze an image and produce a detailed textual context description.",
    category=ToolCategory.ANALYSIS,
    input_schema=_schema(
        required=["attachment", "instruction"],
        properties={
            "attachment": {
                "type": "object",
                "description": "Media payload: {mimeType, dataBase64}.",
            },
            "instruction": {
                "type": "string",
                "description": "Natural-language instruction for the analysis.",
            },
        },
    ),
    supported_modalities=frozenset({Modality.IMAGE, Modality.VIDEO}),
)

SUMMARIZE_DOCUMENT = AgentTool(
    name="summarize_document",
    description=(
        "Summarize a document or long text faithfully, extracting key facts "
        "and actions."
    ),
    category=ToolCategory.KNOWLEDGE,
    input_schema=_schema(
        required=["attachment"],
        properties={
            "attachment": {
                "type": "object",
                "description": "Document payload: {mimeType, dataBase64}.",
            },
            "instruction": {
                "type": "string",
                "description": "Optional summarization focus.",
            },
        },
    ),
    supported_modalities=frozenset({Modality.DOCUMENT, Modality.TEXT, Modality.IMAGE}),
)

SCHEDULE_REMINDER = AgentTool(
    name="schedule_reminder",
    description="Schedule a time-based reminder for the user.",
    category=ToolCategory.PRODUCTIVITY,
    input_schema=_schema(
        required=["title", "dueAt"],
        properties={
            "title": {"type": "string", "description": "Reminder title."},
            "dueAt": {"type": "string", "description": "ISO-8601 due datetime."},
            "note": {"type": "string", "description": "Optional reminder note."},
        },
    ),
    supported_modalities=frozenset({Modality.TEXT}),
)

ANALYZE_AMBIENT_STREAM = AgentTool(
    name="analyze_ambient_stream",
    description=(
        "Continuously monitor a home or environment snapshot (elder fall "
        "detection, unattended pets, smoke/fire, intrusions or security "
        "anomalies) and return a risk-graded ambient awareness report."
    ),
    category=ToolCategory.SAFETY,
    input_schema=_schema(
        required=["observation"],
        properties={
            "location": {
                "type": "string",
                "description": "Physical zone being observed, e.g. living room.",
            },
            "timestamp": {
                "type": "string",
                "description": "ISO-8601 timestamp of the snapshot.",
            },
            "observation": {
                "type": "string",
                "description": (
                    "Natural-language or sensor description of the current state."
                ),
            },
            "attachment": {
                "type": "object",
                "description": "Optional media payload: {mimeType, dataBase64}.",
            },
        },
    ),
    supported_modalities=frozenset(
        {Modality.TEXT, Modality.IMAGE, Modality.VIDEO, Modality.AUDIO}
    ),
)

MEMORY_LAST_SEEN = AgentTool(
    name="memory_last_seen",
    description=(
        "Answer historical questions like 'when was the gate last seen open?' "
        "from local vectorial memory only, never using an LLM."
    ),
    category=ToolCategory.KNOWLEDGE,
    input_schema=_schema(
        required=["label"],
        properties={
            "label": {
                "type": "string",
                "description": (
                    "Canonical label, e.g. PERSON, PERSON_ELDERLY, PET, "
                    "GATE_OPEN, DOOR_OPEN."
                ),
            },
            "location": {
                "type": "string",
                "description": "Optional physical zone filter.",
            },
        },
    ),
)

MEMORY_SEARCH = AgentTool(
    name="memory_search",
    description=(
        "Search local vectorial memory for past observations matching a "
        "natural-language query. Pure structured retrieval, no LLM involved."
    ),
    category=ToolCategory.KNOWLEDGE,
    input_schema=_schema(
        required=["query"],
        properties={
            "query": {
                "type": "string",
                "description": "Natural-language or label-based query.",
            },
            "limit": {
                "type": "number",
                "description": "Maximum results to return (default 5).",
            },
            "min_score": {
                "type": "number",
                "description": "Minimum cosine score threshold (default 0.0).",
            },
            "location": {
                "type": "string",
                "description": "Optional physical zone filter.",
            },
        },
    ),
)

MEMORY_SUMMARY = AgentTool(
    name="memory_summary",
    description=(
        "Produce a short recap in Spanish of what home observations were "
        "persisted over the recent period, backed exclusively by local memory."
    ),
    category=ToolCategory.KNOWLEDGE,
    input_schema=_schema(
        required=[],
        properties={
            "hours": {
                "type": "number",
                "description": "Lookback window in hours (default 24).",
            },
            "location": {
                "type": "string",
                "description": "Optional physical zone filter.",
            },
        },
    ),
)

MEMORY_CONVERSE = AgentTool(
    name="memory_converse",
    description=(
        "Conversational memory endpoint: interpret a natural-language Spanish "
        "question about the home's history and answer it from local memory "
        "(last seen, search, summary, top/high/critical events, or current "
        "state plus historical context). Deterministic routing, no LLM."
    ),
    category=ToolCategory.KNOWLEDGE,
    input_schema=_schema(
        required=["query"],
        properties={
            "query": {
                "type": "string",
                "description": "Natural-language question in Spanish.",
            }
        },
    ),
)

AGENTIC_TOOL_CATALOG: tuple[AgentTool, ...] = (
    ANALYZE_IMAGE_CONTEXT,
    SUMMARIZE_DOCUMENT,
    SCHEDULE_REMINDER,
    ANALYZE_AMBIENT_STREAM,
    MEMORY_LAST_SEEN,
    MEMORY_SEARCH,
    MEMORY_SUMMARY,
    MEMORY_CONVERSE,
)
