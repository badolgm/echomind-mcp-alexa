"""Timeline layer: episodes, ordering and silences over persisted memories.

Rebuilds the episode notion that :class:`MemoryBridge` coalesces in RAM, but
*over the persisted store*, so the ordering survives a restart. Splitting
mirrors the bridge: same location + same detection labels, split when the gap
between consecutive memories exceeds ``gap_seconds``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.infrastructure.services.memory_service import MemoryRecord

DEFAULT_EPISODE_GAP_SECONDS = 30.0
DEFAULT_TIMELINE_GAP_SECONDS = 300.0

_SEVERITY_ORDER: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True, slots=True)
class Episode:
    """A run of consecutive memories that belong to the same occurrence."""

    start: float
    end: float
    location: str
    labels: tuple[str, ...]
    risk: str
    record_ids: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.record_ids)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class TimelineGap:
    """A silence between two consecutive episodes."""

    start: float
    end: float
    seconds: float


def episode_key(record: MemoryRecord) -> tuple[str, tuple[str, ...]]:
    """Identity of an episode: same location + same set of detection labels."""
    return (record.location, labels_of(record))


def labels_of(record: MemoryRecord) -> tuple[str, ...]:
    """Sorted detection labels carried by a record."""
    return tuple(sorted(str(item.get("label") or "") for item in record.detections))


def build_episodes(
    records: Sequence[MemoryRecord],
    *,
    gap_seconds: float = DEFAULT_EPISODE_GAP_SECONDS,
) -> tuple[Episode, ...]:
    """Group memories into chronological episodes, oldest first."""
    ordered = sorted(records, key=lambda record: (record.timestamp, record.id))
    episodes: list[Episode] = []
    key: tuple[str, tuple[str, ...]] | None = None
    last_ts = 0.0
    current: list[MemoryRecord] = []

    for record in ordered:
        record_key = episode_key(record)
        if key is None or record_key != key or record.timestamp - last_ts > gap_seconds:
            if current:
                episodes.append(_to_episode(tuple(current)))
            key = record_key
            current = []
        current.append(record)
        last_ts = record.timestamp

    if current:
        episodes.append(_to_episode(tuple(current)))
    return tuple(episodes)


def timeline_gaps(
    episodes: Sequence[Episode],
    *,
    max_gap: float = DEFAULT_TIMELINE_GAP_SECONDS,
) -> tuple[TimelineGap, ...]:
    """Return the silences longer than ``max_gap`` between consecutive episodes."""
    gaps: list[TimelineGap] = []
    for previous, following in zip(episodes, episodes[1:]):
        seconds = following.start - previous.end
        if seconds > max_gap:
            gaps.append(
                TimelineGap(start=previous.end, end=following.start, seconds=seconds)
            )
    return tuple(gaps)


def episodes_before(
    episodes: Sequence[Episode], *, target_ts: float
) -> tuple[Episode, ...]:
    """Keep the episodes that ended at or before ``target_ts``."""
    return tuple(episode for episode in episodes if episode.end <= target_ts)


def episodes_after(
    episodes: Sequence[Episode], *, target_ts: float
) -> tuple[Episode, ...]:
    """Keep the episodes that started at or after ``target_ts``.

    Directional mirror of :func:`episodes_before`, cutting on ``start`` with
    the inclusive boundary so an episode beginning exactly at the target
    counts as "after" it. Both directions use the same inclusive rule, which
    keeps a target episode reachable from either side of the cut.
    """
    return tuple(episode for episode in episodes if episode.start >= target_ts)


def _to_episode(records: tuple[MemoryRecord, ...]) -> Episode:
    labels: list[str] = []
    for record in records:
        for label in labels_of(record):
            if label and label not in labels:
                labels.append(label)
    return Episode(
        start=records[0].timestamp,
        end=records[-1].timestamp,
        location=records[0].location,
        labels=tuple(sorted(labels)),
        risk=_highest_risk(records),
        record_ids=tuple(record.id for record in records),
    )


def _highest_risk(records: Sequence[MemoryRecord]) -> str:
    best = "LOW"
    best_rank = -1
    for record in records:
        risk = record.risk.upper()
        rank = _SEVERITY_ORDER.index(risk) if risk in _SEVERITY_ORDER else 0
        if rank > best_rank:
            best, best_rank = risk, rank
    return best
