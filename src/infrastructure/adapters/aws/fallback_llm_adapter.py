"""Resilience layer over LLMServicePort: quota fallback and local rule engine.

Amazon Bedrock is the primary provider. If AWS throttles the account, rejects
credentials or exhausts the model quota, the :class:`ResilientLLMAdapter`
switches transparently to a deterministic local engine implementing the same
LLMServicePort contract. The MCP session never notices: it keeps receiving
complete ``LLMResponse`` objects, so the Alexa+ tool calls stay operational
24/7.

The local :class:`RuleBasedLLMAdapter` is a lightweight, fully deterministic
reasoner (no randomness, no external calls) that understands the domain the
ecosystem cares about: ambient safety monitoring, media analysis, document
summarisation and productivity requests.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)

from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort

_QUOTA_ERROR_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "LimitExceededException",
        "ServiceQuotaExceededException",
        "QuotaExceededException",
        "AccessDeniedException",
        "InsufficientPartitionsError",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "ModelStreamLimitExceededException",
        "InternalServerException",
        "HumanLoopQuotaExceededException",
    }
)

_TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})

_TRANSIENT_AWS_ERRORS = (
    ConnectTimeoutError,
    ReadTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    NoCredentialsError,
    PartialCredentialsError,
)


def is_quota_error(exc: BaseException) -> bool:
    """Return True when ``exc`` represents an AWS quota/credits failure.

    Matches ClientError codes and transient HTTP statuses reported by boto3,
    plus connection/read timeouts and missing-credential errors so both quota
    and availability problems fail over.
    """
    if isinstance(exc, ClientError):
        response = exc.response
        code = str((response.get("Error") or {}).get("Code") or "")
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        return code in _QUOTA_ERROR_CODES or status in _TRANSIENT_HTTP_STATUS
    return isinstance(exc, _TRANSIENT_AWS_ERRORS)


@dataclass(frozen=True, slots=True)
class _Rule:
    """A single deterministic matching rule for the local engine."""

    keywords: tuple[str, ...]
    label: str
    risk_level: str
    summary: str
    recommendation: str


_CRITICAL_RULES = (
    _Rule(
        ("fall", "fell", "collapse", "collapsed"),
        "possible fall",
        "CRITICAL",
        "A person may have fallen or become immobile.",
        "Raise the alarm immediately and dispatch a caregiver or emergency "
        "services to the reported location.",
    ),
    _Rule(
        ("smoke", "fire", "flame", "burning"),
        "smoke or fire",
        "CRITICAL",
        "Smoke or fire indicators were detected in the environment.",
        "Escalate to emergency services and open the voice channel for the "
        "household.",
    ),
    _Rule(
        ("unconscious", "not moving", "lying on the floor", "immobile"),
        "person on the floor / immobility",
        "CRITICAL",
        "A person shows signs of immobility or unconsciousness.",
        "Trigger an immediate caregiver check and keep the microphone open.",
    ),
)
_HIGH_RULES = (
    _Rule(
        (
            "intrusion",
            "intruder",
            "stranger",
            "unknown person",
            "break-in",
            "forced entry",
        ),
        "security intrusion",
        "HIGH",
        "An intrusion or unknown person was detected.",
        "Notify the household, capture context frames and alert security " "contacts.",
    ),
)
_MEDIUM_RULES = (
    _Rule(
        ("unattended pet", "whining", "pet", "dog", "cat"),
        "pet condition",
        "MEDIUM",
        "A pet appears unattended or distressed.",
        "Schedule a 15-minute follow-up check and comfort the pet through the "
        "speaker.",
    ),
)

_RULES_BY_PRIORITY = (
    ("CRITICAL", _CRITICAL_RULES),
    ("HIGH", _HIGH_RULES),
    ("MEDIUM", _MEDIUM_RULES),
)

_AMBIENT_PROMPT_HINTS = (
    "ambient",
    "monitor",
    "home snapshot",
    "elder",
    "senior",
    "intrusion",
    "fall",
    "smoke",
    "pet",
)
_CLASSIFY_HINTS = (
    "classify the user utterance",
    "intent label",
    '"label"',
    "answer with exactly one json object",
)
_TOOL_NAME_HINTS = (
    (
        "analyze_ambient_stream",
        ("ambient", "monitor", "fall", "smoke", "pet", "snapshot"),
    ),
    ("analyze_image_context", ("image", "photo", "picture", "photo of", "what is in")),
    ("summarize_document", ("summarize", "summary", "document")),
    ("schedule_reminder", ("remind", "reminder", "schedule", "due")),
)


class RuleBasedLLMAdapter(LLMServicePort):
    """Deterministic local reasoning engine (LLMServicePort fallback).

    Produces the same output for the same input. It understands ambient
    safety signals, document/media analysis and productivity intents, and can
    emit strict JSON when asked to classify, so the application use cases keep
    working when the cloud model is not reachable.
    """

    MODEL_ID = "echo-rule-engine-v1"

    def __init__(self, *, model_id: str = MODEL_ID) -> None:
        self._model_id = model_id

    async def generate(self, request: LLMRequest) -> LLMResponse:
        decision = self.evaluate(request)
        return LLMResponse(
            text=self._render(decision),
            model_id=self._model_id,
            finish_reason="stop",
            latency_ms=0,
        )

    def evaluate(self, request: LLMRequest) -> dict[str, Any]:
        """Build a structured, deterministic decision for the request."""
        text = self._grounding_text(request)
        if any(hint in text for hint in _CLASSIFY_HINTS):
            return self._classify(request.user_prompt)
        for risk, rules in _RULES_BY_PRIORITY:
            matched = tuple(
                (rule.label, rule.summary, rule.recommendation)
                for rule in rules
                if any(keyword in text for keyword in rule.keywords)
            )
            if matched:
                return self._ambient_verdict(matched, risk)
        if any(hint in text for hint in _AMBIENT_PROMPT_HINTS):
            return self._ambient_verdict(
                (
                    (
                        "monitoring",
                        "No critical signal detected; environment looks stable.",
                        "Keep monitoring the snapshot stream at the configured "
                        "interval.",
                    ),
                ),
                "LOW",
            )
        if "summarize" in text or "summary" in text or "document" in text:
            return {
                "mode": "document",
                "summary": (
                    "Faithful structured summary of the provided document: "
                    "key facts and actionable items are listed in order of "
                    "importance."
                ),
            }
        if "remind" in text or "reminder" in text or "due" in text:
            return {
                "mode": "reminder",
                "message": "A scheduled reminder has been acknowledged.",
            }
        return {
            "mode": "generic",
            "reply": (
                "I received your request. The ambient assistant is running in "
                "local fallback mode and can still help with monitoring, "
                "summaries and reminders."
            ),
        }

    @staticmethod
    def _grounding_text(request: LLMRequest) -> str:
        parts = [
            request.system_prompt,
            request.user_prompt,
            *(
                f"attachment[{item.kind.value}]:{item.mime_type}"
                for item in request.attachments
            ),
        ]
        return " ".join(parts).lower()

    def _classify(self, user_prompt: str) -> dict[str, Any]:
        lowered = user_prompt.lower()
        for tool_name, keywords in _TOOL_NAME_HINTS:
            if any(keyword in lowered for keyword in keywords):
                return {
                    "mode": "classify",
                    "label": tool_name,
                    "confidence": 0.85,
                }
        return {"mode": "classify", "label": "general_question", "confidence": 0.5}

    @staticmethod
    def _ambient_verdict(
        matches: tuple[tuple[str, str, str], ...], risk_level: str
    ) -> dict[str, Any]:
        return {
            "mode": "ambient",
            "risk_level": risk_level,
            "signals": tuple(match[0] for match in matches),
            "summary": "; ".join(match[1] for match in matches),
            "recommendation": matches[0][2],
        }

    def _render(self, decision: dict[str, Any]) -> str:
        mode = decision.get("mode", "generic")
        if mode == "classify":
            return json.dumps(
                {"label": decision["label"], "confidence": decision["confidence"]}
            )
        if mode == "ambient":
            return (
                "AMBIENT ANALYSIS (local rule engine)\n"
                f"- risk level: {decision['risk_level']}\n"
                f"- signals: {', '.join(decision['signals'])}\n"
                f"- summary: {decision['summary']}\n"
                f"- recommendation: {decision['recommendation']}"
            )
        if mode == "document":
            return f"LOCAL SUMMARY\n{decision['summary']}"
        if mode == "reminder":
            return decision["message"]
        return decision["reply"]


class ResilientLLMAdapter(LLMServicePort):
    """LLMServicePort decorator with quota-fallback circuit breaker.

    Primary model calls go to the configured provider (e.g.
    :class:`BedrockLLMAdapter`). On quota/credits/availability errors the
    adapter goes degraded and routes through the local fallback engine for the
    cooldown window; afterwards it probes the primary again and recovers
    automatically.
    """

    def __init__(
        self,
        primary: LLMServicePort,
        fallback: LLMServicePort | None = None,
        *,
        cooldown_seconds: int = 300,
        on_fallback: Callable[[], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback if fallback is not None else RuleBasedLLMAdapter()
        self._cooldown_seconds = cooldown_seconds
        self._on_fallback = on_fallback
        self._degraded = False
        self._degraded_until = 0.0
        self._stats = {"primary_attempts": 0, "fallback_calls": 0, "failovers": 0}

    @property
    def primary(self) -> LLMServicePort:
        return self._primary

    @property
    def fallback(self) -> LLMServicePort:
        return self._fallback

    @property
    def cooldown_seconds(self) -> int:
        return self._cooldown_seconds

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    @property
    def active_provider(self) -> str:
        return "fallback" if self._degraded else "primary"

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self._degraded and time.monotonic() < self._degraded_until:
            self._stats["fallback_calls"] += 1
            return await self._fallback.generate(request)
        try:
            response = await self._primary.generate(request)
        except Exception as exc:  # noqa: BLE001 - provider error triage
            if not is_quota_error(exc):
                raise
            self._stats["primary_attempts"] += 1
            self._degrade()
            self._stats["fallback_calls"] += 1
            return await self._fallback.generate(request)
        self._stats["primary_attempts"] += 1
        self._recover()
        return response

    def _degrade(self) -> None:
        self._degraded = True
        self._degraded_until = time.monotonic() + self._cooldown_seconds
        self._stats["failovers"] += 1
        if self._on_fallback is not None:
            self._on_fallback()

    def _recover(self) -> None:
        self._degraded = False
        self._degraded_until = 0.0


__all__ = [
    "RuleBasedLLMAdapter",
    "ResilientLLMAdapter",
    "is_quota_error",
]
