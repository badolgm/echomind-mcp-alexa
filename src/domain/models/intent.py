"""Domain model: the UserIntent aggregate root and its immutable value objects.

This module belongs to the pure domain hexagon. It must not import frameworks,
AWS SDKs, the MCP SDK, or perform any IO. Only the standard library is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class Modality(Enum):
    """Input/output modality of a user interaction with Alexa+."""

    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    HAPTIC = "haptic"


class IntentStatus(Enum):
    """Lifecycle state of a user intent as it flows through the use case."""

    UNCLASSIFIED = "unclassified"
    CLASSIFIED = "classified"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IntentConfidence:
    """Value object holding a normalized model confidence in [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"confidence must be within [0, 1], got {self.value!r}")


@dataclass(frozen=True, slots=True)
class IntentTarget:
    """Value object describing a concrete MCP tool to invoke for an intent."""

    tool_name: str
    arguments: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be empty")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class UserIntent:
    """The aggregate root representing a single user interaction.

    The intent is created, classified and optionally routed by the application
    layer through pure domain methods, yielding a new immutable instance at
    each transition.
    """

    intent_id: UUID
    utterance: str
    label: str | None
    confidence: IntentConfidence
    targets: tuple[IntentTarget, ...]
    modalities: frozenset[Modality]
    status: IntentStatus = IntentStatus.UNCLASSIFIED

    def __post_init__(self) -> None:
        if not self.utterance.strip():
            raise ValueError("utterance must not be empty")
        if self.label is not None and not _LABEL_PATTERN.match(self.label):
            raise ValueError(f"invalid intent label {self.label!r}")

    @property
    def is_classified(self) -> bool:
        return self.status in {IntentStatus.CLASSIFIED, IntentStatus.PROCESSED}

    def classify(self, label: str, confidence: IntentConfidence) -> "UserIntent":
        """Return a new intent carrying an intent classification result."""
        return UserIntent(
            intent_id=self.intent_id,
            utterance=self.utterance,
            label=label.strip().lower(),
            confidence=confidence,
            targets=self.targets,
            modalities=self.modalities,
            status=IntentStatus.CLASSIFIED,
        )

    def with_target(self, target: IntentTarget) -> "UserIntent":
        """Return a new intent with an additional routing target attached."""
        return UserIntent(
            intent_id=self.intent_id,
            utterance=self.utterance,
            label=self.label,
            confidence=self.confidence,
            targets=self.targets + (target,),
            modalities=self.modalities,
            status=IntentStatus.PROCESSED,
        )
