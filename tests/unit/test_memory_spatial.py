"""Unit tests for the A5 spatial reasoning activation.

Covers the three pieces A5 adds: the pure degradation helpers in
``memory_spatial``, the engine's spatial grouping (``spatial`` by zone and
``correlation`` by camera, each degrading to the V1 identity) and the additive
``camera_id``/``zone`` keys on the ``/api/recall`` payload.
"""

from __future__ import annotations

from src.domain.services.evidence import Evidence, RecallResult, RecallTrace
from src.domain.services.memory_spatial import resolve_camera, resolve_zone
from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.infrastructure.adapters.mcp.recall_resolvers import recall_result_payload
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 10000.0


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    source: str = "camera_alert",
    risk: str = "HIGH",
    labels: tuple[str, ...] = ("PET",),
    camera_id: str | None = None,
    zone: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source=source,
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk=risk,
        model_analysis="analisis",
        camera_id=camera_id,
        zone=zone,
    )


def _plan(*, relations: tuple[RelationKind, ...]) -> RecallPlan:
    return RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=(RetrieveOp(kind=RetrieveKind.RANGE),),
        relations=relations,
    )


def _relate_entry(service: VectorMemoryService, relation: RelationKind) -> dict:
    result = RecallEngine(memory=service).execute(_plan(relations=(relation,)), now=NOW)
    return next(entry for entry in result.trace.ops_executed if entry["op"] == "relate")


def _service(*records: MemoryRecord) -> VectorMemoryService:
    service = VectorMemoryService()
    for record in records:
        service.store_memory(record)
    return service


# --- memory_spatial helpers -------------------------------------------------


def test_resolve_zone_prefers_the_recorded_zone() -> None:
    assert resolve_zone(_record("m", 1.0, zone="outdoor")) == ("outdoor", False)


def test_resolve_zone_degrades_to_location_when_absent() -> None:
    assert resolve_zone(_record("m", 1.0, location="patio")) == ("patio", True)


def test_resolve_zone_treats_blank_zone_as_absent() -> None:
    assert resolve_zone(_record("m", 1.0, location="patio", zone="   ")) == (
        "patio",
        True,
    )


def test_resolve_camera_prefers_the_recorded_camera() -> None:
    assert resolve_camera(_record("m", 1.0, camera_id="cam-07")) == ("cam-07", False)


def test_resolve_camera_degrades_to_source_when_absent() -> None:
    assert resolve_camera(_record("m", 1.0, source="camera_alert")) == (
        "camera_alert",
        True,
    )


def test_resolve_camera_treats_blank_camera_as_absent() -> None:
    assert resolve_camera(_record("m", 1.0, source="camera_alert", zone=None)) == (
        "camera_alert",
        True,
    )


def test_helpers_duck_type_objects_without_spatial_fields() -> None:
    class StandIn:
        location = "garage"
        source = "watchdog"

    assert resolve_zone(StandIn()) == ("garage", True)
    assert resolve_camera(StandIn()) == ("watchdog", True)


def test_helpers_tolerate_objects_missing_the_v1_fields_too() -> None:
    assert resolve_zone(object()) == ("", True)
    assert resolve_camera(object()) == ("", True)


# --- engine: spatial relation by zone ---------------------------------------


def test_spatial_groups_by_zone_when_records_carry_it() -> None:
    service = _service(
        _record("m-1", 1.0, location="casa", zone="outdoor"),
        _record("m-2", 2.0, location="casa", zone="outdoor"),
        _record("m-3", 3.0, location="casa", zone="garage"),
    )
    entry = _relate_entry(service, RelationKind.SPATIAL)
    assert entry["relation"] == "spatial"
    assert entry["degraded"] is False
    assert entry["groups"] == {"outdoor": ["m-1", "m-2"], "garage": ["m-3"]}


def test_spatial_degrades_to_location_for_legacy_records() -> None:
    service = _service(
        _record("m-1", 1.0, location="patio"),
        _record("m-2", 2.0, location="kitchen"),
    )
    entry = _relate_entry(service, RelationKind.SPATIAL)
    assert entry["degraded"] is True
    assert "location" in entry["reason"]
    assert entry["groups"] == {"patio": ["m-1"], "kitchen": ["m-2"]}


def test_spatial_folds_missing_zone_into_its_location() -> None:
    service = _service(
        _record("m-1", 1.0, location="casa", zone="outdoor"),
        _record("m-2", 2.0, location="patio"),
    )
    entry = _relate_entry(service, RelationKind.SPATIAL)
    assert entry["degraded"] is True
    assert entry["groups"] == {"outdoor": ["m-1"], "patio": ["m-2"]}


# --- engine: correlation relation by camera ---------------------------------


def test_correlation_groups_by_camera_when_records_carry_it() -> None:
    service = _service(
        _record("m-1", 1.0, source="camera_alert", camera_id="cam-01"),
        _record("m-2", 2.0, source="camera_alert", camera_id="cam-01"),
        _record("m-3", 3.0, source="watchdog", camera_id="cam-02"),
    )
    entry = _relate_entry(service, RelationKind.CORRELATION)
    assert entry["relation"] == "correlation"
    assert entry["degraded"] is False
    assert entry["groups"] == {"cam-01": ["m-1", "m-2"], "cam-02": ["m-3"]}


def test_correlation_degrades_to_source_for_legacy_records() -> None:
    service = _service(
        _record("m-1", 1.0, source="camera_alert"),
        _record("m-2", 2.0, source="watchdog"),
    )
    entry = _relate_entry(service, RelationKind.CORRELATION)
    assert entry["degraded"] is True
    assert "source" in entry["reason"]
    assert entry["groups"] == {"camera_alert": ["m-1"], "watchdog": ["m-2"]}


def test_correlation_splits_one_camera_from_several_by_id() -> None:
    service = _service(
        _record("m-1", 1.0, location="patio", camera_id="cam-01"),
        _record("m-2", 2.0, location="patio", camera_id="cam-01"),
        _record("m-3", 3.0, location="patio", camera_id="cam-02"),
    )
    entry = _relate_entry(service, RelationKind.CORRELATION)
    assert entry["groups"] == {"cam-01": ["m-1", "m-2"], "cam-02": ["m-3"]}


# --- V1 identity ------------------------------------------------------------


def test_legacy_store_keeps_the_pre_a5_spatial_groups() -> None:
    """A store without spatial fields must group exactly as before A5."""
    service = _service(
        _record("m-1", 1.0, location="patio"),
        _record("m-2", 2.0, location="patio"),
        _record("m-3", 3.0, location="kitchen"),
    )
    entry = _relate_entry(service, RelationKind.SPATIAL)
    expected: dict[str, list[str]] = {}
    for record in service.records_between(since=None):
        expected.setdefault(record.location, []).append(record.id)
    assert entry["groups"] == expected


def test_spatial_activation_leaves_episode_relations_untouched() -> None:
    service = _service(
        _record("m-1", 1.0, zone="outdoor", camera_id="cam-01"),
        _record("m-2", 2.0, zone="outdoor", camera_id="cam-01"),
    )
    for relation in (
        RelationKind.EPISODE,
        RelationKind.TIMELINE,
        RelationKind.BEFORE_AFTER,
    ):
        entry = _relate_entry(service, relation)
        assert "groups" not in entry, relation
        assert "camera_id" not in entry, relation


# --- /api/recall payload ----------------------------------------------------


def _evidence(**spatial: object) -> Evidence:
    return Evidence(
        record_id="m-1",
        ts=1.0,
        location="casa",
        labels=("PET",),
        risk="HIGH",
        confidence=0.9,
        snippet="analisis",
        camera_id=spatial.get("camera_id"),
        zone=spatial.get("zone"),
    )


def test_payload_exposes_camera_and_zone() -> None:
    result = RecallResult(
        utterance="algo",
        is_error=False,
        lang="es",
        evidence=(_evidence(camera_id="cam-07", zone="outdoor"),),
        trace=RecallTrace(lang="es", plan={}, ops_executed=(), evidence_ids=("m-1",)),
    )
    payload = recall_result_payload(result)
    item = payload["evidence"][0]  # type: ignore[index]
    assert item["camera_id"] == "cam-07"
    assert item["zone"] == "outdoor"


def test_payload_keeps_the_legacy_evidence_keys() -> None:
    result = RecallResult(
        utterance="algo",
        is_error=False,
        lang="es",
        evidence=(_evidence(),),
        trace=RecallTrace(lang="es", plan={}, ops_executed=(), evidence_ids=("m-1",)),
    )
    item = recall_result_payload(result)["evidence"][0]  # type: ignore[index]
    assert set(item) == {
        "id",
        "ts",
        "location",
        "labels",
        "risk",
        "confidence",
        "camera_id",
        "zone",
    }
    assert item["camera_id"] is None
    assert item["zone"] is None
