"""Concrete adapter bridging the AWS Bedrock Converse API to LLMServicePort.

Uses the synchronous boto3 client wrapped with asyncio.to_thread so the
adapter stays non-blocking without depending on async AWS SDKs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping

import boto3

from src.domain.ports.output.llm_port import LLMRequest, LLMResponse, LLMServicePort

_DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"
_DEFAULT_REGION = "us-east-1"


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
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": request.user_prompt}]}],
            system=[{"text": request.system_prompt}],
            inferenceConfig=inference_config,
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
