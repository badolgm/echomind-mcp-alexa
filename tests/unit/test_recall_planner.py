"""Unit tests for recall planner (understand)."""

from __future__ import annotations

import pytest

from src.domain.services.recall_plan import RelationKind, RetrieveKind
from src.domain.services.recall_planner import understand


def test_understand_ops_never_empty() -> None:
    for q in ("mascota", "qué pasó", "cuántos eventos hubo", "estado actual"):
        p = understand(q, now=0.0)
        assert p.ops


def test_understand_fallback_when_nothing_recognized() -> None:
    p = understand("nonsense xyz 123", now=0.0)
    assert any(op.kind is RetrieveKind.SEARCH for op in p.ops)


def test_understand_respects_explicit_lang() -> None:
    p = understand("pet last seen", lang="en", now=0.0)
    assert p.lang == "en"


def test_understand_detects_lang_when_absent() -> None:
    p = understand("cuándo vi a mi mascota", lang=None, now=0.0)
    assert p.lang == "es"


def test_understand_is_deterministic() -> None:
    a = understand("qué pasó ayer", now=1234.5)
    b = understand("qué pasó ayer", now=1234.5)
    assert a == b


def test_understand_uses_injected_now() -> None:
    a = understand("qué pasó en las últimas 2 horas", now=10000.0)
    b = understand("qué pasó en las últimas 2 horas", now=20000.0)
    # window changes
    assert a.window.since != b.window.since or a.window.until != b.window.until


def test_understand_relations_deduplicated() -> None:
    p = understand("dónde y dónde estaba la mascota", now=0.0)
    seen = []
    for r in p.relations:
        assert r not in seen
        seen.append(r)


def test_understand_empty_query_returns_fallback_plan() -> None:
    p = understand("", now=0.0)
    assert p.ops


def test_understand_reuses_public_classifier_api() -> None:
    p = understand("¿cuándo viste una mascota?", now=0.0)
    has_pet = any(e.value == "PET" for e in p.entities if e.kind == "label")
    assert has_pet


def test_understand_never_returns_none() -> None:
    for q in ("mascota", "puerta", "reja", "cámaras", "antes de la caída"):
        p = understand(q, now=0.0)
        assert p is not None


@pytest.mark.parametrize(
    "q,expect_spatial,expect_before,expect_corr,expect_timeline",
    [
        ("dónde vi la mascota", True, False, False, False),
        ("qué pasó antes de la caída", False, True, False, False),
        ("qué ocurrió mientras estaba fuera", False, False, False, True),
        ("qué mostraron las cámaras", False, False, True, False),
    ],
)
def test_understand_four_target_cases(
    q: str,
    expect_spatial: bool,
    expect_before: bool,
    expect_corr: bool,
    expect_timeline: bool,
) -> None:
    p = understand(q, now=0.0)
    assert p.ops
    assert (RelationKind.SPATIAL in p.relations) is expect_spatial
    assert (RelationKind.BEFORE_AFTER in p.relations) is expect_before
    assert (RelationKind.CORRELATION in p.relations) is expect_corr
    assert (RelationKind.TIMELINE in p.relations) is expect_timeline


@pytest.mark.parametrize(
    "query,expected_kind,expected_value",
    [
        ("¿dónde estuvo la mascota en el patio por última vez?", "zone", "patio"),
        ("¿dónde estuvo la mascota en cam-1 por última vez?", "camera", "cam-1"),
    ],
)
def test_understand_location_becomes_camera_or_zone(
    query: str, expected_kind: str, expected_value: str
) -> None:
    p = understand(query, now=0.0)
    slots = {(e.kind, e.value) for e in p.entities}
    assert (expected_kind, expected_value) in slots
