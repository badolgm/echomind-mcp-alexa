"""Concrete adapter bridging the AWS Bedrock Converse API to LLMServicePort.

Uses the synchronous boto3 client wrapped with asyncio.to_thread so the
adapter stays non-blocking without depending on async AWS SDKs. Supports
multimodal input (images, audio, video, documents) through the Converse
content-block API.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, Mapping

import boto3

from src.domain.models.intent import Modality
from src.domain.models.tools import MultimodalAttachment
from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort

_DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"
_DEFAULT_REGION = "us-east-1"

_IMAGE_FORMATS = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

_VIDEO_FORMATS = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
}

_AUDIO_FORMATS = {
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}

_DOCUMENT_FORMATS = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "text/plain": "txt",
    "text/markdown": "md",
}


class BedrockLLMAdapter(LLMServicePort):
    """LLMServicePort implementation backed by Amazon Bedrock.

    The underlying boto3 client can be injected to ease testing; by default it
    is built from the standard AWS credential chain.
    """

    def __init__(
        self,
        *,
        model_id: str = _DEFAULT_MODEL_ID,
        region_name: str = _DEFAULT_REGION,
        client: Any | None = None,
    ) -> None:
        self._model_id = model_id
        self._region_name = region_name
        self._client = (
            client
            if client is not None
            else boto3.client("bedrock-runtime", region_name=region_name)
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        model_response = await asyncio.to_thread(self._invoke_sync, request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        response = self._parse_response(model_response)
        return LLMResponse(
            text=response.text,
            model_id=self._model_id,
            finish_reason=response.finish_reason,
            usage=response.usage,
            latency_ms=latency_ms,
        )

    def _invoke_sync(self, request: LLMRequest) -> Mapping[str, Any]:
        inference_config: dict[str, Any] = {
            "maxTokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop_sequences:
            inference_config["stopSequences"] = list(request.stop_sequences)
        content_blocks: list[dict[str, Any]] = [
            self._attachment_to_converse_block(attachment)
            for attachment in request.attachments
        ]
        content_blocks.append({"text": request.user_prompt})
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": content_blocks}],
            system=[{"text": request.system_prompt}],
            inferenceConfig=inference_config,
        )

    def _attachment_to_converse_block(
        self, attachment: MultimodalAttachment
    ) -> dict[str, Any]:
        if attachment.kind is Modality.IMAGE:
            return _media_block("image", _IMAGE_FORMATS.get, attachment)
        if attachment.kind is Modality.VIDEO:
            return _media_block("video", _VIDEO_FORMATS.get, attachment)
        if attachment.kind is Modality.AUDIO:
            return _media_block("audio", _AUDIO_FORMATS.get, attachment)
        if attachment.kind is Modality.DOCUMENT:
            return _media_block("document", _DOCUMENT_FORMATS.get, attachment)
        if attachment.kind is Modality.TEXT:
            return {"text": attachment.data.decode("utf-8", errors="replace")}
        raise ValueError(
            f"modality {attachment.kind.value} is not supported by the Converse adapter"
        )

    def _parse_response(self, model_response: Mapping[str, Any]) -> LLMResponse:
        message = model_response.get("output", {}).get("message", {})
        text = "".join(
            item.get("text", "")
            for item in message.get("content", [])
            if isinstance(item, dict) and item.get("text")
        )
        usage = model_response.get("usage", {})
        return LLMResponse(
            text=text.strip(),
            model_id=self._model_id,
            finish_reason=model_response.get("stopReason"),
            usage=(
                {str(key): int(value) for key, value in usage.items()}
                if usage
                else None
            ),
        )


def _media_block(
    block_type: str,
    format_lookup: Callable[[str], str | None],
    attachment: MultimodalAttachment,
) -> dict[str, Any]:
    fmt = format_lookup(attachment.mime_type)
    if fmt is None:
        raise ValueError(
            f"unsupported {block_type} MIME type: {attachment.mime_type!r}"
        )
    return {block_type: {"format": fmt, "source": {"bytes": attachment.data}}}
