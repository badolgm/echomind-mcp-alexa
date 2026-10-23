"""Question-directed synthesis (A7B/A7D): answer the shape of the question asked.

Pipeline: data -> relations -> context -> narration -> **synthesis**. The
narrator (A6f) speaks the graded context; this module decides what *shape of
answer* the question deserves and composes it deterministically from the
trace entries the engine already produced.

A7D routes each plan through its :class:`~src.domain.services.response_intent.
ResponseIntent` (resolved by the planner, or derived from the plan's relations
and aggregation when a plan was built directly) to a renderer in one dispatch
table, so two questions that used to share one answer — a *related events*
question and a *cameras* question, say — now get the answer each one asks for:

0. ``state_topic``        -> an A7C live-state sentence rendered only from
                            the snapshot the engine read (or its honest
                            "no dispongo" when there was no live state).
   ``COUNT`` / ``BEFORE`` / ``AFTER`` -> answered without needing evidence
                            (a count, or the directional slice of ``anchor``).
   every other intent      -> needs at least one piece of evidence, else
                            abstains through the V1 narration.
1. ``LAST_SEEN_PLACE``    -> the most recent matching evidence: where it was
                            seen, by which camera, and when.
2. ``TIMELINE``           -> gap overview, event counts, evidence, context.
3. ``CAMERAS``            -> camera roster + the cameras that saw the same
                            event + narrated context.
4. ``RELATIONS``          -> how many events relate + their narrated digest.
5. ``SPATIAL``            -> place roster + evidence.
6. ``SUMMARY``            -> label counts + evidence.
7. ``FALLBACK``           -> :func:`~src.domain.services.evidence.
   render_utterance`, mandatory: when no structural answer applies the V1
   three-line evidence narration (or its abstention) is returned unchanged.

Rules held by construction: pure domain (stdlib only), bilingual, no
invention — every claim is read from executed trace entries or from the
evidence actually retrieved, and every answer stays bounded by the same
three-line ceilings V1 has always had.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from src.domain.services.context import ContextItem
from src.domain.services.context_narrative import render_context
from src.domain.services.current_state_reasoning import render_state_answer
from src.domain.services.evidence import (
    Evidence,
    format_relative_time,
    render_utterance,
)
from src.domain.services.recall_plan import Aggregation, RecallPlan, RelationKind
from src.domain.services.response_intent import ResponseIntent, derive_intent

_MAX_ANSWER_LINES = 3


def render_synthesis(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    """Compose the spoken answer for one executed plan, falling back to V1.

    The plan's response intent selects one renderer from :data:`_INTENT_RENDERERS`.
    Counts and directional slices are answered without evidence; every other
    intent needs at least one retrieved proof, and when its renderer has
    nothing to say the V1 narration (or abstention) is returned unchanged.
    """
    state = _state_line(plan, ops)
    if state:
        return state

    fallback = render_utterance(evidence, lang=lang, now=now)
    intent = _resolve_plan_intent(plan, ops)
    renderer = _INTENT_RENDERERS.get(intent)
    if renderer is None:
        return fallback
    if not evidence and intent not in _EVIDENCE_FREE_INTENTS:
        return fallback
    answer = renderer(plan, evidence, ops, context, now=now, lang=lang)
    return answer or fallback


def _resolve_plan_intent(
    plan: RecallPlan, ops: Sequence[Mapping[str, Any]]
) -> ResponseIntent:
    """The planner's intent when it set one, else the one derived structurally.

    A directly built plan (a low-level test, a programmatic caller) carries no
    intent, so it is derived from the same signals the old policy chain read —
    which keeps every pre-A7D plan rendering exactly as it did.
    """
    if plan.response_intent is not None:
        return plan.response_intent
    return derive_intent(
        aggregation=plan.aggregation.value if plan.aggregation else None,
        relations=tuple(relation.value for relation in plan.relations),
        direction=plan.direction,
        has_count=any(entry.get("aggregation") == "count" for entry in ops),
    )


def _state_line(plan: RecallPlan, ops: Sequence[Mapping[str, Any]]) -> str:
    """Policy 0 (A7C): answer the live-state topic from the snapshot alone.

    The snapshot is read back from the executed ``current_state`` op, so the
    synthesizer never touches the store and never invents: a missing or
    failing provider yields the renderer's honest "no dispongo" sentence.
    """
    if plan.state_topic is None:
        return ""
    snapshot: Mapping[str, object] = {}
    for entry in ops:
        if entry.get("op") != "retrieve:current_state":
            continue
        if entry.get("status") == "ok":
            raw = entry.get("state")
            if isinstance(raw, Mapping):
                snapshot = raw
        break
    return render_state_answer(
        plan.state_topic, snapshot, plan.lang, polarity=plan.state_polarity
    )


def _relate_entry(
    ops: Sequence[Mapping[str, Any]], relation: str
) -> Mapping[str, Any] | None:
    for entry in ops:
        if entry.get("op") == "relate" and entry.get("relation") == relation:
            return entry
    return None


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _whole(value: object) -> int | float:
    """Render a numeric trace value without a trailing ``.0``."""
    number = _number(value)
    if number == int(number):
        return int(number)
    return number


def _count_line(ops: Sequence[Mapping[str, Any]], *, lang: str) -> str:
    """An aggregate count is the whole answer to a how-many question."""
    for entry in ops:
        if entry.get("aggregation") != "count":
            continue
        filters = entry.get("filters") or {}
        entity = str(filters.get("entity") or "").strip()
        risk = str(filters.get("risk") or "").strip()
        value = _whole(entry.get("value", 0))
        english = lang == "en"
        if entity:
            if english:
                noun = "detection" if value == 1 else "detections"
                return f"{value} {entity} {noun}."
            noun = "detección" if value == 1 else "detecciones"
            return f"{value} {noun} de {entity}."
        if risk:
            if english:
                noun = "event" if value == 1 else "events"
                return f"{value} {risk} risk {noun}."
            noun = "evento" if value == 1 else "eventos"
            return f"{value} {noun} de riesgo {risk}."
        if english:
            noun = "event" if value == 1 else "events"
            return f"{value} {noun}."
        noun = "evento" if value == 1 else "eventos"
        return f"{value} {noun}."
    return ""


def _directional_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    *,
    now: float,
    lang: str,
) -> str:
    """Speak the episodes on the side of ``anchor`` the question asked for."""
    if plan.direction not in ("before", "after") or not plan.anchor:
        return ""
    if RelationKind.BEFORE_AFTER not in plan.relations:
        return ""
    entry = _relate_entry(ops, "before_after")
    if entry is None:
        return ""
    after = plan.direction == "after"
    episodes = list(entry.get("episodes_after") if after else entry.get("episodes"))
    anchor = plan.anchor
    english = lang == "en"
    if not episodes:
        if english:
            side = "after" if after else "before"
            return f"No events {side} {anchor}."
        side = "después" if after else "antes"
        return f"No hubo eventos {side} de {anchor}."
    if english:
        header = f"After {anchor}:" if after else f"Before {anchor}:"
    else:
        header = f"Después de {anchor}:" if after else f"Antes de {anchor}:"
    lines = [
        _episode_line(item, after=after, now=now, lang=lang)
        for item in episodes[:_MAX_ANSWER_LINES]
    ]
    return f"{header} {' '.join(lines)}"


def _episode_line(
    item: Mapping[str, Any], *, after: bool, now: float, lang: str
) -> str:
    labels = ", ".join(str(label) for label in (item.get("labels") or ()) if str(label))
    moment = "start" if after else "end"
    when = format_relative_time(_number(item.get(moment)), now, lang)
    location = str(item.get("location") or "")
    subject = labels or ("registro" if lang != "en" else "record")
    if location:
        preposition = "at" if lang == "en" else "en"
        return f"{subject} {preposition} {location}, {when}."
    return f"{subject}, {when}."


def _timeline_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    evidence: Sequence[Evidence],
    now: float,
    lang: str,
) -> str:
    """A session overview: how much happened, the biggest silence, then it."""
    if RelationKind.TIMELINE not in plan.relations:
        return ""
    entry = _relate_entry(ops, "timeline")
    if entry is None:
        return ""
    gaps = list(entry.get("gaps") or [])
    if not gaps:
        return ""
    episodes = list(entry.get("episodes") or [])
    longest = max(_number(gap.get("seconds")) for gap in gaps)
    parts = [
        _timeline_summary(len(episodes), len(gaps), longest, lang=lang),
    ]
    counts = _summary_counts(ops)
    if counts:
        parts.append(_counts_sentence(counts, lang=lang))
    parts.append(render_utterance(evidence, lang=lang, now=now))
    narration = render_context(context, lang=lang)
    if narration:
        parts.append(narration)
    return " ".join(part for part in parts if part)


def _summary_counts(ops: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    """The aggregate label counts behind an overview, when the plan asked for them."""
    for entry in ops:
        if entry.get("aggregation") == "summary":
            return dict(entry.get("label_counts") or {})
    return {}


def _counts_sentence(counts: Mapping[str, object], *, lang: str) -> str:
    """``Sucesos: PET 3, PERSON 3.`` — biggest first, ties by name."""
    ordered = sorted(counts.items(), key=lambda pair: (-_number(pair[1]), str(pair[0])))
    roster = ", ".join(f"{name} {_whole(count)}" for name, count in ordered)
    label = "Events" if lang == "en" else "Sucesos"
    return f"{label}: {roster}."


def _timeline_summary(episodes: int, gaps: int, longest: float, *, lang: str) -> str:
    english = lang == "en"
    if english:
        ep_word = "episode" if episodes == 1 else "episodes"
        gap_word = "pause" if gaps == 1 else "pauses"
        return (
            f"{episodes} {ep_word}, {gaps} {gap_word}; "
            f"the longest {_duration(longest, lang=lang)}."
        )
    ep_word = "episodio" if episodes == 1 else "episodios"
    gap_word = "silencio" if gaps == 1 else "silencios"
    return (
        f"{episodes} {ep_word}, {gaps} {gap_word}; "
        f"el mayor de {_duration(longest, lang=lang)}."
    )


def _duration(seconds: float, *, lang: str) -> str:
    """Human elapsed length: ``45 segundos`` / ``20 minutos`` / ``1 h 45 min``."""
    total = max(0, int(seconds))
    english = lang == "en"
    if total < 60:
        if english:
            unit = "second" if total == 1 else "seconds"
        else:
            unit = "segundo" if total == 1 else "segundos"
        return f"{total} {unit}"
    if total < 3600:
        minutes = total // 60
        if english:
            unit = "minute" if minutes == 1 else "minutes"
        else:
            unit = "minuto" if minutes == 1 else "minutos"
        return f"{minutes} {unit}"
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if minutes:
        return f"{hours} h {minutes} min"
    return f"{hours} h"


def _correlation_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    evidence: Sequence[Evidence],
    *,
    lang: str,
) -> str:
    """Name the cameras, then what they saw together."""
    if RelationKind.CORRELATION not in plan.relations:
        return ""
    entry = _relate_entry(ops, "correlation")
    if entry is None:
        return ""
    groups = dict(entry.get("groups") or {})
    if not groups:
        return ""
    roster = _groups_line(groups, en="Cameras", es="Cámaras", lang=lang)
    pair = _overlap_pair(context, evidence, lang=lang)
    if pair:
        return f"{roster} {pair}"
    narration = render_context(context, lang=lang)
    if narration:
        return f"{roster} {narration}"
    return roster


def _overlap_pair(
    context: Sequence[ContextItem],
    evidence: Sequence[Evidence],
    *,
    lang: str,
) -> str:
    """The two cameras behind the top same-moment context item, if they differ."""
    cameras = {item.record_id: item.camera_id for item in evidence}
    for item in context:
        if not item.narratable:
            continue
        if item.relation.kind != "correlation_overlapping":
            continue
        first = cameras.get(str(item.relation.subject))
        second = cameras.get(str(item.relation.object))
        if not first or not second or first == second:
            continue
        spoken = render_context([item], lang=lang)
        if not spoken:
            continue
        if lang == "en":
            return f"Cameras {first} and {second} observed the same event: {spoken}"
        return f"Las cámaras {first} y {second} vieron el mismo suceso: {spoken}"
    return ""


def _spatial_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    evidence: Sequence[Evidence],
    *,
    now: float,
    lang: str,
) -> str:
    """Where things happened, followed by the evidence that shows it."""
    if RelationKind.SPATIAL not in plan.relations:
        return ""
    entry = _relate_entry(ops, "spatial")
    if entry is None:
        return ""
    groups = dict(entry.get("groups") or {})
    if not groups:
        return ""
    roster = _groups_line(groups, en="Places", es="Lugares", lang=lang)
    return f"{roster} {render_utterance(evidence, lang=lang, now=now)}"


def _summary_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    evidence: Sequence[Evidence],
    *,
    now: float,
    lang: str,
) -> str:
    """A summary question gets its counts, with the records below them."""
    if plan.aggregation is not Aggregation.SUMMARY:
        return ""
    entry = next((item for item in ops if item.get("aggregation") == "summary"), None)
    if entry is None:
        return ""
    counts = dict(entry.get("label_counts") or {})
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda pair: (-_number(pair[1]), str(pair[0])))
    roster = ", ".join(f"{name} {_whole(count)}" for name, count in ordered)
    label = "Summary" if lang == "en" else "Resumen"
    return f"{label}: {roster}. {render_utterance(evidence, lang=lang, now=now)}"


def _groups_line(groups: Mapping[str, Any], *, en: str, es: str, lang: str) -> str:
    """``Cámaras: cam-1 (6), cam-2 (1).`` — biggest group first, ties by name."""
    ordered = sorted(groups.items(), key=lambda pair: (-len(pair[1]), str(pair[0])))
    roster = ", ".join(f"{name} ({len(ids)})" for name, ids in ordered)
    label = en if lang == "en" else es
    return f"{label}: {roster}."


# --- last seen at a place (A7D) ---------------------------------------------


_LABEL_NOUNS_ES: dict[str, str] = {
    "PET": "una mascota",
    "PERSON": "una persona",
    "PERSON_ELDERLY": "una persona mayor",
    "GATE_OPEN": "la reja abierta",
    "DOOR_OPEN": "la puerta abierta",
    "SMOKE": "humo",
    "FIRE": "fuego",
    "FALL DETECTED": "una caída",
    "MOTION": "movimiento",
}

_LABEL_NOUNS_EN: dict[str, str] = {
    "PET": "a pet",
    "PERSON": "a person",
    "PERSON_ELDERLY": "an elderly person",
    "GATE_OPEN": "the gate open",
    "DOOR_OPEN": "the door open",
    "SMOKE": "smoke",
    "FIRE": "fire",
    "FALL DETECTED": "a fall",
    "MOTION": "motion",
}


def _plan_label(plan: RecallPlan) -> str | None:
    """The label slot the planner attached to the question, if any."""
    for slot in plan.entities:
        if slot.kind == "label":
            return slot.value
    return None


def _last_seen_place_line(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    """Say where something was last seen, by which camera, and when."""
    if not evidence:
        return ""
    label = _plan_label(plan)
    matching = [item for item in evidence if not label or label in item.labels]
    latest = max(matching or evidence, key=lambda item: item.ts)
    noun = _label_noun(label, latest, lang=lang)
    when = format_relative_time(latest.ts, now, lang)
    place = latest.location or latest.zone or ""
    camera = latest.camera_id or ""
    english = lang == "en"
    if english:
        line = f"The last time I saw {noun} was"
        if place:
            line += f" in {place}"
        if camera:
            line += f" (camera {camera})"
        line += f", {when}."
    else:
        line = f"La última vez que vi {noun} fue"
        if place:
            line += f" en {place}"
        if camera:
            line += f" (cámara {camera})"
        line += f", {when}."
    narration = render_context(context, lang=lang)
    if narration:
        return f"{line} {narration}"
    return line


def _label_noun(label: str | None, evidence: Evidence, *, lang: str) -> str:
    """A spoken noun for the label, falling back to the label or the record."""
    table = _LABEL_NOUNS_EN if lang == "en" else _LABEL_NOUNS_ES
    if label and label in table:
        return table[label]
    if label:
        return label
    if evidence.labels:
        return evidence.labels[0]
    return "record" if lang == "en" else "registro"


# --- related events (A7D) ----------------------------------------------------


def _relations_line(
    plan: RecallPlan,
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    lang: str,
) -> str:
    """Read the relation digest the engine already built for the answer."""
    entry = _relate_entry(ops, "derived")
    count = int(_number(entry.get("count"))) if entry is not None else 0
    narration = render_context(context, lang=lang)
    head = "Related events" if lang == "en" else "Eventos relacionados"
    if narration:
        return f"{head}: {narration}"
    if count:
        return f"{count} {head.lower()}." if lang == "en" else f"{count} {head}."
    return ""


# --- intent dispatch table (A7D) ---------------------------------------------


def _render_count(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _count_line(ops, lang=lang)


def _render_directional(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _directional_line(plan, ops, now=now, lang=lang)


def _render_last_seen_place(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _last_seen_place_line(plan, evidence, context, now=now, lang=lang)


def _render_timeline(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _timeline_line(plan, ops, context, evidence=evidence, now=now, lang=lang)


def _render_relations(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _relations_line(plan, ops, context, lang=lang)


def _render_cameras(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _correlation_line(plan, ops, context, evidence, lang=lang)


def _render_spatial(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _spatial_line(plan, ops, evidence, now=now, lang=lang)


def _render_summary(
    plan: RecallPlan,
    evidence: Sequence[Evidence],
    ops: Sequence[Mapping[str, Any]],
    context: Sequence[ContextItem],
    *,
    now: float,
    lang: str,
) -> str:
    return _summary_line(plan, ops, evidence, now=now, lang=lang)


_INTENT_RENDERERS: dict[
    ResponseIntent,
    Callable[..., str],
] = {
    ResponseIntent.COUNT: _render_count,
    ResponseIntent.BEFORE: _render_directional,
    ResponseIntent.AFTER: _render_directional,
    ResponseIntent.LAST_SEEN_PLACE: _render_last_seen_place,
    ResponseIntent.TIMELINE: _render_timeline,
    ResponseIntent.RELATIONS: _render_relations,
    ResponseIntent.CAMERAS: _render_cameras,
    ResponseIntent.SPATIAL: _render_spatial,
    ResponseIntent.SUMMARY: _render_summary,
}

_EVIDENCE_FREE_INTENTS: frozenset[ResponseIntent] = frozenset(
    {ResponseIntent.COUNT, ResponseIntent.BEFORE, ResponseIntent.AFTER}
)
