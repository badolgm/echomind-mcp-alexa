"""Context (A6e): the structured, graded digest of a relation graph.

The pipeline this phase belongs to is deliberate:

    data -> relations -> context -> narration

A6d produced the relations: correct, deterministic, traceable. They are still
a graph, which is a good way to be audited and a poor way to be understood.
A6e stops one step short of words. It grades every relation by how much it is
worth telling a human, ranks them so the informative ones lead, and marks the
ones that must not be stated as certain because their identity degraded.

Nothing in here produces a sentence. The narrator is A6f and it will read
this structure, never the raw graph.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.services.relation import Relation, relation_to_dict
from src.domain.services.relation_rules import RELATION_RULES

SIGNAL_MIN = 2
"""Salience at or above which a relation is worth telling without prompting."""

NARRATION_MIN = 3
"""Salience at or above which a relation is worth speaking out loud.

A wider ladder than :data:`SIGNAL_MIN` on purpose. A relation can be signal —
worth reaching for first — and still not be worth saying: ``temporal.precedes``
and ``correlation.same_label`` carry attention but repeat in bulk, and a
recollection that narrates them explains its own noise. Only the grades a human
actually perceives as context reach the voice, which today means
``temporal.transition`` and ``correlation.overlapping``. Raising or lowering
this line later is a one-line decision, not a redesign.
"""

DEFAULT_SALIENCE = 0
"""Grade for a kind the rule table does not know: never promoted, never lost."""

_SALIENCE_BY_KIND = {rule.kind: rule.salience for rule in RELATION_RULES}


@dataclass(frozen=True, slots=True)
class ContextItem:
    """One relation, graded for the narrator."""

    relation: Relation
    salience: int

    def __post_init__(self) -> None:
        if not 0 <= self.salience <= 3:
            raise ValueError(f"salience must be between 0 and 3, got {self.salience}")

    @property
    def signal(self) -> bool:
        """True when this relation deserves to be said out loud first."""
        return self.salience >= SIGNAL_MIN

    @property
    def narratable(self) -> bool:
        """True when this relation may be turned into a sentence."""
        return self.salience >= NARRATION_MIN

    @property
    def degraded(self) -> bool:
        """True when the relation rests on a degraded identity."""
        return self.relation.degraded


def salience_of(kind: str) -> int:
    """Grade a relation kind by its rule, defaulting to silence for unknowns."""
    return _SALIENCE_BY_KIND.get(kind, DEFAULT_SALIENCE)


def build_context(relations: Iterable[Relation]) -> tuple[ContextItem, ...]:
    """Rank ``relations`` for the narrator without dropping any of them.

    Low-salience relations are demoted, not deleted: evidence that already
    exists stays visible, because hiding it is how a system starts lying by
    omission. The order is total and stable — salience first, then kind and
    ids — so the same input always yields the same context.
    """
    items = [
        ContextItem(relation=relation, salience=salience_of(relation.kind))
        for relation in relations
    ]
    items.sort(
        key=lambda item: (
            -item.salience,
            item.relation.kind,
            item.relation.subject,
            item.relation.object,
        )
    )
    return tuple(items)


def context_to_dict(item: ContextItem) -> dict[str, object]:
    """JSON-safe projection of a context item, for ``/api/recall``."""
    payload = relation_to_dict(item.relation)
    payload["salience"] = item.salience
    payload["signal"] = item.signal
    return payload
