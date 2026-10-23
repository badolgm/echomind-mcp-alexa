"""MCP resolvers for local vectorial memory (no LLM involved).

Each resolver answers exclusively from structured memory persisted by the
:class:`MemoryBridge` through :class:`VectorMemoryService`. Narratives are
short, deterministic sentences (in Spanish or English) so Alexa+ can respond with
historical context even behind the Quota Fallback Protocol.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from src.domain.ports.output.mcp_port import MCPContentItem, MCPResponse
from src.domain.services.current_state_reasoning import render_state_answer
from src.domain.services.memory_intent import (
    MemoryIntent,
    MemoryIntentClassifier,
    MemoryIntentType,
)
from src.domain.services.query_router import QueryKind, StateTopic, route_query
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import ToolHandler
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)

MEMORY_TOOL_NAMES = frozenset(
    {
        "memory_last_seen",
        "memory_search",
        "memory_summary",
        "memory_converse",
        "memory_recall",
    }
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
    "FALL DETECTED": "una caída",
}

_DESCRIPTORS_EN: dict[str, str] = {
    "PERSON": "a person",
    "PERSON_ELDERLY": "an elderly person",
    "PET": "a pet",
    "PET_ESCAPING": "a pet attempting to escape",
    "GATE_OPEN": "the open gate",
    "DOOR_OPEN": "the open door",
    "MOTION": "motion",
    "SMOKE": "smoke",
    "FIRE": "fire",
    "PACKAGE": "a package",
    "INTRUDER": "an intrusion",
    "FALL DETECTED": "a fall",
}

_ABSENCE_LABELS = ("GATE_OPEN", "PET_ESCAPING", "PERSON_ELDERLY")

_CURRENT_PHRASES_ES: dict[str, str] = {
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

_CURRENT_PHRASES_EN: dict[str, str] = {
    "MOTION": "motion at main access",
    "GATE_OPEN": "the open gate",
    "DOOR_OPEN": "the open door",
    "PET_ESCAPING": "a pet attempting to escape",
    "PET": "a pet",
    "PERSON": "a person",
    "PERSON_ELDERLY": "an elderly person",
    "SMOKE": "smoke indicators",
    "FIRE": "fire",
}


def _describe(label: str, lang: str = "es") -> str:
    if lang == "en":
        return _DESCRIPTORS_EN.get(label, f"the {label} event")
    return _DESCRIPTORS_ES.get(label, f"el evento {label}")


def _relative_time(timestamp: float, now: float, lang: str = "es") -> str:
    delta = max(0.0, now - timestamp)
    if lang == "en":
        if delta < 60:
            return "a few seconds ago"
        minutes = int(delta // 60)
        if delta < 3600:
            return "1 minute ago" if minutes == 1 else f"{minutes} minutes ago"
        hours = int(delta // 3600)
        if delta < 86400:
            return "1 hour ago" if hours == 1 else f"{hours} hours ago"
        days = int(delta // 86400)
        if delta < 604800:
            return "1 day ago" if days == 1 else f"{days} days ago"
        weeks = int(delta // 604800)
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"

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
        lang = str(arguments.get("lang") or "es").strip().lower()
        if not label:
            return _error("the 'label' argument is required (e.g. GATE_OPEN, PERSON)")
        location = str(arguments.get("location") or "").strip() or None
        record = memory.last_seen(label=label, location=location)
        if record is None:
            if lang == "en":
                zone = f" at {location}" if location else ""
                return _text(
                    f"I have not observed {_describe(label, 'en')} "
                    f"in local memory{zone}."
                )
            zone = f" en {location}" if location else ""
            return _text(
                f"No he observado {_describe(label, 'es')} en la memoria local{zone}."
            )

        if lang == "en":
            return _text(
                f"The last detection of {_describe(label, 'en')} occurred "
                f"{_relative_time(record.timestamp, time.time(), 'en')} "
                f"at {record.location}."
            )
        return _text(
            f"La última detección de {_describe(label, 'es')} ocurrió "
            f"{_relative_time(record.timestamp, time.time(), 'es')} "
            f"en {record.location}."
        )

    return resolve


def build_memory_search_resolver(memory: VectorMemoryService) -> ToolHandler:
    """Retrieve the top-k past observations matching a text query."""

    async def resolve(arguments: Mapping[str, Any]) -> MCPResponse:
        query = str(arguments.get("query") or "").strip()
        lang = str(arguments.get("lang") or "es").strip().lower()
        if not query:
            return _error("the 'query' argument is required")
        limit = max(0, int(_number(arguments.get("limit"), 5)))
        min_score = _number(arguments.get("min_score"), 0.0)
        location = str(arguments.get("location") or "").strip() or None
        results = memory.search_memory(
            query, limit=limit, min_score=min_score, location=location
        )
        if not results:
            if lang == "en":
                return _text(f"I found no memories for: {query}")
            return _text(f"No he encontrado recuerdos para: {query}")

        if lang == "en":
            header = f"I found {len(results)} memory record(s) related to {query}:"
            lines = [header]
            for record, score in results:
                labels = ", ".join(_labels_of(record)) or "no labels"
                snippet = str(record.model_analysis).strip().replace("\n", " ")
                if len(snippet) > 120:
                    snippet = snippet[:120] + "..."
                lines.append(
                    f"- {record.location} [{labels}] risk {record.risk} "
                    f"(score {score}): {snippet}"
                )
            return _text("\n".join(lines))

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
        lang = str(arguments.get("lang") or "es").strip().lower()
        now = time.time()
        since = now - hours * 3600
        counts = memory.label_counts(since=since, location=location)

        if not counts:
            if lang == "en":
                return _text(
                    f"During the last {int(hours)} hours I have not "
                    "recorded any memorable alerts."
                )
            return _text(
                "Durante las últimas "
                f"{int(hours)} horas no he registrado ninguna alerta memorable."
            )

        if lang == "en":
            observed = ", ".join(
                f"{counts[label]} {_times_word(counts[label], 'en')} "
                f"{_describe(label, 'en')}"
                for label, _count in sorted(counts.items(), key=lambda pair: -pair[1])
            )
            sentences = [
                f"During the last {int(hours)} hours I have observed: {observed}."
            ]
            for label in sorted(counts):
                record = memory.last_seen(label=label, location=location)
                if record is not None:
                    sentences.append(
                        f"The last detection of {_describe(label, 'en')} occurred "
                        f"{_relative_time(record.timestamp, time.time(), 'en')} "
                        f"at {record.location}."
                    )
            for label in _ABSENCE_LABELS:
                if label not in counts:
                    sentences.append(
                        f"I have not observed {_describe(label, 'en')} "
                        f"during the last {int(hours)} hours."
                    )
            return _text(" ".join(sentences))

        observed = ", ".join(
            f"{counts[label]} {_times_word(counts[label], 'es')} "
            f"{_describe(label, 'es')}"
            for label, _count in sorted(counts.items(), key=lambda pair: -pair[1])
        )
        sentences = [
            f"Durante las últimas {int(hours)} horas he observado: {observed}."
        ]
        for label in sorted(counts):
            record = memory.last_seen(label=label, location=location)
            if record is not None:
                sentences.append(
                    f"La última detección de {_describe(label, 'es')} ocurrió "
                    f"{_relative_time(record.timestamp, time.time(), 'es')} "
                    f"en {record.location}."
                )
        for label in _ABSENCE_LABELS:
            if label not in counts:
                sentences.append(
                    f"No he observado {_describe(label, 'es')} durante las últimas "
                    f"{int(hours)} horas."
                )
        return _text(" ".join(sentences))

    return resolve


def _times_word(count: int, lang: str = "es") -> str:
    if lang == "en":
        return "time" if count == 1 else "times"
    return "vez" if count == 1 else "veces"


def _events_narrative(
    events: list[MemoryRecord], header: str, lang: str = "es"
) -> MCPResponse:
    if not events:
        msg = (
            "I have no historical records for that query."
            if lang == "en"
            else "No tengo registros históricos para esa consulta."
        )
        return _text(msg)
    lines = [header]
    for record in events[:3]:
        labels = ", ".join(_labels_of(record)) or (
            "no labels" if lang == "en" else "sin etiquetas"
        )
        prep = "at" if lang == "en" else "en"
        lines.append(
            f"- {_relative_time(record.timestamp, time.time(), lang)} {prep} "
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
    lang = intent.lang

    if intent.intent is MemoryIntentType.EVENT_COUNT:
        count = memory.count_events(intent.risk, since=since)
        if count == 0:
            msg = (
                "I have no historical records for that query."
                if lang == "en"
                else "No tengo registros históricos para esa consulta."
            )
            return _text(msg)
        if lang == "en":
            risk_label = f" {intent.risk}" if intent.risk else ""
            return _text(
                f"I observed {count}{risk_label} events during the requested period."
            )
        risk_label = f" eventos {intent.risk}" if intent.risk else ""
        return _text(f"He observado {count}{risk_label} durante el período consultado.")

    if intent.intent is MemoryIntentType.TOP_EVENTS:
        header = (
            "Most important events from the requested period:"
            if lang == "en"
            else "Los eventos más importantes del período consultado:"
        )
        return _events_narrative(
            memory.top_events(since=since, limit=3), header, lang=lang
        )

    if intent.intent is MemoryIntentType.HIGH_RISK:
        total = memory.count_events("HIGH", since=since)
        if total == 0:
            msg = (
                "I have no historical records for that query."
                if lang == "en"
                else "No tengo registros históricos para esa consulta."
            )
            return _text(msg)
        events = memory.recent_high_risk_events(since=since, limit=3)
        header = (
            f"I recorded {total} risk situations:"
            if lang == "en"
            else f"He registrado {total} situaciones de riesgo:"
        )
        return _events_narrative(events, header, lang=lang)

    if intent.intent is MemoryIntentType.CRITICAL_RISK:
        events = memory.recent_critical_events(since=since, limit=3)
        if not events:
            msg = (
                "No critical events occurred recently."
                if lang == "en"
                else "No hubo eventos críticos recientemente."
            )
            return _text(msg)
        header = (
            "Recent critical events:" if lang == "en" else "Eventos críticos recientes:"
        )
        return _events_narrative(events, header, lang=lang)

    if intent.intent is MemoryIntentType.CURRENT_STATE:
        return _current_state_answer(memory, current_state, lang=lang)

    msg = (
        "I have no historical records for that query."
        if lang == "en"
        else "No tengo registros históricos para esa consulta."
    )
    return _text(msg)


def _current_state_answer(
    memory: VectorMemoryService,
    current_state: Callable[[], Mapping[str, Any]] | None,
    lang: str = "es",
) -> MCPResponse:
    state: Mapping[str, Any] = {}
    if current_state is not None:
        try:
            state = current_state()
        except Exception:  # noqa: BLE001 - live state is best-effort
            state = {}
    labels: list[str] = []
    phrases: list[str] = []
    phrases_dict = _CURRENT_PHRASES_EN if lang == "en" else _CURRENT_PHRASES_ES

    for item in state.get("detections") or []:
        label = str(item.get("label") or "")
        labels.append(label)
        phrase = phrases_dict.get(label)
        if phrase:
            phrases.append(phrase)

    if phrases:
        sentence = (
            "Currently I detect " + ", ".join(phrases) + "."
            if lang == "en"
            else "Actualmente detecto " + ", ".join(phrases) + "."
        )
    else:
        sentence = (
            "Currently I have no active detections."
            if lang == "en"
            else "Actualmente no tengo detecciones activas."
        )

    similar = sum(
        memory.count_occurrences(label, since=time.time() - 86400) for label in labels
    )
    if similar:
        if lang == "en":
            sentence += (
                f" I have observed similar events {similar} "
                f"{_times_word(similar, 'en')} during the last 24 hours."
            )
        else:
            sentence += (
                f" He observado eventos similares {similar} "
                f"{_times_word(similar, 'es')} durante las últimas 24 horas."
            )
    return _text(sentence)


def _read_live_state(
    current_state: Callable[[], Mapping[str, Any]] | None,
) -> Mapping[str, Any]:
    """Best-effort read of the live snapshot (absent/failed provider → {})."""
    if current_state is None:
        return {}
    try:
        return dict(current_state() or {})
    except Exception:  # noqa: BLE001 - live state is best-effort
        return {}


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
        lang_arg = str(arguments.get("lang") or "").strip() or None
        if not query:
            return _error("the 'query' argument is required")
        decision = route_query(query, lang_arg)
        if (
            decision.kind is QueryKind.CURRENT_STATE
            and decision.topic is not StateTopic.OVERVIEW
        ):
            # A7C: the question is about the live home state, not about
            # history — answer from watch.last_state and never from the store.
            return _text(
                render_state_answer(
                    decision.topic.value,
                    _read_live_state(current_state),
                    lang=decision.lang,
                    polarity=decision.polarity,
                )
            )
        intent = classifier.classify(query, lang=lang_arg)
        if intent.intent is MemoryIntentType.LAST_SEEN:
            if not intent.label:
                return await search({"query": intent.query, "lang": intent.lang})
            return await last_seen(
                {
                    "label": intent.label,
                    "location": intent.location or "",
                    "lang": intent.lang,
                }
            )
        if intent.intent is MemoryIntentType.SEARCH:
            return await search(
                {
                    "query": intent.query,
                    "location": intent.location or "",
                    "lang": intent.lang,
                }
            )
        if intent.intent is MemoryIntentType.SUMMARY:
            return await summary(
                {
                    "hours": intent.hours or 24.0,
                    "location": intent.location or "",
                    "lang": intent.lang,
                }
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
    if tool_name == "memory_recall":
        # Imported lazily so the production V1 import graph stays untouched and
        # the experimental recall engine is only loaded when explicitly routed.
        from src.infrastructure.adapters.mcp.recall_resolvers import (
            build_memory_recall_resolver,
        )

        return build_memory_recall_resolver(memory)
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
