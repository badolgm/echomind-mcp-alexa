"""Deterministic memory-intent classification for conversational Alexa.

Pure domain logic (standard library only): maps a natural-language Spanish
question about the home's history onto a concrete :class:`MemoryIntent` that
the infrastructure can serve from local structured memory — never from an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class MemoryIntentType(Enum):
    """The recalled capability a memory question asks for."""

    LAST_SEEN = "last_seen"
    SEARCH = "search"
    SUMMARY = "summary"
    TOP_EVENTS = "top_events"
    HIGH_RISK = "high_risk"
    CRITICAL_RISK = "critical_risk"
    EVENT_COUNT = "event_count"
    CURRENT_STATE = "current_state"


@dataclass(frozen=True, slots=True)
class MemoryIntent:
    """The parsed shape of one natural-language memory question."""

    intent: MemoryIntentType
    query: str
    label: str | None = None
    hours: float | None = None
    risk: str | None = None
    location: str | None = None


_LABEL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "PERSON_ELDERLY",
        ("persona mayor", "personas mayores", "anciano", "anciana", "abuelo", "abuela"),
    ),
    ("GATE_OPEN", ("reja", "portón", "porton", "cancela")),
    ("DOOR_OPEN", ("puerta",)),
    ("PET", ("mascota", "mascotas", "perro", "perros", "gato", "gatos", "animal")),
    ("PERSON", ("persona", "personas", "hombre", "mujer", "gente")),
    ("MOTION", ("movimiento",)),
    ("SMOKE", ("humo",)),
    ("FIRE", ("fuego", "incendio")),
)

_CURRENT_PHRASES = (
    "qué ocurre",
    "que ocurre",
    "qué está ocurriendo",
    "qué esta ocurriendo",
    "qué pasa",
    "que pasa",
    "qué está pasando",
    "qué esta pasando",
    "qué sucede",
    "que sucede",
)

_TOP_PHRASES = (
    "más importantes",
    "mas importantes",
    "más importante",
    "mas importante",
    "más relevantes",
    "mas relevantes",
)

_HIGH_RISK_PHRASES = (
    "situaciones de riesgo",
    "eventos de alto riesgo",
    "alto riesgo",
    "situaciones de peligro",
)

_SUMMARY_PHRASES = (
    "recuerdas",
    "resumen",
    "qué ocurrió",
    "que ocurrió",
    "qué ha pasado",
    "que ha pasado",
    "durante las últimas",
    "últimas 2",
    "ha ocurrido antes",
    "ocurrido antes",
    "qué pasó",
    "que pasó",
    "qué ha ocurrido",
    "que ha ocurrido",
)

_HOURS_RE = re.compile(r"últimas?\s+(\d+)\s+horas?")
_CRITICAL_RE = re.compile(r"cr[ií]tic[oa]s?|critical")
_COUNT_RE = re.compile(r"cu[aá]ntos?\s+(eventos?|alertas?|situaciones?)")
_LAST_SEEN_RE = re.compile(
    r"recientemente|cu[aá]ndo\s+v(?:iste|io)|ha estado|última vez|últimamente|por últim"
)


class MemoryIntentClassifier:
    """String-rule classifier routing memory questions to capabilities."""

    def classify(self, text: str) -> MemoryIntent:
        query = text.strip()
        normalized = " ".join(query.lower().split())
        if not normalized:
            return MemoryIntent(MemoryIntentType.SEARCH, query=query)

        if self._contains(normalized, _CURRENT_PHRASES):
            return MemoryIntent(MemoryIntentType.CURRENT_STATE, query=query)

        if _COUNT_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.EVENT_COUNT,
                query=query,
                risk=self._extract_risk(normalized),
                hours=self._extract_hours(normalized),
            )

        if self._contains(normalized, _TOP_PHRASES):
            return MemoryIntent(
                MemoryIntentType.TOP_EVENTS,
                query=query,
                hours=self._extract_hours(normalized),
            )

        if self._contains(normalized, _HIGH_RISK_PHRASES):
            return MemoryIntent(
                MemoryIntentType.HIGH_RISK,
                query=query,
                hours=self._extract_hours(normalized),
            )

        if _CRITICAL_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.CRITICAL_RISK,
                query=query,
                hours=self._extract_hours(normalized),
            )

        if _LAST_SEEN_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.LAST_SEEN,
                query=query,
                label=self._extract_label(normalized),
                location=self._extract_location(normalized),
            )

        if self._contains(normalized, _SUMMARY_PHRASES):
            return MemoryIntent(
                MemoryIntentType.SUMMARY,
                query=query,
                hours=self._extract_hours(normalized) or 24.0,
            )

        return MemoryIntent(
            MemoryIntentType.SEARCH,
            query=query,
            hours=self._extract_hours(normalized),
        )

    @staticmethod
    def _contains(normalized: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _extract_label(normalized: str) -> str | None:
        for label, terms in _LABEL_TERMS:
            if any(term in normalized for term in terms):
                return label
        return None

    @staticmethod
    def _extract_hours(normalized: str) -> float | None:
        match = _HOURS_RE.search(normalized)
        return float(match.group(1)) if match else None

    @staticmethod
    def _extract_risk(normalized: str) -> str | None:
        if _CRITICAL_RE.search(normalized):
            return "CRITICAL"
        if "high" in normalized:
            return "HIGH"
        if "medio" in normalized:
            return "MEDIUM"
        return None

    @staticmethod
    def _extract_location(normalized: str) -> str | None:
        match = re.search(r"en\s+(?:el|la|mi)\s+([a-záéíóúñ]+)", normalized)
        if match:
            return match.group(1)
        match = re.search(r"en\s+(cam-?\d+)", normalized)
        if match:
            return match.group(1)
        return None
