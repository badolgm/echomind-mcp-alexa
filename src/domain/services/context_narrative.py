"""Contextual narration (A6f): the first layer allowed to produce words.

Pipeline: data -> relations -> context -> narration. This module is the last
arrow, and it consumes exactly one thing: :class:`ContextItem`. It never reads
the raw relation graph, never reaches into the audit trace and never touches
the V1 narration.

Three deliberate limits:

* **Signal decides, narration speaks.** Only items whose salience clears
  :data:`~src.domain.services.context.NARRATION_MIN` become sentences, which
  today means ``temporal.transition`` and ``correlation.overlapping`` — the two
  a human perceives as context. Everything else stays in ``context`` as data.
  ``signal`` (the wider grade) orders the queue that arrives already ranked;
  ``narratable`` decides what may be spoken.
* **Degradation is said out loud.** A sentence resting on an approximated
  identity carries the marker instead of stating the guess as fact.
* **Bounded.** At most :data:`MAX_NARRATION_ITEMS` sentences, mirroring the
  three-line ceiling V1 narration has always had.

Output is deterministic, bilingual and never invents: every claim comes from
``relation.facts``.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.services.context import ContextItem

MAX_NARRATION_ITEMS = 3
"""Most sentences produced for one recollection, matching V1's ``_MAX_LINES``."""

_DEGRADED_ES = " (identidad aproximada)"
_DEGRADED_EN = " (approximate identity)"


def _count(value: object) -> str:
    """Render a number without a trailing ``.0``."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0"
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}"


def _elapsed(value: object, lang: str) -> str:
    """``40 segundos`` / ``40 seconds``, singular when the count is one."""
    amount = _count(value)
    if lang == "en":
        unit = "second" if amount == "1" else "seconds"
    else:
        unit = "segundo" if amount == "1" else "segundos"
    return f"{amount} {unit}"


def _labels(value: object) -> tuple[str, ...]:
    """Clean a label tuple coming out of ``relation.facts``."""
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _joined(labels: tuple[str, ...], lang: str) -> str:
    """``PET, MOTION and FALL`` / ``PET, MOTION y FALL``."""
    if len(labels) < 2:
        return "".join(labels)
    conjunction = " and " if lang == "en" else " y "
    return conjunction.join((", ".join(labels[:-1]), labels[-1]))


def _transition(item: ContextItem, lang: str) -> str:
    """Narrate a change of activity between adjacent episodes."""
    facts = item.relation.facts
    before = _labels(facts.get("from_labels"))
    after = _labels(facts.get("to_labels"))
    when = _elapsed(facts.get("seconds", 0), lang)
    marker = _DEGRADED_EN if lang == "en" else _DEGRADED_ES
    suffix = marker if item.degraded else ""
    if lang == "en":
        if before and after:
            core = (
                f"Change from {', '.join(before)} to {', '.join(after)}, "
                f"{when} later"
            )
        else:
            core = f"Change of activity, {when} later"
        return f"{core}, in the same place{suffix}."
    if before and after:
        core = f"Cambio de {', '.join(before)} a {', '.join(after)}, {when} después"
    else:
        core = f"Cambio de actividad, {when} después"
    return f"{core}, en el mismo lugar{suffix}."


def _overlapping(item: ContextItem, lang: str) -> str:
    """Narrate two episodes covering the same moment in time.

    The engine's episodes are built from sorted records, so they can only ever
    touch rather than nest: in practice ``overlap_seconds`` is 0 and saying
    "simultaneous for 0 seconds" would say nothing. Touching episodes are
    narrated as the same instant instead.
    """
    facts = item.relation.facts
    elapsed = _elapsed(facts.get("overlap_seconds", 0), lang)
    seen: list[str] = []
    for label in (
        *_labels(facts.get("subject_labels")),
        *_labels(facts.get("object_labels")),
    ):
        if label not in seen:
            seen.append(label)
    subjects = _joined(tuple(seen), lang)
    if _count(facts.get("overlap_seconds", 0)) == "0":
        moment_en, moment_es = "at the same instant", "en el mismo instante"
    else:
        moment_en = f"at the same time for {elapsed}"
        moment_es = f"simultáneos durante {elapsed}"
    if lang == "en":
        if subjects:
            return f"{subjects} {moment_en}."
        return f"Two episodes {moment_en}."
    if subjects:
        return f"{subjects} {moment_es}."
    return f"Dos episodios {moment_es}."


def _generic(item: ContextItem, lang: str) -> str:
    """Fallback so a future narratable kind is never silently dropped."""
    relation = item.relation
    if lang == "en":
        return f"Relation between {relation.subject} and {relation.object}."
    return f"Relación entre {relation.subject} y {relation.object}."


_RENDERERS = {
    "temporal_transition": _transition,
    "correlation_overlapping": _overlapping,
}


def render_context(context: Iterable[ContextItem], *, lang: str = "es") -> str:
    """Speak the narratable part of a context, or return an empty string.

    The input arrives already ranked by :func:`~src.domain.services.context.
    build_context`, so ``signal`` has already ordered the queue; what happens
    here is selection (``narratable``), degradation disclosure and wording.
    An empty context, or one holding nothing speakable, yields ``""`` — never
    an abstention phrase, because "there is no context" is not the same
    statement as "there is nothing to recall".
    """
    items = [item for item in context if item.narratable][:MAX_NARRATION_ITEMS]
    if not items:
        return ""
    english = lang == "en"
    sentences = [
        _RENDERERS.get(item.relation.kind, _generic)(item, "en" if english else "es")
        for item in items
    ]
    return " ".join(sentences)
