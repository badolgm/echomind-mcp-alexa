"""Unit tests for the A6a relation foundation.

Locks the four invariants of the Relation Layer: closed vocabulary, mandatory
provenance, immutability and JSON-safe serialization — plus the deliberate
absence of a ``confidence`` field.
"""

from __future__ import annotations

import json

import pytest

from src.domain.services.relation import (
    CORRELATIONAL_KINDS,
    KNOWN_RELATION_KINDS,
    SPATIAL_KINDS,
    TEMPORAL_KINDS,
    Relation,
    relation_to_dict,
)


def _relation(**overrides: object) -> Relation:
    payload: dict[str, object] = {
        "kind": "temporal_precedes",
        "subject": "ep-1",
        "object": "ep-2",
        "rule": "temporal.precedes",
        "facts": {"seconds": 40.0},
    }
    payload.update(overrides)
    return Relation(**payload)  # type: ignore[arg-type]


# --- closed vocabulary ------------------------------------------------------


def test_every_declared_kind_can_be_constructed() -> None:
    for kind in KNOWN_RELATION_KINDS:
        assert _relation(kind=kind).kind == kind


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown relation kind"):
        _relation(kind="caused_by")


def test_causal_language_is_not_a_valid_kind() -> None:
    for kind in ("causal", "causes", "caused_by", "because_of"):
        with pytest.raises(ValueError):
            _relation(kind=kind)


def test_kinds_are_grouped_into_the_four_families() -> None:
    assert set(TEMPORAL_KINDS) | set(SPATIAL_KINDS) | set(CORRELATIONAL_KINDS) == (
        set(KNOWN_RELATION_KINDS)
    )
    assert all(kind.startswith("temporal_") for kind in TEMPORAL_KINDS)
    assert all(kind.startswith("spatial_") for kind in SPATIAL_KINDS)
    assert all(kind.startswith("correlation_") for kind in CORRELATIONAL_KINDS)


def test_vocabulary_is_frozen_against_free_strings() -> None:
    assert isinstance(KNOWN_RELATION_KINDS, tuple)


# --- mandatory provenance ---------------------------------------------------


def test_empty_subject_is_rejected() -> None:
    with pytest.raises(ValueError, match="subject"):
        _relation(subject="   ")


def test_empty_object_is_rejected() -> None:
    with pytest.raises(ValueError, match="object"):
        _relation(object="")


def test_empty_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="rule"):
        _relation(rule="  ")


# --- immutability -----------------------------------------------------------


def test_relation_is_frozen() -> None:
    relation = _relation()
    with pytest.raises(Exception):
        relation.kind = "temporal_follows"  # type: ignore[misc]


def test_relation_has_no_instance_dict() -> None:
    assert not hasattr(_relation(), "__dict__")


def test_facts_are_carried_verbatim() -> None:
    relation = _relation(facts={"seconds": 12.5, "labels": ("PET", "FALL")})
    assert relation.facts["seconds"] == 12.5
    assert relation.facts["labels"] == ("PET", "FALL")


# --- deliberate absence of confidence ---------------------------------------


def test_relation_has_no_confidence_field() -> None:
    assert not hasattr(_relation(), "confidence")


def test_degradation_is_explicit_instead() -> None:
    relation = _relation(degraded=True, fallback="location")
    assert relation.degraded is True
    assert relation.fallback == "location"


def test_relation_defaults_to_exact_identity() -> None:
    relation = _relation()
    assert relation.degraded is False
    assert relation.fallback is None


# --- serialization ----------------------------------------------------------


def test_relation_to_dict_is_json_safe() -> None:
    data = relation_to_dict(_relation())
    _ = json.dumps(data)
    assert data == {
        "kind": "temporal_precedes",
        "subject": "ep-1",
        "object": "ep-2",
        "rule": "temporal.precedes",
        "facts": {"seconds": 40.0},
        "degraded": False,
        "fallback": None,
    }


def test_relation_to_dict_is_deterministic() -> None:
    assert relation_to_dict(_relation()) == relation_to_dict(_relation())


def test_relation_to_dict_copies_facts() -> None:
    data = relation_to_dict(_relation(facts={"seconds": 1.0}))
    data["facts"]["seconds"] = 999.0  # type: ignore[index]
    assert _relation(facts={"seconds": 1.0}).facts["seconds"] == 1.0


def test_round_trip_rebuilds_an_equal_relation() -> None:
    original = _relation(degraded=True, fallback="source")
    rebuilt = Relation(**relation_to_dict(original))  # type: ignore[arg-type]
    assert rebuilt == original
