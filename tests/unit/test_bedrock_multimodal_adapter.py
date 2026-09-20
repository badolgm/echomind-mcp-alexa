"""Unit tests for the multimodal content mapping in the Bedrock adapter."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from src.domain.models.intent import Modality
from src.domain.models.tools import MultimodalAttachment
from src.domain.ports.output.llm_port import LLMRequest
from src.infrastructure.adapters.aws.bedrock_adapter import BedrockLLMAdapter


class FakeBedrockClient:
    """boto3 client double that records the Converse invocation."""

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "output": {"message": {"content": [{"text": "vision summary"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150},
        }


@pytest.fixture
def client() -> FakeBedrockClient:
    return FakeBedrockClient()


@pytest.fixture
def adapter(client: FakeBedrockClient) -> BedrockLLMAdapter:
    return BedrockLLMAdapter(
        model_id="amazon.nova-pro-v1:0", region_name="us-east-1", client=client
    )


def test_multimodal_request_builds_converse_content_blocks(
    adapter: BedrockLLMAdapter, client: FakeBedrockClient
) -> None:
    request = LLMRequest(
        system_prompt="be thorough",
        user_prompt="What is this?",
        attachments=(
            MultimodalAttachment(
                kind=Modality.IMAGE, mime_type="image/png", data=b"\x89PNG\r\n"
            ),
            MultimodalAttachment(
                kind=Modality.DOCUMENT, mime_type="application/pdf", data=b"%PDF-1.4"
            ),
        ),
    )

    adapter._invoke_sync(request)

    payload = client.calls[0]
    content = payload["messages"][0]["content"]
    assert payload["system"] == [{"text": "be thorough"}]
    assert content[0] == {
        "image": {"format": "png", "source": {"bytes": b"\x89PNG\r\n"}}
    }
    assert content[1] == {
        "document": {"format": "pdf", "source": {"bytes": b"%PDF-1.4"}}
    }
    assert content[2] == {"text": "What is this?"}


def test_text_modality_is_inlined_as_string(
    adapter: BedrockLLMAdapter, client: FakeBedrockClient
) -> None:
    request = LLMRequest(
        system_prompt="",
        user_prompt="say hi",
        attachments=(
            MultimodalAttachment(
                kind=Modality.TEXT, mime_type="text/plain", data=b"hello"
            ),
        ),
    )
    adapter._invoke_sync(request)
    content = client.calls[0]["messages"][0]["content"]
    assert content[0] == {"text": "hello"}
    assert content[1] == {"text": "say hi"}


def test_unsupported_modality_is_rejected(adapter: BedrockLLMAdapter) -> None:
    request = LLMRequest(
        system_prompt="",
        user_prompt="beep",
        attachments=(
            MultimodalAttachment(
                kind=Modality.HAPTIC, mime_type="application/haptics", data=b""
            ),
        ),
    )
    with pytest.raises(ValueError):
        adapter._invoke_sync(request)


@pytest.mark.asyncio
async def test_generate_round_trips_text_and_usage(
    adapter: BedrockLLMAdapter, client: FakeBedrockClient
) -> None:
    request = LLMRequest(
        system_prompt="sys",
        user_prompt="What is this?",
        attachments=(
            MultimodalAttachment(
                kind=Modality.IMAGE, mime_type="image/jpeg", data=b"jpeg"
            ),
        ),
    )
    response = await adapter.generate(request)
    assert client.calls[0]["modelId"] == "amazon.nova-pro-v1:0"
    assert response.text == "vision summary"
    assert response.model_id == "amazon.nova-pro-v1:0"
    assert response.finish_reason == "end_turn"
    assert response.usage == {
        "inputTokens": 120,
        "outputTokens": 30,
        "totalTokens": 150,
    }


def test_invalid_mime_format_raises_value_error(adapter: BedrockLLMAdapter) -> None:
    request = LLMRequest(
        system_prompt="",
        user_prompt="what",
        attachments=(
            MultimodalAttachment(
                kind=Modality.IMAGE, mime_type="image/bmp", data=b"bmp"
            ),
        ),
    )
    with pytest.raises(ValueError):
        adapter._invoke_sync(request)
