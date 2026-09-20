"""Output port for LLM reasoning.

Defines the contract the application uses to obtain AI classification and
free-form responses. The concrete implementation (e.g. AWS Bedrock, local
model, mock) is provided by the infrastructure layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Immutable request payload for a single model-generation call."""

    system_prompt: str
    user_prompt: str
    temperature: float = 0.0
    max_tokens: int = 256
    stop_sequences: tuple[str, ...] = ()
    extra: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be within [0, 2], got {self.temperature!r}"
            )
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens!r}")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Immutable result of a single model-generation call."""

    text: str
    model_id: str
    finish_reason: str | None = None
    usage: Mapping[str, int] | None = None
    latency_ms: int = 0


class LLMServicePort(ABC):
    """Port for LLM-based reasoning required by the application layer."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Run a single generation against the configured foundation model."""
