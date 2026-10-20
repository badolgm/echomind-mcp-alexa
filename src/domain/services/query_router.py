"""Deterministic query router: current state vs memory recall (A7C).

Pure domain layer (standard library only). Every question passes through this
module **first** and leaves as exactly one of two domains:

* ``CURRENT_STATE`` — the answer must be built from the live home snapshot
  (``watch.last_state``) and may never touch stored records;
* ``RECALL`` — the historical pipelines (V1 ``MemoryIntentClassifier`` and the
  V2 recall planner) then run exactly as they always have.

Classification is table driven, following the same philosophy as
``recall_planner``: word-bounded regex tables composed by one precedence
rule (first match wins)::

    count > memory-anchor > past > subject+present > overview > default

``RECALL`` is the safe default, so a question with no present-state signal is
answered by the memory pipelines exactly as it was before A7C. The tables:

* ``_STATE_SUBJECTS`` — the concrete snapshot topics (gate, door, motion,
  temperature, risk, smoke) a present-state question can ask about;
* ``_PRESENT_MARKERS`` — words that anchor a sentence in the present;
* ``_PAST_MARKERS`` — words that anchor a question in history: they beat any
  present marker, which is what keeps memory questions out of the state path;
* ``_OVERVIEW_PHRASES`` — broad "what is happening" phrasings without a
  concrete subject;
* ``_MEMORY_ANCHORS`` / ``_PERSON_ANCHORS`` — where/who framings that are
  always history (spatial recall), except that a person anchor only vetoes the
  gate/door topics (state of a thing), never motion (movement of someone is
  still movement).

No LLM, no wall clock, no state: ``route_query`` is a pure function of the
text (and the caller's language, when given).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.domain.services.memory_intent import MemoryIntentClassifier


class QueryKind(Enum):
    """Which truth source can answer one question."""

    CURRENT_STATE = "current_state"
    RECALL = "recall"


class StateTopic(Enum):
    """The concrete aspect of the live snapshot a state question asks for."""

    GATE = "gate"
    DOOR = "door"
    MOTION = "motion"
    TEMPERATURE = "temperature"
    RISK = "risk"
    SMOKE = "smoke"
    OVERVIEW = "overview"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Where one question goes, in which language, and why (for traces).

    ``polarity`` is the property the question itself asserts about an
    entry ("open" / "closed"): the answerer uses it to prefix ``Sí/No``
    without ever changing the fact it reports. ``None`` when the question
    asked for no such property.
    """

    kind: QueryKind
    topic: StateTopic | None
    lang: str
    matched: tuple[str, ...]
    polarity: str | None = None


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in patterns)


_STATE_SUBJECTS: tuple[tuple[StateTopic, re.Pattern[str]], ...] = (
    (
        StateTopic.GATE,
        re.compile(
            r"\b(?:reja|rejas|port[oó]n|port[oó]nes|cancela|cancelas|gate|gates)\b"
        ),
    ),
    (StateTopic.DOOR, re.compile(r"\b(?:puerta|puertas|door|doors)\b")),
    (
        StateTopic.MOTION,
        re.compile(r"\b(?:movimiento|movimientos|moviendo|motion|moving|movement)\b"),
    ),
    (
        StateTopic.TEMPERATURE,
        re.compile(
            r"\b(?:temperatura|temperaturas|temperature|temperatures|"
            r"grados|degrees|fr[ií]o|frio|cold)\b"
        ),
    ),
    (
        StateTopic.RISK,
        re.compile(r"\b(?:riesgo|riesgos|risk|risks|peligro|danger)\b"),
    ),
    (StateTopic.SMOKE, re.compile(r"\b(?:humo|humos|smoke|smokes)\b")),
)

_PRESENT_MARKERS: tuple[re.Pattern[str], ...] = _compile(
    (
        r"\best[áa]\b",
        r"\bestán\b",
        r"\bse encuentra\b",
        r"\bhay\b",
        r"\bhace\b",
        r"\bahora\b",
        r"\bahorita\b",
        r"\ben este momento\b",
        r"\bactualmente\b",
        r"\bactual\b",
        r"\ben curso\b",
        r"\blleva\b",
        r"\bes\b",
        r"\babiert[oa]s?\b",
        r"\bcerrad[oa]s?\b",
        r"\bwhat'?s\b",
        r"\bis\b",
        r"\bare\b",
        r"\bnow\b",
        r"\bcurrently\b",
        r"\bopen\b",
        r"\bclosed\b",
    )
)

_PAST_MARKERS: tuple[re.Pattern[str], ...] = _compile(
    (
        r"\bcu[aá]ndo\b",
        r"\bantes\b",
        r"\bdespu[eé]s\b",
        r"\bdespues\b",
        r"\bmientras\b",
        r"\bocurri(?:[óo]|id|ier)",
        r"\bocurr[íi]a",
        r"\bpas[óo]\b",
        r"\bpasado\b",
        r"\bhubo\b",
        r"\bhab[ií]a\b",
        r"\bha estado\b",
        r"\bestuv(?:e|o|imos|ieron)\b",
        r"\bestab(?:a|an|as)\b",
        r"\bqued(?:[óo]|aron|aba)\b",
        r"\bdej(?:aste|aron|[óo])\b",
        r"\bviste\b",
        r"\bmoviste\b",
        r"\bmovi[óo]\b",
        r"\bvio\b",
        r"\bvi\b",
        r"\bleft\b",
        r"\bayer\b",
        r"\brecientemente\b",
        r"\b[úu]ltima vez\b",
        r"\bwhen\b",
        r"\bbefore\b",
        r"\bafter\b",
        r"\bwhile\b",
        r"\bhappened\b",
        r"\boccurred\b",
        r"\bwas\b",
        r"\bwere\b",
        r"\bhas been\b",
        r"\byesterday\b",
        r"\blast\b",
    )
)

_MEMORY_ANCHORS: tuple[re.Pattern[str], ...] = _compile(
    (
        r"\bdónde\b",
        r"\bdonde\b",
        r"\bwhere\b",
        r"\bquien\b",
        r"\bqui[eé]n\b",
        r"\bwho\b",
        r"\ben (?:el|la|the) (?:lugar|zona|place|spot)\b",
    )
)

_PERSON_ANCHORS: tuple[re.Pattern[str], ...] = _compile(
    (r"\balguien\b", r"\bnadie\b", r"\bsomeone\b", r"\banyone\b")
)

_COUNT_MARKER = re.compile(
    r"(?:cu[aá]ntos?|how\s+many)\s+(?:[a-z0-9_-]+\s+)*"
    r"(?:eventos?|alertas?|situaciones?|events?|alerts?)"
)

_OVERVIEW_PHRASES: tuple[re.Pattern[str], ...] = _compile(
    (
        r"qu[eé]\s+ocurre",
        r"qu[eé]\s+pasa\b",
        r"qu[eé]\s+est[áa]\s+(?:pasando|ocurriendo)",
        r"qu[eé]\s+esta\s+(?:pasando|ocurriendo)",
        r"qu[eé]\s+sucede",
        r"what(?:'?s?|\s+is)\s+happening",
        r"what(?:'?s?|\s+is)\s+going\s+on",
        r"what\s+is\s+occurring",
        r"current\s+state",
        r"right\s+now",
    )
)

_PERSON_VETO_TOPICS = frozenset({StateTopic.GATE, StateTopic.DOOR})

_OPEN_WORDS: tuple[re.Pattern[str], ...] = _compile((r"\babiert", r"\bopen\b"))

_CLOSED_WORDS: tuple[re.Pattern[str], ...] = _compile((r"\bcerrad", r"\bclosed\b"))


def _detect_polarity(normalized: str) -> str | None:
    """The open/closed property the question itself asks about, if any."""
    opened = _first_match(_OPEN_WORDS, normalized)
    closed = _first_match(_CLOSED_WORDS, normalized)
    if (opened is None) == (closed is None):
        return None
    return "open" if opened is not None else "closed"


def _first_match(patterns: tuple[re.Pattern[str], ...], normalized: str) -> str | None:
    for pattern in patterns:
        found = pattern.search(normalized)
        if found is not None:
            return found.group(0)
    return None


def _recall(lang: str, matched: str) -> RouteDecision:
    return RouteDecision(QueryKind.RECALL, None, lang, (matched,))


def route_query(text: str, lang: str | None = None) -> RouteDecision:
    """Decide whether one question is answered by state or by memory.

    Precedence (first match wins): count > memory anchor > past >
    subject+present > overview > default recall. Language detection reuses the
    proven ``MemoryIntentClassifier`` so both channels always agree on ``es``
    versus ``en``.
    """
    query = str(text)
    normalized = " ".join(query.lower().split())
    detected_lang = MemoryIntentClassifier().classify(query, lang).lang

    if not normalized:
        return _recall(detected_lang, "empty")

    count = _COUNT_MARKER.search(normalized)
    if count is not None:
        return _recall(detected_lang, f"count:{count.group(0)}")

    anchor = _first_match(_MEMORY_ANCHORS, normalized)
    if anchor is not None:
        return _recall(detected_lang, f"anchor:{anchor}")

    past = _first_match(_PAST_MARKERS, normalized)
    if past is not None:
        return _recall(detected_lang, f"past:{past}")

    person = _first_match(_PERSON_ANCHORS, normalized)
    for topic, subject_pattern in _STATE_SUBJECTS:
        subject = subject_pattern.search(normalized)
        if subject is None:
            continue
        present = _first_match(_PRESENT_MARKERS, normalized)
        if present is None:
            continue
        if topic in _PERSON_VETO_TOPICS and person is not None:
            continue
        return RouteDecision(
            QueryKind.CURRENT_STATE,
            topic,
            detected_lang,
            (f"subject:{subject.group(0)}", f"present:{present}"),
            polarity=_detect_polarity(normalized),
        )

    overview = _first_match(_OVERVIEW_PHRASES, normalized)
    if overview is not None:
        return RouteDecision(
            QueryKind.CURRENT_STATE,
            StateTopic.OVERVIEW,
            detected_lang,
            (f"overview:{overview}",),
            polarity=_detect_polarity(normalized),
        )

    return _recall(detected_lang, "default")
