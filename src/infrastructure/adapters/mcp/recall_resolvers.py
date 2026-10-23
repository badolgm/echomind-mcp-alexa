"""MCP/HTTP resolver for the experimental ``memory_recall`` channel.

This is the *second* memory path, deliberately parallel to the production
``memory_converse`` tool: ``memory_converse`` keeps routing V1 intents with its
verbatim narratives, while this module delegates to the recall planner and
engine (A1/A2) and answers **only** from the evidence that was actually
retrieced, exposing that evidence and the executed trace for auditability.

Nothing here replaces, wraps or mutates V1: it is an additive surface that
stays inert until a caller explicitly asks for ``memory_recall``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Mapping

from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.domain.services.context import context_to_dict
from src.domain.services.evidence import RecallResult
from src.domain.services.recall_planner import understand
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import ToolHandler
from src.infrastructure.services.memory_service import VectorMemoryService
from src.infrastructure.services.recall_engine import (
    ENGINE_NAME,
    ENGINE_VERSION,
    RecallEngine,
)


def _text(data: str) -> MCPResponse:
    return MCPResponse(content=(MCPContentItem(kind="text", data=data),))


def _error(message: str) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=message),), is_error=True
    )


def _number(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def recall(
    memory: VectorMemoryService,
    query: str,
    *,
    lang: str | None = None,
    now: float | None = None,
    session_start: float | None = None,
    state_provider: Callable[[], Mapping[str, Any]] | None = None,
) -> RecallResult:
    """Plan and execute one recall request end to end.

    Pure and deterministic: no LLM, no wall-clock dependency unless ``now`` is
    omitted (in which case the current time is taken once, at the boundary).
    ``state_provider`` is the read-only live home-state source used by
    ``CURRENT_STATE`` plans; without it those plans abstain honestly.
    """
    anchor = time.time() if now is None else float(now)
    plan = understand(query, lang=lang, now=anchor)
    return RecallEngine(memory=memory, state_provider=state_provider).execute(
        plan, now=anchor, session_start=session_start
    )


def recall_result_payload(result: RecallResult) -> dict[str, object]:
    """JSON-safe projection of a recall result, used by the ``/api/recall`` route."""
    return {
        "response": result.utterance,
        "is_error": result.is_error,
        "lang": result.lang,
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "evidence": [
            {
                "id": item.record_id,
                "ts": item.ts,
                "location": item.location,
                "labels": list(item.labels),
                "risk": item.risk,
                "confidence": item.confidence,
                "camera_id": item.camera_id,
                "zone": item.zone,
            }
            for item in result.evidence
        ],
        "trace": {
            "lang": result.trace.lang,
            "plan": result.trace.plan,
            "ops": [dict(entry) for entry in result.trace.ops_executed],
            "evidence_ids": list(result.trace.evidence_ids),
            "relations": [dict(item) for item in result.trace.relations],
        },
        "context": [context_to_dict(item) for item in result.context],
        "context_response": result.context_utterance,
    }


def _render(result: RecallResult) -> str:
    """Narration plus the evidence and trace that back it."""
    english = result.lang == "en"
    lines = [result.utterance]
    if result.evidence:
        lines.append("evidence:" if english else "evidencia:")
        for item in result.evidence:
            fallback = "no labels" if english else "sin etiquetas"
            labels = ", ".join(item.labels) or fallback
            place = f" {item.location}" if item.location else ""
            lines.append(f"- {item.record_id} [{labels}]{place} ({item.risk})")
    else:
        lines.append("evidence: none" if english else "evidencia: ninguna")
    ops = ", ".join(str(entry.get("op", "")) for entry in result.trace.ops_executed)
    lines.append(f"trace: lang={result.trace.lang} ops={ops or 'none'}")
    return "\n".join(lines)


def build_memory_recall_resolver(
    memory: VectorMemoryService,
    *,
    session_start: float | None = None,
    state_provider: Callable[[], Mapping[str, Any]] | None = None,
) -> ToolHandler:
    """Answer a natural-language question through the recall engine."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _error("the 'query' argument is required")
        lang = str(arguments.get("lang") or "").strip() or None
        now_arg = arguments.get("now")
        now = _number(now_arg, time.time()) if now_arg is not None else None
        result = recall(
            memory,
            query,
            lang=lang,
            now=now,
            session_start=session_start,
            state_provider=state_provider,
        )
        return _text(_render(result))

    return resolve
