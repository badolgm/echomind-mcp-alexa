"""Application-level DTOs exchanged with the ProcessIntentUseCase."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from src.domain.models.intent import Modality


@dataclass(frozen=True, slots=True)
class ProcessIntentRequest:
    """Input DTO carrying a raw user interaction into the use case."""

    utterance: str
    session_id: str | None = None
    context: Mapping[str, str] = field(default_factory=dict)
    modalities: frozenset[Modality] = field(
        default_factory=lambda: frozenset({Modality.TEXT})
    )
    hint_label: str | None = None

    def __post_init__(self) -> None:
        if not self.utterance.strip():
            raise ValueError("utterance must not be empty")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    """Output DTO describing the result of a single MCP tool invocation."""

    tool_name: str
    success: bool
    summary: str


@dataclass(frozen=True, slots=True)
class ProcessIntentResult:
    """Output DTO returned by the use case after processing an intent."""

    request_id: UUID
    label: str
    confidence: float
    response_text: str
    tool_outcomes: tuple[ToolCallOutcome, ...] = ()
