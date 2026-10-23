"""Relation rules (A6d): the table that turns episodes into relations.

Pure domain layer (standard library only). Given a set of :class:`Episode`
objects it emits the :class:`Relation` graph between them, pairwise, in a
deterministically ordered and capped list.

Two rules of the design:

* **Table, not branches** — every rule is a row in :data:`RELATION_RULES` and
  a matching builder, mirroring how ``recall_planner`` adds a use case with a
  table row instead of an ``if``.
* **Only what the episodes can prove** — an episode carries ``location`` but no
  ``camera_id``, so ``spatial_same_zone`` degrades to the location identity and
  says so, and no camera rule is emitted at all: a rule that always guessed
  would be worse than a rule that stays silent.

The engine emits relations into the trace only; it never words an answer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.domain.services.memory_spatial import resolve_zone
from src.domain.services.relation import Relation

DEFAULT_MAX_RELATIONS = 64

DEFAULT_ADJACENCY_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class RelationRule:
    """One declared rule: its stable id, the kind it emits and its meaning.

    ``salience`` (0-3) is how much the relation deserves a human's attention.
    It grades the *rule*, not the evidence: every instance of a rule inherits
    the same weight. It does not change whether a relation is produced, only
    whether the narrator should reach for it first — the data comes first and
    the wording is a later phase.
    """

    id: str
    kind: str
    description: str
    salience: int


RELATION_RULES: tuple[RelationRule, ...] = (
    RelationRule(
        id="temporal.precedes",
        kind="temporal_precedes",
        description="one episode ends at or before another starts",
        salience=2,
    ),
    RelationRule(
        id="temporal.transition",
        kind="temporal_transition",
        description=(
            "adjacent episodes in the same place whose detection labels change"
        ),
        salience=3,
    ),
    RelationRule(
        id="correlation.same_label",
        kind="correlation_same_label",
        description="two episodes share at least one detection label",
        salience=2,
    ),
    RelationRule(
        id="correlation.same_risk",
        kind="correlation_same_risk",
        description="two episodes carry the same risk level",
        salience=1,
    ),
    RelationRule(
        id="correlation.overlapping",
        kind="correlation_overlapping",
        description="two episodes cover overlapping moments in time",
        salience=3,
    ),
    RelationRule(
        id="spatial.same_zone",
        kind="spatial_same_zone",
        description="two episodes resolve to the same zone identity",
        salience=1,
    ),
)

_RULE_BY_ID = {rule.id: rule for rule in RELATION_RULES}


def relate_episodes(
    episodes: Iterable[object],
    *,
    max_relations: int = DEFAULT_MAX_RELATIONS,
    adjacency_seconds: float = DEFAULT_ADJACENCY_SECONDS,
) -> tuple[Relation, ...]:
    """Relations between ``episodes``, deterministically ordered and capped."""
    ordered = sorted(episodes, key=_order_key)
    collected: list[Relation] = []
    for index, subject in enumerate(ordered):
        for following in ordered[index + 1 :]:
            collected.extend(_pair_relations(subject, following, adjacency_seconds))
    collected.sort(
        key=lambda relation: (relation.kind, relation.subject, relation.object)
    )
    if max_relations < 0:
        return ()
    return tuple(collected[:max_relations])


def _pair_relations(
    first: object, second: object, adjacency_seconds: float
) -> list[Relation]:
    """Every rule applied to one ordered pair of episodes."""
    found: list[Relation] = []
    first_id, second_id = _id_of(first), _id_of(second)
    same_zone, zone_degraded, zone_fallback = _same_zone(first, second)

    if _ends_at_or_before(first, second):
        seconds = _start_of(second) - _end_of(first)
        found.append(
            _build(
                "temporal.precedes",
                subject=first_id,
                object=second_id,
                facts={"seconds": seconds},
            )
        )
        if (
            seconds <= adjacency_seconds
            and _labels_of(first) != _labels_of(second)
            and same_zone
        ):
            found.append(
                _build(
                    "temporal.transition",
                    subject=first_id,
                    object=second_id,
                    facts={
                        "seconds": seconds,
                        "from_labels": _labels_of(first),
                        "to_labels": _labels_of(second),
                    },
                    degraded=zone_degraded,
                    fallback=zone_fallback,
                )
            )

    shared = _shared_labels(first, second)
    if shared:
        found.append(
            _build(
                "correlation.same_label",
                subject=first_id,
                object=second_id,
                facts={"shared": shared},
            )
        )

    if str(_risk_of(first)) == str(_risk_of(second)):
        found.append(
            _build(
                "correlation.same_risk",
                subject=first_id,
                object=second_id,
                facts={"risk": _risk_of(first)},
            )
        )

    overlap = min(_end_of(first), _end_of(second)) - max(
        _start_of(first), _start_of(second)
    )
    if overlap >= 0:
        found.append(
            _build(
                "correlation.overlapping",
                subject=first_id,
                object=second_id,
                facts={
                    "overlap_seconds": overlap,
                    "subject_labels": _labels_of(first),
                    "object_labels": _labels_of(second),
                },
            )
        )

    if same_zone:
        found.append(
            _build(
                "spatial.same_zone",
                subject=first_id,
                object=second_id,
                facts={"zone": resolve_zone(first)[0]},
                degraded=zone_degraded,
                fallback=zone_fallback,
            )
        )
    return found


def _build(
    rule_id: str,
    *,
    subject: str,
    object: str,
    facts: dict[str, object],
    degraded: bool = False,
    fallback: str | None = None,
) -> Relation:
    rule = _RULE_BY_ID[rule_id]
    return Relation(
        kind=rule.kind,
        subject=subject,
        object=object,
        rule=rule.id,
        facts=facts,
        degraded=degraded,
        fallback=fallback,
    )


def _same_zone(first: object, second: object) -> tuple[bool, bool, str | None]:
    """Whether both episodes share a zone, and whether that identity degraded."""
    first_zone, first_degraded = resolve_zone(first)
    second_zone, second_degraded = resolve_zone(second)
    if first_zone != second_zone:
        return False, False, None
    degraded = first_degraded or second_degraded
    return True, degraded, ("location" if degraded else None)


def _ends_at_or_before(first: object, second: object) -> bool:
    return _end_of(first) <= _start_of(second)


def _start_of(episode: object) -> float:
    return float(getattr(episode, "start", 0.0) or 0.0)


def _end_of(episode: object) -> float:
    return float(getattr(episode, "end", 0.0) or 0.0)


def _risk_of(episode: object) -> str:
    return str(getattr(episode, "risk", "") or "")


def _labels_of(episode: object) -> tuple[str, ...]:
    labels = getattr(episode, "labels", ()) or ()
    return tuple(str(label) for label in labels)


def _shared_labels(first: object, second: object) -> tuple[str, ...]:
    return tuple(sorted(set(_labels_of(first)) & set(_labels_of(second))))


def _id_of(episode: object) -> str:
    """Stable identity of an episode: its first record, else its start moment."""
    record_ids: Sequence[str] = getattr(episode, "record_ids", ()) or ()
    if record_ids:
        return str(record_ids[0])
    return f"ep@{_start_of(episode):.3f}"


def _order_key(episode: object) -> tuple[float, float, str]:
    return (_start_of(episode), _end_of(episode), _id_of(episode))
