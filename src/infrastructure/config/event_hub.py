"""Async broadcast hub for live dashboard events (tool executions).

A minimal in-process pub/sub: subscribers receive an ``asyncio.Queue`` and the
MCP transport publishes tool-lifecycle events into every attached queue. No
external broker is required; a single uvicorn worker keeps publication
loop-safe and avoids any heavy dependency.
"""

from __future__ import annotations

import asyncio
from typing import Any

Event = dict[str, Any]


class EventHub:
    """Broadcast events to one or more ``asyncio.Queue`` subscribers."""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._queues: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        """Create and attach a queue for one consumer (the dashboard SSE)."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._maxsize)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._queues.discard(queue)

    def publish(self, event: Event) -> None:
        """Fan the event out to every attached queue (never blocks)."""
        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)
