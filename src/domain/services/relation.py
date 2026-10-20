"""Relation Layer foundation (A6a): the unit of contextual reasoning.

Pure domain layer (standard library only). A :class:`Relation` is a derived,
fully-provenance-carrying link between two pieces of evidence, computed only
from stored facts (timestamps, labels, locations, cameras, risk) — never from
a model and never from a guess.

Invariants enforced here and locked by tests:

* **Closed vocabulary** — ``kind`` must be one of ``KNOWN_RELATION_KINDS``. A
  new relation type means a new row in that tuple, never a free string, which
  is what keeps the answerable surface auditable.
* **Provenance** — ``subject``, ``object`` and ``rule`` are mandatory and
  non-empty. A relation nobody can trace back to a rule and to an id is not a
  relation, it is a guess.
* **Immutability** — frozen and slotted, so a relation can be replayed.
* **No ``confidence``** — deliberately. ``degraded``/``fallback`` state whether
  the identity used was exact or approximated; "how sure are you" is not a
  question a deterministic engine can answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

TEMPORAL_KINDS: tuple[str, ...] = (
    "temporal_precedes",
    "temporal_follows",
    "temporal_within",
    "temporal_gap",
    "temporal_transition",
)

SPATIAL_KINDS: tuple[str, ...] = (
    "spatial_same_zone",
    "spatial_same_camera",
    "spatial_degraded",
)

CORRELATIONAL_KINDS: tuple[str, ...] = (
    "correlation_same_label",
    "correlation_same_risk",
    "correlation_overlapping",
    "correlation_co_occurring",
)

KNOWN_RELATION_KINDS: tuple[str, ...] = (
    TEMPORAL_KINDS + SPATIAL_KINDS + CORRELATIONAL_KINDS
)


@dataclass(frozen=True, slots=True)
class Relation:
    """One derived link between two evidence items.

    ``facts`` carries the raw numbers behind the claim (seconds of separation,
    the shared label, the window bounds…) so a reader never has to trust the
    wording: the measurement is in the payload.
    """

    kind: str
    subject: str
    object: str
    rule: str
    facts: Mapping[str, object] = field(default_factory=dict)
    degraded: bool = False
    fallback: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KNOWN_RELATION_KINDS:
            raise ValueError(
                f"unknown relation kind {self.kind!r}; "
                f"known kinds are {KNOWN_RELATION_KINDS}"
            )
        for name in ("subject", "object", "rule"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"relation field {name!r} must not be empty")


def relation_to_dict(relation: Relation) -> dict[str, object]:
    """JSON-safe projection, used to put relations into an audit trace."""
    return {
        "kind": relation.kind,
        "subject": relation.subject,
        "object": relation.object,
        "rule": relation.rule,
        "facts": dict(relation.facts),
        "degraded": relation.degraded,
        "fallback": relation.fallback,
    }
