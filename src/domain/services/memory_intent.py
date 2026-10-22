"""Deterministic memory-intent classification for conversational Alexa.

Pure domain logic (standard library only): maps a natural-language Spanish or
English question about the home's history onto a concrete :class:`MemoryIntent`
that the infrastructure can serve from local structured memory — never from an LLM.
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
    lang: str = "es"


_LABEL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "PERSON_ELDERLY",
        (
            "persona mayor",
            "personas mayores",
            "anciano",
            "anciana",
            "abuelo",
            "abuela",
            "elderly",
            "senior",
            "grandfather",
            "grandmother",
        ),
    ),
    ("GATE_OPEN", ("reja", "portón", "porton", "cancela", "gate", "front gate")),
    ("DOOR_OPEN", ("puerta", "door", "front door")),
    (
        "PET",
        (
            "mascota",
            "mascotas",
            "perro",
            "perros",
            "gato",
            "gatos",
            "animal",
            "pet",
            "pets",
            "dog",
            "dogs",
            "cat",
            "cats",
        ),
    ),
    (
        "PERSON",
        (
            "persona",
            "personas",
            "hombre",
            "mujer",
            "gente",
            "person",
            "people",
            "someone",
            "human",
        ),
    ),
    ("MOTION", ("movimiento", "motion", "movement")),
    ("SMOKE", ("humo", "smoke")),
    ("FIRE", ("fuego", "incendio", "fire")),
    ("FALL DETECTED", ("caída", "caida", "fall", "fall detected")),
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
    "what is happening",
    "what's happening",
    "what is going on",
    "what's going on",
    "what is occurring",
    "current state",
    "right now",
)

_TOP_PHRASES = (
    "más importantes",
    "mas importantes",
    "más importante",
    "mas importante",
    "más relevantes",
    "mas relevantes",
    "most important",
    "top events",
    "key events",
    "main events",
)

_HIGH_RISK_PHRASES = (
    "situaciones de riesgo",
    "eventos de alto riesgo",
    "alto riesgo",
    "situaciones de peligro",
    "risk situations",
    "high risk",
    "high-risk",
    "dangerous situations",
    "danger",
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
    "what happened",
    "what occurred",
    "summary",
    "summarize",
    "recap",
    "today",
    "remember",
    "during the last",
    "past 24 hours",
    "last 24 hours",
)

_HOURS_RE = re.compile(r"(?:últimas?|last|past)\s+(\d+)\s+(?:horas?|hours?)")
_CRITICAL_RE = re.compile(r"cr[ií]tic[oa]s?|critical")
_COUNT_RE = re.compile(
    r"(?:cu[aá]ntos?|how\s+many)\s+(?:[a-z0-9_-]+\s+)*"
    r"(?:eventos?|alertas?|situaciones?|events?|alerts?)"
)
_LAST_SEEN_RE = re.compile(
    r"recientemente|recently|cu[aá]ndo\s+v(?:iste|io)|"
    r"when\s+did\s+you\s+(?:last\s+)?see|when\s+did\s+you\s+see|when\s+was|"
    r"ha estado|última vez|last\s+seen|last\s+time|últimamente|por últim"
)
_SPANISH_HINTS = re.compile(
    r"[áéíóúñ]|¿|¡|\b(cu[aá]ndo|qu[eé]|reja|puerta|mascota|persona|abuelo|"
    r"anciano|movimiento|humo|fuego|pasado|ocurrido|recuerdas|hoy|ayer|"
    r"últim[ao])\b"
)
_ENGLISH_HINTS = re.compile(
    r"\b(when|what|where|who|how|is|was|were|did|see|seen|last|today|"
    r"yesterday|gate|door|pet|dog|cat|smoke|fire|critical|happened|"
    r"occurred|summary|recap|hours|events|alerts?|danger|at|in)\b"
)


class MemoryIntentClassifier:
    """String-rule classifier routing memory questions to capabilities."""

    def classify(self, text: str, lang: str | None = None) -> MemoryIntent:
        query = text.strip()
        normalized = " ".join(query.lower().split())

        chosen_lang = lang.lower().strip() if lang else None
        if chosen_lang not in ("en", "es"):
            if _SPANISH_HINTS.search(normalized):
                chosen_lang = "es"
            elif _ENGLISH_HINTS.search(normalized):
                chosen_lang = "en"
            else:
                chosen_lang = "es"

        if not normalized:
            return MemoryIntent(MemoryIntentType.SEARCH, query=query, lang=chosen_lang)

        if self._contains(normalized, _CURRENT_PHRASES):
            return MemoryIntent(
                MemoryIntentType.CURRENT_STATE, query=query, lang=chosen_lang
            )

        if _COUNT_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.EVENT_COUNT,
                query=query,
                risk=self._extract_risk(normalized),
                hours=self._extract_hours(normalized),
                lang=chosen_lang,
            )

        if self._contains(normalized, _TOP_PHRASES):
            return MemoryIntent(
                MemoryIntentType.TOP_EVENTS,
                query=query,
                hours=self._extract_hours(normalized),
                lang=chosen_lang,
            )

        if self._contains(normalized, _HIGH_RISK_PHRASES):
            return MemoryIntent(
                MemoryIntentType.HIGH_RISK,
                query=query,
                hours=self._extract_hours(normalized),
                lang=chosen_lang,
            )

        if _CRITICAL_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.CRITICAL_RISK,
                query=query,
                hours=self._extract_hours(normalized),
                lang=chosen_lang,
            )

        if _LAST_SEEN_RE.search(normalized):
            return MemoryIntent(
                MemoryIntentType.LAST_SEEN,
                query=query,
                label=self._extract_label(normalized),
                location=self._extract_location(normalized),
                lang=chosen_lang,
            )

        if self._contains(normalized, _SUMMARY_PHRASES):
            return MemoryIntent(
                MemoryIntentType.SUMMARY,
                query=query,
                location=self._extract_location(normalized),
                hours=self._extract_hours(normalized) or 24.0,
                lang=chosen_lang,
            )

        return MemoryIntent(
            MemoryIntentType.SEARCH,
            query=query,
            location=self._extract_location(normalized),
            hours=self._extract_hours(normalized),
            lang=chosen_lang,
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
        if "high" in normalized or "alto" in normalized:
            return "HIGH"
        if "medio" in normalized or "medium" in normalized:
            return "MEDIUM"
        if "bajo" in normalized or "low" in normalized:
            return "LOW"
        return None

    @staticmethod
    def _extract_location(normalized: str) -> str | None:
        stop_words = frozenset(
            {
                "cam",
                "the",
                "a",
                "an",
                "el",
                "la",
                "un",
                "una",
                "was",
                "did",
                "you",
                "is",
                "are",
                "were",
                "see",
                "seen",
                "open",
                "closed",
                "gate",
                "door",
                "pet",
                "dog",
                "cat",
                "last",
                "today",
                "yesterday",
                "reja",
                "puerta",
                "casa",
            }
        )
        match_cam = re.search(r"\b(?:en|at|in)\s+(cam-?\d+)\b", normalized)
        if match_cam:
            return match_cam.group(1)

        match = re.search(
            r"\b(?:en|at|in)\s+(?:el|la|mi|the)?\s*([a-záéíóúñ]+)\b", normalized
        )
        if match:
            loc = match.group(1).strip()
            if loc not in stop_words and len(loc) > 2:
                return loc
        return None
