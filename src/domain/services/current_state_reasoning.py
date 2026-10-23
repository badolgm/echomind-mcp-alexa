"""Honest current-state answers built only from the live snapshot (A7C).

Pure domain layer (standard library only). One deterministic sentence per
state topic, derived **exclusively** from real fields of the watchdog
snapshot (``watch.last_state``): ``gate_open``, ``door_open``,
``temperature_c``, ``risk`` and the live ``detections`` list.

Guarantees by construction:

* never touches ``search_memory`` / ``last_seen`` / timelines — there is no
  call to any store in this module;
* never invents: a missing field yields an honest "no dispongo" sentence;
* no LLM, no wall clock, no placeholders — just the fields that are there.

The ``polarity`` (the open/closed property the question itself asserts) only
chooses the ``Sí/No`` prefix; the reported fact never changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Mapping

from src.domain.services.query_router import StateTopic

_Renderer = Callable[..., str | None]

_UNAVAILABLE: dict[StateTopic, tuple[str, str]] = {
    StateTopic.GATE: (
        "No dispongo del estado actual de la reja.",
        "I don't have the current state of the gate.",
    ),
    StateTopic.DOOR: (
        "No dispongo del estado actual de la puerta.",
        "I don't have the current state of the door.",
    ),
    StateTopic.MOTION: (
        "No dispongo del estado actual del movimiento.",
        "I don't have the current state of the motion.",
    ),
    StateTopic.TEMPERATURE: (
        "No dispongo de la temperatura actual.",
        "I don't have the current temperature.",
    ),
    StateTopic.RISK: (
        "No dispongo del nivel de riesgo actual.",
        "I don't have the current risk level.",
    ),
    StateTopic.SMOKE: (
        "No dispongo del estado actual del humo.",
        "I don't have the current state of the smoke.",
    ),
    StateTopic.OVERVIEW: (
        "No dispongo del estado actual de la vivienda.",
        "I don't have the current state of the home.",
    ),
}

_LABEL_PHRASES_ES: dict[str, str] = {
    "GATE_OPEN": "reja abierta",
    "DOOR_OPEN": "puerta abierta",
    "MOTION": "movimiento",
    "SMOKE": "humo",
    "FIRE": "fuego",
    "PET_ESCAPING": "mascota intentando escapar",
    "TEMP_RISING": "temperatura elevada",
    "PERSON": "una persona",
    "PERSON_ELDERLY": "una persona mayor",
    "PET": "una mascota",
    "FALL DETECTED": "una caída",
}

_LABEL_PHRASES_EN: dict[str, str] = {
    "GATE_OPEN": "an open gate",
    "DOOR_OPEN": "an open door",
    "MOTION": "motion",
    "SMOKE": "smoke",
    "FIRE": "fire",
    "PET_ESCAPING": "a pet trying to escape",
    "TEMP_RISING": "rising temperature",
    "PERSON": "a person",
    "PERSON_ELDERLY": "an elderly person",
    "PET": "a pet",
    "FALL DETECTED": "a fall",
}


def _labels(state: Mapping[str, object]) -> list[str]:
    """Canonical labels of the live detections, in snapshot order."""
    labels: list[str] = []
    detections = state.get("detections") or ()
    if not isinstance(detections, (list, tuple)):
        return labels
    for item in detections:
        if isinstance(item, dict):
            label = str(item.get("label") or "")
            if label:
                labels.append(label)
    return labels


def _prefix(agrees: bool | None, english: bool) -> str:
    if agrees is None:
        return ""
    if english:
        return "Yes. " if agrees else "No. "
    return "Sí. " if agrees else "No. "


def _agreement(is_open: bool, polarity: str | None) -> bool | None:
    if polarity == "open":
        return is_open
    if polarity == "closed":
        return not is_open
    return None


def _render_open_closed(
    state: Mapping[str, object],
    *,
    english: bool,
    polarity: str | None,
    key: str,
    noun_es: str,
    noun_en: str,
) -> str | None:
    if key not in state:
        return None
    is_open = bool(state[key])
    agrees = _agreement(is_open, polarity)
    if english:
        if is_open:
            body = f"The {noun_en} is open right now."
        else:
            body = f"The {noun_en} is currently closed."
        return _prefix(agrees, True) + body
    if is_open:
        body = f"La {noun_es} está abierta ahora mismo."
    else:
        body = f"La {noun_es} se encuentra cerrada actualmente."
    return _prefix(agrees, False) + body


def _render_gate(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    return _render_open_closed(
        state,
        english=english,
        polarity=polarity,
        key="gate_open",
        noun_es="reja",
        noun_en="gate",
    )


def _render_door(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    return _render_open_closed(
        state,
        english=english,
        polarity=polarity,
        key="door_open",
        noun_es="puerta",
        noun_en="door",
    )


def _render_motion(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    if "detections" not in state:
        return None
    active = "MOTION" in _labels(state)
    if english:
        if active:
            return "Yes, I detect active motion."
        return "I detect no active motion."
    if active:
        return "Sí, detecto movimiento activo."
    return "No detecto movimiento activo."


def _render_temperature(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    if "temperature_c" not in state:
        return None
    try:
        value = float(state["temperature_c"])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    text = f"{value:g}"
    if english:
        return f"The current temperature is {text}°C."
    return f"La temperatura actual es {text}°C."


def _render_risk(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    if "risk" not in state:
        return None
    level = str(state["risk"] or "").strip()
    if not level:
        return None
    if english:
        return f"The current risk level is {level}."
    return f"El nivel de riesgo actual es {level}."


def _render_smoke(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    if "detections" not in state:
        return None
    labels = _labels(state)
    active = "SMOKE" in labels or "FIRE" in labels
    if english:
        if active:
            return "Yes, I detect active smoke."
        return "I detect no active smoke."
    if active:
        return "Sí, detecto humo activo."
    return "No detecto humo activo."


def _render_overview(
    state: Mapping[str, object], *, english: bool, polarity: str | None
) -> str | None:
    if not state:
        return None
    parts: list[str] = []

    risk_sentence = _render_risk(state, english=english, polarity=None)
    if risk_sentence is not None:
        parts.append(risk_sentence)

    if "detections" in state:
        labels = _labels(state)
        if labels:
            table = _LABEL_PHRASES_EN if english else _LABEL_PHRASES_ES
            phrases = [table.get(label, label.lower()) for label in labels]
            if english:
                parts.append(f"I detect {', '.join(phrases)}.")
            else:
                parts.append(f"Detecto {', '.join(phrases)}.")
        elif english:
            parts.append("I detect no active incidents.")
        else:
            parts.append("No detecto incidencias activas.")

    temperature_sentence = _render_temperature(state, english=english, polarity=None)
    if temperature_sentence is not None:
        parts.append(temperature_sentence)

    if not parts:
        return None
    return " ".join(parts)


_RENDERERS: dict[StateTopic, _Renderer] = {
    StateTopic.GATE: _render_gate,
    StateTopic.DOOR: _render_door,
    StateTopic.MOTION: _render_motion,
    StateTopic.TEMPERATURE: _render_temperature,
    StateTopic.RISK: _render_risk,
    StateTopic.SMOKE: _render_smoke,
    StateTopic.OVERVIEW: _render_overview,
}


def render_state_answer(
    topic: str,
    state: Mapping[str, object],
    lang: str = "es",
    *,
    polarity: str | None = None,
) -> str:
    """Render one honest sentence for ``topic`` from the live ``state``.

    ``topic`` is a ``StateTopic`` value; an unknown value still degrades to
    an honest non-answer instead of guessing. ``lang`` selects ``es`` or
    ``en`` (anything else falls back to Spanish, like the rest of EchoMind).
    """
    try:
        resolved = StateTopic(str(topic))
    except ValueError:
        return (
            "No dispongo de una respuesta de estado para esa consulta."
            if lang != "en"
            else "I don't have a state answer for that question."
        )
    english = lang == "en"
    renderer = _RENDERERS[resolved]
    sentence = renderer(state, english=english, polarity=polarity)
    if sentence is None:
        return _UNAVAILABLE[resolved][0 if not english else 1]
    return sentence
