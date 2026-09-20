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

AGENTIC_TOOL_CATALOG: tuple[AgentTool, ...] = (
    ANALYZE_IMAGE_CONTEXT,
    SUMMARIZE_DOCUMENT,
    SCHEDULE_REMINDER,
)
