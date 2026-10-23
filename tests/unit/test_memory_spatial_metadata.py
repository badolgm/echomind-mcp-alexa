"""Unit tests for the Memory Spatial Foundation (A4).

``MemoryRecord`` gains two optional spatial metadata fields (``camera_id`` and
``zone``) that must stay 100% backward compatible: every pre-existing
construction, payload and V1 query has to behave exactly as before.
"""

from __future__ import annotations

from dataclasses import fields

from src.domain.services.evidence import Evidence
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.memory_bridge import (
    MemoryBridge,
    camera_alert_to_memory_record,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)

_TS = 1700000000.0


def _record(**overrides: object) -> MemoryRecord:
    payload: dict[str, object] = {
        "id": "m1",
        "timestamp": _TS,
        "location": "patio",
        "source": "camera_alert",
        "detections": ({"label": "PET", "confidence": 0.9},),
        "risk": "HIGH",
        "model_analysis": "mascota en el patio",
    }
    payload.update(overrides)
    return MemoryRecord(**payload)  # type: ignore[arg-type]


def _alert(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "kind": "camera_alert",
        "risk": "HIGH",
        "status": "HIGH",
        "location": "patio",
        "source": "live",
        "detections": [{"label": "MOTION", "confidence": 0.8}],
        "model_analysis": "movimiento detectado",
        "ts": _TS,
    }
    event.update(overrides)
    return event


# --- defaults ---------------------------------------------------------------


def test_spatial_fields_default_to_none() -> None:
    record = _record()
    assert record.camera_id is None
    assert record.zone is None


def test_legacy_positional_construction_still_works() -> None:
    record = MemoryRecord(
        "m1", _TS, "patio", "camera_alert", ({"label": "PET"},), "HIGH", "x"
    )
    assert record.camera_id is None
    assert record.zone is None


def test_explicit_none_matches_legacy_construction() -> None:
    assert _record() == _record(camera_id=None, zone=None)


# --- compatibility ----------------------------------------------------------


def test_record_stays_frozen_and_slot_sealed() -> None:
    record = _record(camera_id="cam-01", zone="outdoor")
    assert not hasattr(record, "__dict__")
    try:
        record.camera_id = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - guards against losing frozen semantics
        raise AssertionError("MemoryRecord must stay immutable")


def test_spatial_metadata_does_not_change_v1_queries() -> None:
    plain = VectorMemoryService()
    spatial = VectorMemoryService()
    rows = (
        (100.0, "patio", "PET"),
        (200.0, "kitchen", "SMOKE"),
        (300.0, "patio", "PET"),
    )
    for index, (ts, location, label) in enumerate(rows):
        plain.store_memory(
            _record(
                id=f"m{index}",
                timestamp=ts,
                location=location,
                detections=({"label": label},),
                model_analysis=label,
            )
        )
        spatial.store_memory(
            _record(
                id=f"m{index}",
                timestamp=ts,
                location=location,
                detections=({"label": label},),
                model_analysis=label,
                camera_id=f"cam-{index}",
                zone=location,
            )
        )

    assert [r.id for r in spatial.records_between(None, None)] == [
        r.id for r in plain.records_between(None, None)
    ]
    assert (
        spatial.last_seen(label="PET").id
        == plain.last_seen(label="PET").id  # type: ignore[union-attr]
    )
    assert spatial.count_events("HIGH") == plain.count_events("HIGH")
    assert spatial.label_counts(since=None) == plain.label_counts(since=None)
    assert [r.id for r in spatial.top_events(since=None, limit=3)] == [
        r.id for r in plain.top_events(since=None, limit=3)
    ]
    assert spatial.size == plain.size


def test_records_differing_only_spatially_are_distinct() -> None:
    assert _record(camera_id="cam-01") != _record(camera_id="cam-02")
    assert _record(camera_id="cam-01") == _record(camera_id="cam-01")
    assert _record() != _record(zone="outdoor")


# --- serialization ----------------------------------------------------------


def test_public_field_contract_is_locked() -> None:
    assert [field.name for field in fields(MemoryRecord)] == [
        "id",
        "timestamp",
        "location",
        "source",
        "detections",
        "risk",
        "model_analysis",
        "camera_id",
        "zone",
    ]


def test_payload_round_trip_includes_spatial_metadata() -> None:
    record = _record(camera_id="cam-07", zone="outdoor")
    payload = {field.name: getattr(record, field.name) for field in fields(record)}
    assert payload["camera_id"] == "cam-07"
    assert payload["zone"] == "outdoor"
    assert set(payload) == {
        "id",
        "timestamp",
        "location",
        "source",
        "detections",
        "risk",
        "model_analysis",
        "camera_id",
        "zone",
    }
    assert MemoryRecord(**payload) == record  # type: ignore[arg-type]


def test_legacy_payload_without_spatial_fields_loads_unchanged() -> None:
    legacy = {
        "id": "legacy-1",
        "timestamp": 42.0,
        "location": "camera",
        "source": "camera_alert",
        "detections": ({"label": "MOTION"},),
        "risk": "HIGH",
        "model_analysis": "old data",
    }
    record = MemoryRecord(**legacy)
    assert record.camera_id is None
    assert record.zone is None
    assert record.id == "legacy-1"
    assert record.location == "camera"


# --- spatial metadata flowing into evidence --------------------------------


def test_evidence_from_record_carries_spatial_metadata() -> None:
    ev = Evidence.from_record(_record(camera_id="cam-07", zone="outdoor"))
    assert ev.camera_id == "cam-07"
    assert ev.zone == "outdoor"


def test_evidence_from_record_degrades_for_legacy_records() -> None:
    ev = Evidence.from_record(_record())
    assert ev.camera_id is None
    assert ev.zone is None


def test_evidence_from_record_treats_blank_metadata_as_absent() -> None:
    ev = Evidence.from_record(_record(camera_id="  ", zone=""))
    assert ev.camera_id is None
    assert ev.zone is None


def test_evidence_from_record_still_duck_types_bare_objects() -> None:
    class Bare:
        id = "b1"
        timestamp = 1.0
        location = "living"
        detections = ()
        risk = "LOW"
        model_analysis = ""

    ev = Evidence.from_record(Bare())
    assert ev.camera_id is None
    assert ev.zone is None


def test_evidence_defaults_remain_none() -> None:
    ev = Evidence(record_id="r1", ts=1.0)
    assert ev.camera_id is None
    assert ev.zone is None


# --- the bridge keeps the chain intact -------------------------------------


def test_bridge_ingest_leaves_spatial_metadata_absent_by_default() -> None:
    record = camera_alert_to_memory_record(_alert())
    assert record is not None
    assert record.camera_id is None
    assert record.zone is None


def test_bridge_maps_spatial_metadata_when_the_event_carries_it() -> None:
    record = camera_alert_to_memory_record(_alert(camera_id="cam-04", zone="patio"))
    assert record is not None
    assert record.camera_id == "cam-04"
    assert record.zone == "patio"


def test_bridge_ignores_blank_spatial_metadata() -> None:
    record = camera_alert_to_memory_record(_alert(camera_id="  ", zone=None))
    assert record is not None
    assert record.camera_id is None
    assert record.zone is None


def test_bridge_coalescing_preserves_spatial_metadata() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory, episode_gap=30.0)
    shared = {"camera_id": "cam-04", "zone": "patio"}
    first = bridge.ingest(
        _alert(ts=_TS, detections=[{"label": "MOTION", "confidence": 0.8}], **shared)
    )
    merged = bridge.ingest(
        _alert(
            ts=_TS + 1.0, detections=[{"label": "MOTION", "confidence": 0.9}], **shared
        )
    )
    assert first is not None and merged is not None
    assert memory.size == 1
    assert merged.id == first.id
    assert merged.camera_id == "cam-04"
    assert merged.zone == "patio"


def test_bridge_coalescing_is_identity_for_legacy_events() -> None:
    memory = VectorMemoryService()
    bridge = MemoryBridge(event_hub=EventHub(), memory=memory, episode_gap=30.0)
    first = bridge.ingest(_alert(ts=_TS))
    merged = bridge.ingest(_alert(ts=_TS + 1.0))
    assert first is not None and merged is not None
    assert memory.size == 1
    assert merged.camera_id is None
    assert merged.zone is None
    assert merged.detections == first.detections
