"""Unit tests for the recall engine (retrieve → relate → synthesize)."""

from __future__ import annotations

from src.domain.services.evidence import render_abstention
from src.domain.services.recall_plan import (
    Aggregation,
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.domain.services.recall_planner import understand
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import (
    ENGINE_NAME,
    ENGINE_VERSION,
    RecallEngine,
)

NOW = 10000.0


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    risk: str = "HIGH",
    labels: tuple[str, ...] = ("PET",),
    analysis: str = "la mascota se acerca a la reja",
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk=risk,
        model_analysis=analysis,
    )


def _service() -> VectorMemoryService:
    service = VectorMemoryService()
    for record in (
        _record("mem-1", 1000.0, labels=("PET",), analysis="la mascota en el patio"),
        _record("mem-2", 2000.0, labels=("PET",), analysis="la mascota entra"),
        _record(
            "mem-3",
            5000.0,
            location="kitchen",
            risk="CRITICAL",
            labels=("SMOKE",),
            analysis="humo en la cocina",
        ),
        _record("mem-4", 9000.0, labels=("GATE_OPEN",), analysis="reja abierta"),
    ):
        service.store_memory(record)
    return service


def _clustered_service() -> VectorMemoryService:
    service = VectorMemoryService()
    for record in (
        _record("cl-1", 1000.0),
        _record("cl-2", 1010.0),
        _record("cl-3", 5000.0),
    ):
        service.store_memory(record)
    return service


def _plan(
    *,
    lang: str = "es",
    window: TimeWindow | None = None,
    ops: tuple[RetrieveOp, ...] = (),
    relations: tuple[RelationKind, ...] = (),
) -> RecallPlan:
    return RecallPlan(
        lang=lang,
        window=window or TimeWindow(anchor=Anchor.NOW),
        ops=ops,
        relations=relations,
    )


def test_engine_exposes_identity() -> None:
    assert ENGINE_NAME == "echo-recall"
    assert ENGINE_VERSION == 1


def test_execute_returns_recall_result() -> None:
    engine = RecallEngine(memory=_service())
    result = engine.execute(_plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),)), now=NOW)
    assert result.lang == "es"
    assert result.is_error is False
    assert len(result.evidence) == 4


def test_execute_abstains_when_memory_is_empty() -> None:
    engine = RecallEngine(memory=VectorMemoryService())
    result = engine.execute(_plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),)), now=NOW)
    assert result.evidence == ()
    assert result.utterance == render_abstention(lang="es")


def test_execute_with_no_ops_abstains() -> None:
    engine = RecallEngine(memory=_service())
    result = engine.execute(_plan(), now=NOW)
    assert result.evidence == ()
    assert result.utterance == render_abstention(lang="es")


def test_execute_is_deterministic() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),))
    assert engine.execute(plan, now=NOW) == engine.execute(plan, now=NOW)


def test_execute_last_seen_returns_most_recent_match() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.LAST_SEEN, entity="PET"),))
    result = engine.execute(plan, now=NOW)
    assert [item.record_id for item in result.evidence] == ["mem-2"]


def test_execute_range_respects_the_window() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        window=TimeWindow(since=1500.0, until=6000.0, anchor=Anchor.EXPLICIT),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
    )
    result = engine.execute(plan, now=NOW)
    assert [item.record_id for item in result.evidence] == ["mem-2", "mem-3"]


def test_execute_search_returns_matching_evidence() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.SEARCH, query="humo"),))
    result = engine.execute(plan, now=NOW)
    search = next(
        entry for entry in result.trace.ops_executed if entry["op"] == "retrieve:search"
    )
    assert "mem-3" in search["returned_ids"]


def test_execute_trace_records_every_operation() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(
            RetrieveOp(kind=RetrieveKind.LAST_SEEN, entity="PET"),
            RetrieveOp(kind=RetrieveKind.RANGE),
        )
    )
    result = engine.execute(plan, now=NOW)
    assert [entry["op"] for entry in result.trace.ops_executed] == [
        "retrieve:last_seen",
        "retrieve:range",
    ]


def test_execute_trace_evidence_ids_match_evidence() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),))
    result = engine.execute(plan, now=NOW)
    assert result.trace.evidence_ids == tuple(
        item.record_id for item in result.evidence
    )


def test_execute_dedupes_records_across_operations() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(
            RetrieveOp(kind=RetrieveKind.LAST_SEEN, entity="PET"),
            RetrieveOp(kind=RetrieveKind.RANGE),
        )
    )
    result = engine.execute(plan, now=NOW)
    ids = [item.record_id for item in result.evidence]
    assert ids.count("mem-2") == 1
    assert set(ids) == {"mem-1", "mem-2", "mem-3", "mem-4"}


def test_execute_orders_evidence_chronologically() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),))
    result = engine.execute(plan, now=NOW)
    assert [item.ts for item in result.evidence] == [1000.0, 2000.0, 5000.0, 9000.0]


def test_execute_timeline_relation_exposes_episodes_and_gaps() -> None:
    engine = RecallEngine(memory=_clustered_service())
    plan = _plan(
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.TIMELINE,),
    )
    result = engine.execute(plan, now=NOW)
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    assert entry["relation"] == "timeline"
    assert len(entry["episodes"]) == 2
    assert len(entry["gaps"]) == 1
    assert entry["gaps"][0]["seconds"] == 3990.0


def test_execute_before_after_limits_episodes_to_the_target() -> None:
    engine = RecallEngine(memory=_clustered_service())
    plan = _plan(
        window=TimeWindow(since=0.0, until=2000.0, anchor=Anchor.EXPLICIT),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.BEFORE_AFTER,),
    )
    result = engine.execute(plan, now=NOW)
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    assert entry["relation"] == "before_after"
    assert entry["target_ts"] == 2000.0
    assert entry["count"] == 1
    assert entry["episodes"][0]["record_ids"] == ["cl-1", "cl-2"]


def test_execute_spatial_relation_groups_and_flags_degradation() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.SPATIAL,),
    )
    result = engine.execute(plan, now=NOW)
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    assert entry["relation"] == "spatial"
    assert entry["degraded"] is True
    assert set(entry["groups"]) == {"patio", "kitchen"}
    assert entry["groups"]["kitchen"] == ["mem-3"]


def test_execute_correlation_relation_groups_by_location() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=(RelationKind.CORRELATION,),
    )
    result = engine.execute(plan, now=NOW)
    entry = next(e for e in result.trace.ops_executed if e["op"] == "relate")
    assert entry["relation"] == "correlation"
    assert entry["degraded"] is True


def test_execute_session_start_anchor_uses_the_injected_anchor() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        window=TimeWindow(anchor=Anchor.SESSION_START),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
    )
    result = engine.execute(plan, now=NOW, session_start=4000.0)
    assert [item.record_id for item in result.evidence] == ["mem-3", "mem-4"]


def test_execute_session_start_without_anchor_degrades_to_unbounded() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        window=TimeWindow(anchor=Anchor.SESSION_START),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
    )
    result = engine.execute(plan, now=NOW)
    entry = result.trace.ops_executed[0]
    assert entry["filters"]["since"] is None
    assert len(result.evidence) == 4


def test_execute_count_aggregation_exposes_the_value() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(
            RetrieveOp(
                kind=RetrieveKind.AGGREGATE,
                entity="PET",
                aggregation=Aggregation.COUNT,
            ),
        )
    )
    result = engine.execute(plan, now=NOW)
    entry = result.trace.ops_executed[0]
    assert entry["aggregation"] == "count"
    assert entry["value"] == 2
    assert result.evidence == ()


def test_execute_summary_aggregation_exposes_label_counts() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(
        ops=(
            RetrieveOp(
                kind=RetrieveKind.AGGREGATE,
                entity="PET",
                aggregation=Aggregation.SUMMARY,
            ),
        )
    )
    result = engine.execute(plan, now=NOW)
    entry = result.trace.ops_executed[0]
    assert entry["aggregation"] == "summary"
    assert entry["label_counts"] == {"PET": 2}
    assert [item.record_id for item in result.evidence] == ["mem-1", "mem-2"]


def test_execute_current_state_reports_unavailable() -> None:
    engine = RecallEngine(memory=_service())
    plan = _plan(ops=(RetrieveOp(kind=RetrieveKind.CURRENT_STATE),))
    result = engine.execute(plan, now=NOW)
    assert result.trace.ops_executed[0]["status"] == "unavailable"
    assert result.evidence == ()
    assert result.utterance == render_abstention(lang="es")


def test_execute_needs_only_the_memory_store() -> None:
    engine = RecallEngine(memory=VectorMemoryService())
    assert not hasattr(engine, "_llm")
    assert not hasattr(engine, "llm")
    result = engine.execute(understand("mascota", now=NOW), now=NOW)
    assert result.is_error is False


def test_execute_full_pipeline_from_a_natural_query() -> None:
    engine = RecallEngine(memory=_service())
    plan = understand("¿cuándo viste una mascota?", now=NOW)
    result = engine.execute(plan, now=NOW)
    assert plan.ops[0].kind is RetrieveKind.LAST_SEEN
    assert {item.record_id for item in result.evidence} == {"mem-1", "mem-2"}
    assert "PET" in result.utterance
    assert result.trace.plan["lang"] == "es"


def test_execute_does_not_mutate_the_store() -> None:
    service = _service()
    engine = RecallEngine(memory=service)
    before = service.size
    engine.execute(_plan(ops=(RetrieveOp(kind=RetrieveKind.RANGE),)), now=NOW)
    assert service.size == before
