"""MCP resolvers for local vectorial memory (no LLM involved).

Each resolver answers exclusively from structured memory persisted by the
:class:`MemoryBridge` through :class:`VectorMemoryService`. Narratives are
short, deterministic Spanish sentences so Alexa+ can respond with historical
context even behind the Quota Fallback Protocol.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.domain.services.memory_intent import (
    MemoryIntent,
    MemoryIntentClassifier,
    MemoryIntentType,
)
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import ToolHandler
from src.infrastructure.services.memory_service import MemoryRecord, VectorMemoryService

MEMORY_TOOL_NAMES = frozenset(
    {"memory_last_seen", "memory_search", "memory_summary", "memory_converse"}
)

_DESCRIPTORS_ES: dict[str, str] = {
    "PERSON": "una persona",
    "PERSON_ELDERLY": "una persona mayor",
    "PET": "una mascota",
    "PET_ESCAPING": "una mascota intentando escapar",
    "GATE_OPEN": "la reja abierta",
    "DOOR_OPEN": "la puerta abierta",
    "MOTION": "movimiento",
    "SMOKE": "humo",
    "FIRE": "fuego",
    "PACKAGE": "un paquete",
    "INTRUDER": "una intrusión",
}

_ABSENCE_LABELS = ("GATE_OPEN", "PET_ESCAPING", "PERSON_ELDERLY")

_CURRENT_PHRASES: dict[str, str] = {
    "MOTION": "movimiento en el acceso principal",
    "GATE_OPEN": "la reja abierta",
    "DOOR_OPEN": "la puerta abierta",
    "PET_ESCAPING": "una mascota intentando escapar",
    "PET": "una mascota",
    "PERSON": "una persona",
    "PERSON_ELDERLY": "una persona mayor",
    "SMOKE": "indicadores de humo",
    "FIRE": "fuego",
}


def _describe(label: str) -> str:
    return _DESCRIPTORS_ES.get(label, f"el evento {label}")


def _relative_time(timestamp: float, now: float) -> str:
    delta = max(0.0, now - timestamp)
    if delta < 60:
        return "hace unos segundos"
    minutes = int(delta // 60)
    if delta < 3600:
        return "hace 1 minuto" if minutes == 1 else f"hace {minutes} minutos"
    hours = int(delta // 3600)
    if delta < 86400:
        return "hace 1 hora" if hours == 1 else f"hace {hours} horas"
    days = int(delta // 86400)
    if delta < 604800:
        return "hace 1 día" if days == 1 else f"hace {days} días"
    weeks = int(delta // 604800)
    return "hace 1 semana" if weeks == 1 else f"hace {weeks} semanas"


def _labels_of(record: object) -> list[str]:
    labels = []
    for item in getattr(record, "detections", ()):
        label = str(item.get("label") or "")
        if label:
            labels.append(label)
    return labels


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(data: str) -> MCPResponse:
    return MCPResponse(content=(MCPContentItem(kind="text", data=data),))


def _error(message: str) -> MCPResponse:
    return MCPResponse(
        content=(MCPContentItem(kind="text", data=message),), is_error=True
    )


def build_memory_last_seen_resolver(memory: VectorMemoryService) -> ToolHandler:
    """Answer 'cuándo ocurrió por última vez' for one canonical label."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        label = str(arguments.get("label") or "").strip().upper()
        if not label:
            return _error("the 'label' argument is required (e.g. GATE_OPEN, PERSON)")
        location = str(arguments.get("location") or "").strip() or None
        record = memory.last_seen(label=label, location=location)
        if record is None:
            zone = f" en {location}" if location else ""
            return _text(
                f"No he observado {_describe(label)} en la memoria local{zone}."
            )
        return _text(
            f"La última detección de {_describe(label)} ocurrió "
            f"{_relative_time(record.timestamp, time.time())} en {record.location}."
        )

    return resolve


def build_memory_search_resolver(memory: VectorMemoryService) -> ToolHandler:
    """Retrieve the top-k past observations matching a text query."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _error("the 'query' argument is required")
        limit = max(0, int(_number(arguments.get("limit"), 5)))
        min_score = _number(arguments.get("min_score"), 0.0)
        location = str(arguments.get("location") or "").strip() or None
        results = memory.search_memory(
            query, limit=limit, min_score=min_score, location=location
        )
        if not results:
            return _text(f"No he encontrado recuerdos para: {query}")
        header = f"He encontrado {len(results)} recuerdo(s) relacionados con {query}:"
        lines = [header]
        for record, score in results:
            labels = ", ".join(_labels_of(record)) or "sin etiquetas"
            snippet = str(record.model_analysis).strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."
            lines.append(
                f"- {record.location} [{labels}] riesgo {record.risk} "
                f"(score {score}): {snippet}"
            )
        return _text("\n".join(lines))

    return resolve


def build_memory_summary_resolver(memory: VectorMemoryService) -> ToolHandler:
    """Recap persisted observations over the recent lookback window."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        hours = _number(arguments.get("hours"), 24.0)
        location = str(arguments.get("location") or "").strip() or None
        now = time.time()
        since = now - hours * 3600
        counts = memory.label_counts(since=since, location=location)
        if not counts:
            return _text(
                "Durante las últimas "
                f"{int(hours)} horas no he registrado ninguna alerta memorable."
            )
        observed = ", ".join(
            f"{counts[label]} {_times_word(counts[label])} {_describe(label)}"
            for label, _count in sorted(counts.items(), key=lambda pair: -pair[1])
        )
        sentences = [
            f"Durante las últimas {int(hours)} horas he observado: {observed}."
        ]
        for label in sorted(counts):
            record = memory.last_seen(label=label, location=location)
            if record is not None:
                sentences.append(
                    f"La última detección de {_describe(label)} ocurrió "
                    f"{_relative_time(record.timestamp, time.time())} "
                    f"en {record.location}."
                )
        for label in _ABSENCE_LABELS:
            if label not in counts:
                sentences.append(
                    f"No he observado {_describe(label)} durante las últimas "
                    f"{int(hours)} horas."
                )
        return _text(" ".join(sentences))

    return resolve


def _times_word(count: int) -> str:
    return "vez" if count == 1 else "veces"


def _events_narrative(events: list[MemoryRecord], header: str) -> MCPResponse:
    if not events:
        return _text("No tengo registros históricos para esa consulta.")
    lines = [header]
    for record in events[:3]:
        labels = ", ".join(_labels_of(record)) or "sin etiquetas"
        lines.append(
            f"- {_relative_time(record.timestamp, time.time())} en "
            f"{record.location}: {labels} ({record.risk})"
        )
    return _text("\n".join(lines))


async def _answer_history_intent(
    memory: VectorMemoryService,
    intent: MemoryIntent,
    current_state: Callable[[], Mapping[str, Any]] | None,
) -> MCPResponse:
    now = time.time()
    since = now - intent.hours * 3600 if intent.hours else None

    if intent.intent is MemoryIntentType.EVENT_COUNT:
        count = memory.count_events(intent.risk, since=since)
        if count == 0:
            return _text("No tengo registros históricos para esa consulta.")
        risk_label = f" eventos {intent.risk}" if intent.risk else ""
        return _text(f"He observado {count}{risk_label} durante el período consultado.")

    if intent.intent is MemoryIntentType.TOP_EVENTS:
        return _events_narrative(
            memory.top_events(since=since, limit=3),
            "Los eventos más importantes del período consultado:",
        )

    if intent.intent is MemoryIntentType.HIGH_RISK:
        total = memory.count_events("HIGH", since=since)
        if total == 0:
            return _text("No tengo registros históricos para esa consulta.")
        events = memory.recent_high_risk_events(since=since, limit=3)
        return _events_narrative(
            events, f"He registrado {total} situaciones de riesgo:"
        )

    if intent.intent is MemoryIntentType.CRITICAL_RISK:
        events = memory.recent_critical_events(since=since, limit=3)
        if not events:
            return _text("No hubo eventos críticos recientemente.")
        return _events_narrative(events, "Eventos críticos recientes:")

    if intent.intent is MemoryIntentType.CURRENT_STATE:
        return _current_state_answer(memory, current_state)

    return _text("No tengo registros históricos para esa consulta.")


def _current_state_answer(
    memory: VectorMemoryService,
    current_state: Callable[[], Mapping[str, Any]] | None,
) -> MCPResponse:
    state: Mapping[str, Any] = {}
    if current_state is not None:
        try:
            state = current_state()
        except Exception:  # noqa: BLE001 - live state is best-effort
            state = {}
    labels: list[str] = []
    phrases: list[str] = []
    for item in state.get("detections") or []:
        label = str(item.get("label") or "")
        labels.append(label)
        phrase = _CURRENT_PHRASES.get(label)
        if phrase:
            phrases.append(phrase)
    if phrases:
        sentence = "Actualmente detecto " + ", ".join(phrases) + "."
    else:
        sentence = "Actualmente no tengo detecciones activas."
    similar = sum(
        memory.count_occurrences(label, since=time.time() - 86400) for label in labels
    )
    if similar:
        sentence += (
            f" He observado eventos similares {similar} {_times_word(similar)} "
            "durante las últimas 24 horas."
        )
    return _text(sentence)


def build_memory_converse_resolver(
    memory: VectorMemoryService,
    current_state: Callable[[], Mapping[str, Any]] | None = None,
) -> ToolHandler:
    """Answer a natural-language memory question by deterministic routing."""

    classifier = MemoryIntentClassifier()
    last_seen = build_memory_last_seen_resolver(memory)
    search = build_memory_search_resolver(memory)
    summary = build_memory_summary_resolver(memory)

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _error("the 'query' argument is required")
        intent = classifier.classify(query)
        if intent.intent is MemoryIntentType.LAST_SEEN:
            if not intent.label:
                return await search({"query": intent.query})
            return await last_seen(
                {"label": intent.label, "location": intent.location or ""}
            )
        if intent.intent is MemoryIntentType.SEARCH:
            return await search(
                {"query": intent.query, "location": intent.location or ""}
            )
        if intent.intent is MemoryIntentType.SUMMARY:
            return await summary(
                {"hours": intent.hours or 24.0, "location": intent.location or ""}
            )
        return await _answer_history_intent(memory, intent, current_state)

    return resolve


def build_memory_resolver(
    tool_name: str,
    memory: VectorMemoryService | None,
    current_state: Callable[[], Mapping[str, Any]] | None = None,
) -> ToolHandler:
    """Dispatch the catalog memory tool name onto its storage-backed resolver."""
    if tool_name not in MEMORY_TOOL_NAMES or memory is None:
        return _unavailable_memory_resolver()
    if tool_name == "memory_converse":
        return build_memory_converse_resolver(memory, current_state)
    builders: Mapping[str, Callable[[VectorMemoryService], ToolHandler]] = {
        "memory_last_seen": build_memory_last_seen_resolver,
        "memory_search": build_memory_search_resolver,
        "memory_summary": build_memory_summary_resolver,
    }
    return builders[tool_name](memory)


def _unavailable_memory_resolver() -> ToolHandler:
    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        return _error("memory service is not available")

    return resolve
