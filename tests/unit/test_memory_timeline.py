"""Unit tests for the timeline layer (episodes, silences, before, after)."""

from __future__ import annotations

from src.infrastructure.services.memory_service import MemoryRecord
from src.infrastructure.services.memory_timeline import (
    Episode,
    build_episodes,
    episode_key,
    episodes_after,
    episodes_before,
    labels_of,
    timeline_gaps,
)


def _record(
    record_id: str,
    timestamp: float,
    *,
    location: str = "patio",
    risk: str = "LOW",
    labels: tuple[str, ...] = ("PET",),
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        timestamp=timestamp,
        location=location,
        source="camera_alert",
        detections=tuple({"label": label, "confidence": 0.7} for label in labels),
        risk=risk,
        model_analysis="",
    )


def test_episode_key_is_location_and_sorted_labels() -> None:
    first = _record("m1", 1.0, labels=("B", "A"))
    second = _record("m2", 2.0, labels=("A", "B"))
    assert episode_key(first) == episode_key(second)
    assert episode_key(first) == ("patio", ("A", "B"))


def test_episode_key_differs_on_location() -> None:
    assert episode_key(_record("m1", 1.0)) != episode_key(
        _record("m1", 1.0, location="kitchen")
    )


def test_labels_of_is_sorted_and_stringified() -> None:
    assert labels_of(_record("m1", 1.0, labels=("MOTION", "PET"))) == (
        "MOTION",
        "PET",
    )


def test_build_episodes_empty_input() -> None:
    assert build_episodes([]) == ()


def test_build_episodes_orders_ascending() -> None:
    records = [_record("m2", 200.0), _record("m1", 100.0)]
    episodes = build_episodes(records)
    assert [episode.start for episode in episodes] == [100.0, 200.0]


def test_build_episodes_coalesces_within_gap() -> None:
    records = [_record("m1", 100.0), _record("m2", 110.0)]
    episodes = build_episodes(records, gap_seconds=30.0)
    assert len(episodes) == 1
    assert episodes[0].count == 2
    assert episodes[0].record_ids == ("m1", "m2")


def test_build_episodes_splits_when_gap_exceeded() -> None:
    records = [_record("m1", 100.0), _record("m2", 140.0)]
    episodes = build_episodes(records, gap_seconds=30.0)
    assert len(episodes) == 2
    assert episodes[0].record_ids == ("m1",)
    assert episodes[1].record_ids == ("m2",)


def test_build_episodes_splits_on_different_location() -> None:
    records = [
        _record("m1", 100.0, location="patio"),
        _record("m2", 105.0, location="kitchen"),
    ]
    assert len(build_episodes(records)) == 2


def test_build_episodes_splits_on_different_labels() -> None:
    records = [
        _record("m1", 100.0, labels=("PET",)),
        _record("m2", 105.0, labels=("SMOKE",)),
    ]
    assert len(build_episodes(records)) == 2


def test_episode_labels_are_union_and_sorted() -> None:
    records = [
        _record("m1", 100.0, labels=("PET", "MOTION")),
        _record("m2", 110.0, labels=("PET",)),
    ]
    episode = build_episodes(records)[0]
    assert episode.labels == ("MOTION", "PET")


def test_episode_risk_is_the_highest_severity() -> None:
    records = [
        _record("m1", 100.0, risk="LOW"),
        _record("m2", 110.0, risk="CRITICAL"),
        _record("m3", 120.0, risk="HIGH"),
    ]
    assert build_episodes(records)[0].risk == "CRITICAL"


def test_episode_count_and_duration() -> None:
    episodes = build_episodes([_record("m1", 100.0), _record("m2", 120.0)])
    episode = episodes[0]
    assert episode.count == 2
    assert episode.duration == 20.0
    assert episode.end == 120.0


def test_build_episodes_is_deterministic() -> None:
    records = [_record("m1", 100.0), _record("m2", 140.0), _record("m3", 200.0)]
    assert build_episodes(records) == build_episodes(list(reversed(records)))


def test_timeline_gaps_detects_silences() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 2000.0)], gap_seconds=30.0
    )
    gaps = timeline_gaps(episodes, max_gap=300.0)
    assert len(gaps) == 1
    assert gaps[0].start == 100.0
    assert gaps[0].end == 2000.0
    assert gaps[0].seconds == 1900.0


def test_timeline_gaps_ignores_short_silences() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 250.0)], gap_seconds=30.0
    )
    assert timeline_gaps(episodes, max_gap=300.0) == ()


def test_timeline_gaps_single_episode_is_empty() -> None:
    episodes = build_episodes([_record("m1", 100.0)])
    assert timeline_gaps(episodes) == ()


def test_episodes_before_filters_by_target() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 500.0), _record("m3", 900.0)],
        gap_seconds=30.0,
    )
    before = episodes_before(episodes, target_ts=500.0)
    assert [episode.start for episode in before] == [100.0, 500.0]


def test_episodes_before_all_after_target_is_empty() -> None:
    episodes = build_episodes([_record("m1", 900.0)])
    assert episodes_before(episodes, target_ts=100.0) == ()


def test_episodes_after_filters_by_target() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 500.0), _record("m3", 900.0)],
        gap_seconds=30.0,
    )
    after = episodes_after(episodes, target_ts=500.0)
    assert [episode.start for episode in after] == [500.0, 900.0]


def test_episodes_after_all_before_target_is_empty() -> None:
    episodes = build_episodes([_record("m1", 100.0)])
    assert episodes_after(episodes, target_ts=900.0) == ()


def test_episodes_after_includes_the_episode_starting_on_target() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 500.0)],
        gap_seconds=30.0,
    )
    assert [episode.start for episode in episodes_after(episodes, target_ts=500.0)] == [
        500.0
    ]


def test_episodes_before_and_after_partition_the_timeline() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 500.0), _record("m3", 900.0)],
        gap_seconds=30.0,
    )
    for target in (100.0, 500.0, 900.0, 0.0, 10000.0):
        kept = {
            episode.start for episode in episodes_before(episodes, target_ts=target)
        } | {episode.start for episode in episodes_after(episodes, target_ts=target)}
        assert kept == {episode.start for episode in episodes}


def test_episodes_after_preserves_order() -> None:
    episodes = build_episodes(
        [_record("m1", 100.0), _record("m2", 500.0), _record("m3", 900.0)],
        gap_seconds=30.0,
    )
    assert [episode.start for episode in episodes_after(episodes, target_ts=0.0)] == [
        100.0,
        500.0,
        900.0,
    ]


def test_episode_is_frozen() -> None:
    episode = Episode(
        start=1.0,
        end=2.0,
        location="patio",
        labels=(),
        risk="LOW",
        record_ids=(),
    )
    assert not hasattr(episode, "__dict__")
