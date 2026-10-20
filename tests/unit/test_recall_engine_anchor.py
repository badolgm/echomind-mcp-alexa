"""Unit tests for anchored plans in the recall engine (A6c).

Covers the two-pass mechanism: resolve the anchor event, rebuild the window
around it, cut the relations at its timestamp, and abstain entirely when the
anchor cannot be resolved.
"""

from __future__ import annotations

from src.domain.services.evidence import RecallResult, render_abstention
from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import (
    DEFAULT_ANCHOR_SPAN_SECONDS,
    RecallEngine,
)

NOW = 10000.0


def _record(
    record_id: str,
    timestamp: float,
    *,
    labels: tuple[str, ...] = ("PET",),
    location: str = "patio",
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk="HIGH",
        model_analysis="",
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    for record in (
        _record("m-old", 10.0, labels=("GATE_OPEN",)),
        _record("m-gate", 1000.0, labels=("GATE_OPEN",)),
        _record("m-fall", 1080.0, labels=("FALL",)),
        _record("m-pet", 1095.0, labels=("PET",)),
    ):
        service.store_memory(record)
    return service


def _plan(
    *,
    anchor: str | None = None,
    hours: float | None = None,
    relations: tuple[RelationKind, ...] = (),
) -> RecallPlan:
    return RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW, hours=hours),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=relations,
        anchor=anchor,
    )


def _execute(**kwargs: object) -> RecallResult:
    plan = _plan(**kwargs)  # type: ignore[arg-type]
    return RecallEngine(memory=_service()).execute(plan, now=NOW)


def _entries(result: RecallResult, op: str) -> list[dict]:
    return [entry for entry in result.trace.ops_executed if entry["op"] == op]


# --- inert by default -------------------------------------------------------


def test_plan_defaults_to_no_anchor() -> None:
    assert _plan().anchor is None


def test_plan_without_anchor_runs_no_anchor_step() -> None:
    result = _execute()
    assert _entries(result, "anchor") == []


def test_plan_without_anchor_keeps_the_original_window() -> None:
    result = _execute()
    entry = _entries(result, "retrieve:range")[0]
    assert set(entry["returned_ids"]) == {"m-old", "m-gate", "m-fall", "m-pet"}


# --- anchoring --------------------------------------------------------------


def test_anchored_plan_resolves_the_most_recent_match() -> None:
    result = _execute(anchor="FALL")
    entry = _entries(result, "anchor")[0]
    assert entry == {
        "op": "anchor",
        "label": "FALL",
        "found": True,
        "record_id": "m-fall",
        "ts": 1080.0,
        "candidates": 1,
    }


def test_anchor_reports_the_candidate_count() -> None:
    service = _service()
    service.store_memory(_record("m-fall-2", 900.0, labels=("FALL",)))
    result = RecallEngine(memory=service).execute(_plan(anchor="FALL"), now=NOW)
    assert _entries(result, "anchor")[0]["candidates"] == 2


def test_anchored_plan_rebases_the_window_on_the_anchor() -> None:
    result = _execute(anchor="FALL")
    entry = _entries(result, "retrieve:range")[0]
    assert set(entry["returned_ids"]) == {"m-gate", "m-fall", "m-pet"}
    assert "m-old" not in entry["returned_ids"]


def test_anchor_span_follows_the_plan_window_hours() -> None:
    result = _execute(anchor="FALL", hours=0.5)
    entry = _entries(result, "retrieve:range")[0]
    assert set(entry["returned_ids"]) == {"m-old", "m-gate", "m-fall", "m-pet"}


def test_default_anchor_span_is_the_timeline_gap() -> None:
    assert DEFAULT_ANCHOR_SPAN_SECONDS == 300.0


def test_trace_plan_carries_the_anchor() -> None:
    result = _execute(anchor="FALL")
    assert result.trace.plan["anchor"] == "FALL"


def test_anchored_evidence_excludes_the_distant_record() -> None:
    result = _execute(anchor="FALL")
    ids = [item.record_id for item in result.evidence]
    assert ids == ["m-gate", "m-fall", "m-pet"]


# --- directional cut at the anchor (Caso 1) ---------------------------------


def test_anchored_before_relation_cuts_at_the_anchor_timestamp() -> None:
    result = _execute(anchor="FALL", relations=(RelationKind.BEFORE_AFTER,))
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    assert [episode["end"] for episode in entry["episodes"]] == [1000.0, 1080.0]


def test_relations_are_cut_at_the_anchor_not_at_the_window_edge() -> None:
    result = _execute(anchor="FALL", hours=0.5, relations=(RelationKind.BEFORE_AFTER,))
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    ends = [episode["end"] for episode in entry["episodes"]]
    assert ends == [10.0, 1000.0, 1080.0]
    assert max(ends) == 1080.0  # cut at the anchor, not at the window edge 2880.0


# --- abstention -------------------------------------------------------------


def test_anchored_plan_abstains_when_the_label_was_never_seen() -> None:
    result = _execute(anchor="SMOKE")
    assert result.utterance == render_abstention(lang="es")
    assert result.evidence == ()
    assert result.is_error is False


def test_abstention_trace_records_the_anchor_miss() -> None:
    result = _execute(anchor="SMOKE")
    entry = _entries(result, "anchor")[0]
    assert entry == {
        "op": "anchor",
        "label": "SMOKE",
        "found": False,
    }


def test_abstention_runs_no_retrieval_operation() -> None:
    result = _execute(anchor="SMOKE")
    ops = [entry["op"] for entry in result.trace.ops_executed]
    assert ops == ["anchor"]


def test_abstention_carries_no_evidence_ids() -> None:
    result = _execute(anchor="SMOKE")
    assert result.trace.evidence_ids == ()


def test_abstention_is_available_in_english() -> None:
    plan = RecallPlan(
        lang="en",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        anchor="SMOKE",
    )
    result = RecallEngine(memory=_service()).execute(plan, now=NOW)
    assert result.utterance == render_abstention(lang="en")
