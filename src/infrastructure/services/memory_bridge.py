"""Memory bridge: wires real ``camera_alert`` events into the local memory.

Every HIGH/CRITICAL ``camera_alert`` published on the dashboard ``EventHub``
is mapped onto a :class:`MemoryRecord` and persisted through
:class:`VectorMemoryService`, so Alexa+ can later answer historical questions
("cuándo ocurrió por última vez") exclusively from local structured memory.
The bridge is a passive subscriber: it never modifies events, never blocks the
publisher and never consumes a message meant for the dashboard SSE stream.

Because the watchdog publishes one alert per tick (~0.5s) while an episode is
active, consecutive alerts that share the same location and detection set are
*coalesced* into a single episode record (see ``episode_gap``); a walk therefore
becomes one memory, not hundreds of per-tick duplicates.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from src.infrastructure.config.event_hub import Event
from src.infrastructure.services.memory_service import MemoryRecord

if TYPE_CHECKING:
    from src.infrastructure.config.event_hub import EventHub
    from src.infrastructure.services.memory_service import VectorMemoryService

_ALERT_RISK_LEVELS = ("HIGH", "CRITICAL")
_EPISODE_GAP_SECONDS = 30.0


def _episode_key(record: MemoryRecord) -> tuple[str, tuple[str, ...]]:
    """Identity of an episode: same location + same set of detection labels."""
    labels = tuple(sorted(str(item.get("label") or "") for item in record.detections))
    return (record.location, labels)


def _merge_detections(
    first: tuple[dict[str, object], ...],
    second: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Union detections by label, keeping the most recent confidence."""
    merged: dict[str, dict[str, object]] = {}
    for item in first:
        merged[str(item.get("label") or "")] = dict(item)
    for item in second:
        merged[str(item.get("label") or "")] = dict(item)
    return tuple(merged.values())


def camera_alert_to_memory_record(
    event: Event, risk_levels: tuple[str, ...] = _ALERT_RISK_LEVELS
) -> MemoryRecord | None:
    """Map a ``camera_alert`` event onto a ``MemoryRecord`` (None if not one).

    Only events whose ``risk`` (or ``status``) reaches the alert levels are
    considered memorable; everything else is left untouched.
    """
    if event.get("kind") != "camera_alert":
        return None
    risk = str(event.get("risk") or event.get("status") or "LOW").upper()
    if risk not in risk_levels:
        return None
    detections = event.get("detections") or []
    return MemoryRecord(
        id=f"mem-{uuid4().hex[:12]}",
        timestamp=float(event.get("ts") or time.time()),
        location=str(event.get("location") or "home"),
        source=str(event.get("source") or "camera_alert"),
        detections=tuple(dict(item) for item in detections),
        risk=risk,
        model_analysis=str(
            event.get("model_analysis") or event.get("announcement") or ""
        ),
    )


class MemoryBridge:
    """Passive EventHub consumer persisting memorable alerts into the memory."""

    def __init__(
        self,
        *,
        event_hub: EventHub,
        memory: VectorMemoryService,
        risk_levels: tuple[str, ...] = _ALERT_RISK_LEVELS,
        episode_gap: float = _EPISODE_GAP_SECONDS,
    ) -> None:
        self._hub = event_hub
        self._memory = memory
        self._risk_levels = risk_levels
        self._episode_gap = episode_gap
        self._episodes: dict[tuple[str, tuple[str, ...]], MemoryRecord] = {}
        self._queue: asyncio.Queue[Event] | None = None
        self._stop = False

    def attach(self) -> asyncio.Queue[Event]:
        """Subscribe one dedicated queue to the hub (idempotent)."""
        if self._queue is None:
            self._queue = self._hub.subscribe()
        return self._queue

    @property
    def attached(self) -> bool:
        return self._queue is not None

    def ingest(self, event: Event) -> MemoryRecord | None:
        """Map and store one event; consecutive ticks coalesce into episodes."""
        record = camera_alert_to_memory_record(event, self._risk_levels)
        if record is None:
            return None
        key = _episode_key(record)
        existing = self._episodes.get(key)
        if existing is not None and 0.0 <= record.timestamp - existing.timestamp <= (
            self._episode_gap
        ):
            record = MemoryRecord(
                id=existing.id,
                timestamp=record.timestamp,
                location=record.location,
                source=record.source,
                detections=_merge_detections(existing.detections, record.detections),
                risk=record.risk,
                model_analysis=record.model_analysis,
            )
        try:
            self._memory.store_memory(record)
        except MemoryError:
            return None
        self._episodes[key] = record
        return record

    async def consume_next(self) -> MemoryRecord | None:
        """Wait for the next event on the hub and persist it."""
        queue = self.attach()
        event = await queue.get()
        return self.ingest(event)

    async def run(self) -> None:
        """Consume ``camera_alert`` events forever until :meth:`stop`."""
        self.attach()
        while not self._stop:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                self.ingest(event)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop = True
