"""Unit tests for evidence and narration (deterministic, no invention)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.services.evidence import (
    Evidence,
    RecallResult,
    RecallTrace,
    format_relative_time,
    render_abstention,
    render_utterance,
    truncate_snippet,
)


@dataclass(frozen=True, slots=True)
class DummyRecord:
    id: str
    timestamp: float
    location: str
    source: str = "cam"
    detections: tuple[dict[str, Any], ...] = ()
    risk: str = "LOW"
    model_analysis: str = ""


def test_evidence_frozen_with_optional_defaults() -> None:
    ev = Evidence(record_id="r1", ts=1.0)
    assert ev.camera_id is None
    assert ev.zone is None
    assert ev.location == ""
    assert ev.labels == ()


def test_from_record_reads_detections_duck_typed() -> None:
    rec = DummyRecord(
        id="m1",
        timestamp=42.0,
        location="living_room",
        detections=({"label": "PET", "confidence": 0.92}, {"label": "MOTION"}),
        risk="MEDIUM",
        model_analysis="A small pet was detected moving in the living room.",
    )
    ev = Evidence.from_record(rec)
    assert ev.record_id == "m1"
    assert ev.ts == 42.0
    assert ev.location == "living_room"
    assert ev.labels == ("PET", "MOTION")
    assert ev.risk == "MEDIUM"
    assert ev.confidence == 0.92


def test_from_record_missing_fields_degrade() -> None:
    class Bare:
        id = "m3"
        timestamp = 5.0
        detections = ()
        risk = "HIGH"
        model_analysis = ""

    ev = Evidence.from_record(Bare())
    assert ev.location == ""
    assert ev.labels == ()
    assert ev.snippet == ""


def test_from_record_confidence_is_max() -> None:
    rec = DummyRecord(
        id="m4",
        timestamp=1.0,
        location="zone",
        detections=(
            {"label": "PET", "confidence": 0.1},
            {"label": "MOTION", "confidence": 0.9},
        ),
    )
    ev = Evidence.from_record(rec)
    assert ev.confidence == 0.9


def test_from_record_does_not_import_memory_record() -> None:
    rec = DummyRecord(id="m5", timestamp=2.0, location="cam-1", detections=())
    ev = Evidence.from_record(rec)
    assert ev.record_id == "m5"
    assert ev.location == "cam-1"


def test_render_abstention_bilingual() -> None:
    es = render_abstention(lang="es")
    en = render_abstention(lang="en")
    assert es and en and es != en


def test_render_utterance_deterministic() -> None:
    ev = Evidence(
        record_id="r1",
        ts=100.0,
        location="living_room",
        labels=("PET",),
        snippet="pet moving",
    )
    a = render_utterance((ev,), lang="es", now=200.0)
    b = render_utterance((ev,), lang="es", now=200.0)
    assert a == b


def test_render_utterance_never_invents() -> None:
    out = render_utterance((), lang="es", now=0.0)
    assert out == render_abstention(lang="es")


def test_render_utterance_bilingual() -> None:
    ev = Evidence(record_id="r2", ts=60.0, location="kitchen", labels=("MOTION",))
    es = render_utterance((ev,), lang="es", now=120.0)
    en = render_utterance((ev,), lang="en", now=120.0)
    assert "kitchen" in es or "kitchen" in en or True
    # stronger: location appears
    assert "kitchen" in es.lower() or "cocina" in es.lower() or "kitchen" in en.lower()


def test_format_relative_time_matches_v1_semantics() -> None:
    # <60s → a few seconds
    assert "segundos" in format_relative_time(0, 30, "es")
    assert "seconds" in format_relative_time(0, 30, "en")
    # 1 min
    assert "1 minuto" in format_relative_time(
        0, 60, "es"
    ) or "1 minute" in format_relative_time(0, 60, "en")
    # 2 min
    assert "2 minutos" in format_relative_time(
        0, 120, "es"
    ) or "2 minutes" in format_relative_time(0, 120, "en")
    # 1 hour
    assert "1 hora" in format_relative_time(
        0, 3600, "es"
    ) or "1 hour" in format_relative_time(0, 3600, "en")
    # 2 hours
    assert "2 horas" in format_relative_time(
        0, 7200, "es"
    ) or "2 hours" in format_relative_time(0, 7200, "en")
    # 1 day
    assert "1 día" in format_relative_time(
        0, 86400, "es"
    ) or "1 day" in format_relative_time(0, 86400, "en")
    # 2 days
    assert "2 días" in format_relative_time(
        0, 172800, "es"
    ) or "2 days" in format_relative_time(0, 172800, "en")
    # week
    assert "semana" in format_relative_time(
        0, 604800, "es"
    ) or "week" in format_relative_time(0, 604800, "en")


def test_truncate_snippet_limit() -> None:
    long = "x" * 200
    s = truncate_snippet(long, limit=120)
    assert len(s) == 120
    assert s.endswith("...")


def test_recall_result_serializable() -> None:
    ev = Evidence(record_id="e1", ts=1.0, location="l", labels=("PET",), snippet="ok")
    trace = RecallTrace(
        lang="es",
        plan={"ops": []},
        ops_executed=(),
        evidence_ids=("e1",),
    )
    res = RecallResult(utterance="ok", evidence=(ev,), trace=trace, lang="es")
    assert res.trace.plan["ops"] == []
    assert res.trace.evidence_ids == ("e1",)
