"""Tests for the quota-fallback resilience layer and local rule engine."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort
from src.infrastructure.adapters.aws.fallback_llm_adapter import (
    ResilientLLMAdapter,
    RuleBasedLLMAdapter,
    is_quota_error,
)


def _client_error(code: str, status: int = 400) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": code, "Message": "boom"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation_name="Converse",
    )


class _FakePrimary(LLMServicePort):
    def __init__(
        self, failures: list[BaseException] | None = None, text: str = "primary-ok"
    ) -> None:
        self._failures = list(failures or [])
        self.text = text
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return LLMResponse(text=self.text, model_id="primary")


class _FakeFallback(LLMServicePort):
    def __init__(self, text: str = "fallback-ok") -> None:
        self.text = text
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.text, model_id="fallback")


REQUEST = LLMRequest(system_prompt="system", user_prompt="user")


def test_is_quota_error_accepts_quota_codes() -> None:
    for code in ("ThrottlingException", "Throttling", "TooManyRequestsException"):
        assert is_quota_error(_client_error(code)) is True
    assert is_quota_error(_client_error("AccessDeniedException")) is True
    assert is_quota_error(_client_error("ServiceQuotaExceededException")) is True


def test_is_quota_error_accepts_transient_http_status() -> None:
    assert is_quota_error(_client_error("Whatever", status=429)) is True
    assert is_quota_error(_client_error("Whatever", status=503)) is True


def test_is_quota_error_accepts_missing_credentials() -> None:
    from botocore.exceptions import NoCredentialsError

    assert is_quota_error(NoCredentialsError()) is True


def test_is_quota_error_rejects_non_quota_failures() -> None:
    assert (
        is_quota_error(_client_error("ResourceNotFoundException", status=404)) is False
    )
    assert is_quota_error(ValueError("not an aws error")) is False
    assert is_quota_error(_client_error("HumanLoopQuotaExceededException")) is True


@pytest.mark.asyncio
async def test_healthy_primary_passes_through() -> None:
    primary = _FakePrimary()
    fallback = _FakeFallback()
    adapter = ResilientLLMAdapter(
        primary=primary, fallback=fallback, cooldown_seconds=3600
    )

    response = await adapter.generate(REQUEST)

    assert response.text == "primary-ok"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert adapter.is_degraded is False
    assert adapter.active_provider == "primary"
    assert adapter.stats["primary_attempts"] == 1
    assert adapter.stats["failovers"] == 0


@pytest.mark.asyncio
async def test_failover_on_throttling() -> None:
    primary = _FakePrimary(failures=[_client_error("ThrottlingException", status=429)])
    fallback = _FakeFallback()
    adapter = ResilientLLMAdapter(
        primary=primary, fallback=fallback, cooldown_seconds=3600
    )

    response = await adapter.generate(REQUEST)

    assert response.text == "fallback-ok"
    assert fallback.calls == 1
    assert adapter.is_degraded is True
    assert adapter.active_provider == "fallback"
    assert adapter.stats == {"primary_attempts": 1, "fallback_calls": 1, "failovers": 1}


@pytest.mark.asyncio
async def test_degraded_window_skips_primary() -> None:
    primary = _FakePrimary(failures=[_client_error("QuotaExceededException")])
    fallback = _FakeFallback()
    adapter = ResilientLLMAdapter(
        primary=primary, fallback=fallback, cooldown_seconds=3600
    )

    await adapter.generate(REQUEST)
    await adapter.generate(REQUEST)

    assert primary.calls == 1
    assert fallback.calls == 2


@pytest.mark.asyncio
async def test_recovers_after_cooldown_elapses() -> None:
    primary = _FakePrimary(failures=[_client_error("ThrottlingException")])
    adapter = ResilientLLMAdapter(primary=primary, cooldown_seconds=0)

    first = await adapter.generate(REQUEST)
    assert first.model_id == "echo-rule-engine-v1"  # local engine answered

    second = await adapter.generate(REQUEST)
    assert second.text == "primary-ok"
    assert primary.calls == 2
    assert adapter.is_degraded is False


@pytest.mark.asyncio
async def test_non_quota_error_propagates() -> None:
    primary = _FakePrimary(failures=[ValueError("bad request")])
    fallback = _FakeFallback()
    adapter = ResilientLLMAdapter(
        primary=primary, fallback=fallback, cooldown_seconds=3600
    )

    with pytest.raises(ValueError, match="bad request"):
        await adapter.generate(REQUEST)
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_rule_engine_is_deterministic() -> None:
    engine = RuleBasedLLMAdapter()
    first = await engine.generate(REQUEST)
    second = await engine.generate(REQUEST)
    assert first.text == second.text
    assert first.model_id == "echo-rule-engine-v1"


@pytest.mark.asyncio
async def test_rule_engine_grades_ambient_critical_signals() -> None:
    engine = RuleBasedLLMAdapter()
    response = await engine.generate(
        LLMRequest(
            system_prompt="ambient monitoring prompt",
            user_prompt="Smoke and flames are visible in the kitchen.",
        )
    )
    assert "CRITICAL" in response.text
    assert "smoke or fire" in response.text.lower()
    assert "recommendation" in response.text.lower()


@pytest.mark.asyncio
async def test_rule_engine_emits_json_classification_when_asked() -> None:
    engine = RuleBasedLLMAdapter()
    response = await engine.generate(
        LLMRequest(
            system_prompt=(
                "Classify the user utterance into an intent label. Answer with "
                "exactly one JSON object."
            ),
            user_prompt="Please monitor the living room for my grandmother.",
        )
    )
    payload = json.loads(response.text)
    assert payload["label"] == "analyze_ambient_stream"
    assert payload["confidence"] == 0.85
