"""Unit tests for event anchoring (A6c).

Locks the anchoring rule: most recent match, id as a deterministic tie-break,
candidate count carried for transparency, and ``None`` when there is nothing
to anchor to.
"""

from __future__ import annotations

import pytest

from src.domain.services.memory_anchor import (
    AnchorRef,
    anchor_from_record,
    resolve_anchor,
)
from src.infrastructure.services.memory_service import MemoryRecord


def _record(
    record_id: str,
    timestamp: float,
    *,
    labels: tuple[str, ...] = ("PET",),
    location: str = "patio",
    camera_id: str | None = None,
    zone: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.9} for label in labels),
        risk="HIGH",
        model_analysis="",
        camera_id=camera_id,
        zone=zone,
    )


# --- structure --------------------------------------------------------------


def test_anchor_ref_is_frozen() -> None:
    anchor = AnchorRef(record_id="m-1", ts=1.0, label="FALL", location="patio")
    with pytest.raises(Exception):
        anchor.ts = 2.0  # type: ignore[misc]


def test_anchor_ref_has_no_instance_dict() -> None:
    anchor = AnchorRef(record_id="m-1", ts=1.0, label="FALL", location="patio")
    assert not hasattr(anchor, "__dict__")


def test_anchor_defaults_to_one_candidate_and_no_spatial_metadata() -> None:
    anchor = AnchorRef(record_id="m-1", ts=1.0, label="FALL", location="patio")
    assert anchor.candidates == 1
    assert anchor.camera_id is None
    assert anchor.zone is None


# --- resolution -------------------------------------------------------------


def test_resolve_anchor_returns_none_when_nothing_matches() -> None:
    records = [_record("m-1", 100.0, labels=("PET",))]
    assert resolve_anchor(records, label="FALL") is None


def test_resolve_anchor_returns_none_for_an_empty_store() -> None:
    assert resolve_anchor([], label="FALL") is None


def test_resolve_anchor_picks_the_most_recent_match() -> None:
    records = [
        _record("m-1", 100.0, labels=("FALL",)),
        _record("m-2", 900.0, labels=("FALL",)),
        _record("m-3", 500.0, labels=("FALL",)),
    ]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.record_id == "m-2"
    assert anchor.ts == 900.0


def test_resolve_anchor_ties_break_on_id_descending() -> None:
    records = [
        _record("m-1", 500.0, labels=("FALL",)),
        _record("m-2", 500.0, labels=("FALL",)),
    ]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.record_id == "m-2"


def test_resolve_anchor_is_independent_of_input_order() -> None:
    records = [
        _record("m-1", 100.0, labels=("FALL",)),
        _record("m-2", 500.0, labels=("FALL",)),
        _record("m-3", 500.0, labels=("FALL",)),
    ]
    first = resolve_anchor(records, label="FALL")
    second = resolve_anchor(list(reversed(records)), label="FALL")
    assert first == second
    assert first is not None
    assert first.record_id == "m-3"


def test_resolve_anchor_counts_every_match() -> None:
    records = [
        _record("m-1", 100.0, labels=("FALL",)),
        _record("m-2", 200.0, labels=("FALL",)),
        _record("m-3", 300.0, labels=("PET",)),
    ]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.candidates == 2


def test_resolve_anchor_reports_one_candidate_when_unique() -> None:
    records = [_record("m-1", 100.0, labels=("FALL",))]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.candidates == 1


def test_resolve_anchor_matches_on_any_detection_label() -> None:
    records = [_record("m-1", 100.0, labels=("PET", "FALL"))]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.record_id == "m-1"


def test_resolve_anchor_does_not_mutate_input_order() -> None:
    records = [
        _record("m-1", 100.0, labels=("FALL",)),
        _record("m-2", 900.0, labels=("FALL",)),
    ]
    resolve_anchor(records, label="FALL")
    assert [record.id for record in records] == ["m-1", "m-2"]


# --- spatial metadata -------------------------------------------------------


def test_anchor_carries_spatial_metadata_when_present() -> None:
    records = [
        _record("m-1", 900.0, labels=("FALL",), camera_id="cam-07", zone="outdoor")
    ]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.camera_id == "cam-07"
    assert anchor.zone == "outdoor"


def test_anchor_keeps_spatial_metadata_none_for_legacy_records() -> None:
    records = [_record("m-1", 900.0, labels=("FALL",))]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.camera_id is None
    assert anchor.zone is None


# --- duck-typing ------------------------------------------------------------


def test_resolve_anchor_duck_types_objects_without_a_store_model() -> None:
    class StandIn:
        def __init__(self, record_id: str, timestamp: float, labels: tuple) -> None:
            self.id = record_id
            self.timestamp = timestamp
            self.location = "patio"
            self.detections = tuple({"label": label} for label in labels)

    records = [StandIn("s-1", 10.0, ("FALL",)), StandIn("s-2", 20.0, ("FALL",))]
    anchor = resolve_anchor(records, label="FALL")
    assert anchor is not None
    assert anchor.record_id == "s-2"
    assert anchor.candidates == 2


def test_anchor_from_record_normalizes_blank_metadata_to_none() -> None:
    record = _record("m-1", 5.0, camera_id="  ", zone="")
    anchor = anchor_from_record(record, label="FALL", candidates=3)
    assert anchor.camera_id is None
    assert anchor.zone is None
    assert anchor.candidates == 3


def test_anchor_from_record_never_reports_zero_candidates() -> None:
    anchor = anchor_from_record(_record("m-1", 5.0), label="FALL", candidates=0)
    assert anchor.candidates == 1
