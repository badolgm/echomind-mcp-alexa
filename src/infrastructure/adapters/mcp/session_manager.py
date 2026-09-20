"""In-memory MCP session state management with pluggable persistence.

The transport keeps conversational context between Alexa+ and the MCP server
through persistent sessions. A session holds protocol negotiation state, an
outgoing event queue (delivered by the SSE stream) and a lifecycle flag.

Persistence is abstracted behind :class:`SessionPersistence` so the in-memory
default can be swapped for e.g. DynamoDB, Redis or a database table without
touching the transport layer.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStatus(Enum):
    """Lifecycle state of a transport session."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Serialisable projection of a session for external persistence."""

    session_id: str
    status: SessionStatus
    created_at: str
    last_active: str
    protocol_version: str | None
    is_initialized: bool


@dataclass
class McpSession:
    """Runtime representation of a persistent MCP session."""

    session_id: str
    status: SessionStatus = SessionStatus.INITIALIZING
    created_at: str = field(default_factory=_now_iso)
    last_active: str = field(default_factory=_now_iso)
    protocol_version: str | None = None
    is_initialized: bool = False
    events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)

    def touch(self) -> None:
        self.last_active = _now_iso()

    def mark_initialized(self, protocol_version: str) -> None:
        self.protocol_version = protocol_version
        self.is_initialized = True
        self.status = SessionStatus.ACTIVE
        self.touch()

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.session_id,
            status=self.status,
            created_at=self.created_at,
            last_active=self.last_active,
            protocol_version=self.protocol_version,
            is_initialized=self.is_initialized,
        )

    @classmethod
    def from_snapshot(cls, snapshot: SessionSnapshot) -> McpSession:
        return cls(
            session_id=snapshot.session_id,
            status=snapshot.status,
            created_at=snapshot.created_at,
            last_active=snapshot.last_active,
            protocol_version=snapshot.protocol_version,
            is_initialized=snapshot.is_initialized,
        )


class SessionPersistence(ABC):
    """Storage contract for session lifecycle snapshots.

    Implementations must be passive: they persist an immutable snapshot but
    never decide session lifecycle policy.
    """

    @abstractmethod
    def load(self, session_id: str) -> SessionSnapshot | None: ...

    @abstractmethod
    def save(self, snapshot: SessionSnapshot) -> None: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...


class InMemorySessionPersistence(SessionPersistence):
    """Default persistence backed by a plain dictionary."""

    def __init__(self) -> None:
        self._snapshots: dict[str, SessionSnapshot] = {}

    def load(self, session_id: str) -> SessionSnapshot | None:
        return self._snapshots.get(session_id)

    def save(self, snapshot: SessionSnapshot) -> None:
        self._snapshots[snapshot.session_id] = snapshot

    def delete(self, session_id: str) -> None:
        self._snapshots.pop(session_id, None)


class SessionManager:
    """Owns session lifecycle policy; storage is delegated to persistence.

    The manager is the single input point for session creation, lookup, touch,
    server push and destruction. It keeps a hot in-memory registry synchronised
    with the injected persistence for forward compatibility.
    """

    def __init__(
        self,
        persistence: SessionPersistence | None = None,
        idle_timeout_seconds: int = 300,
    ) -> None:
        self._persistence = persistence or InMemorySessionPersistence()
        self._idle_timeout_seconds = idle_timeout_seconds
        self._sessions: dict[str, McpSession] = {}

    @property
    def idle_timeout_seconds(self) -> int:
        return self._idle_timeout_seconds

    def create(self) -> McpSession:
        session = McpSession(session_id=str(uuid4()))
        self._sessions[session.session_id] = session
        self._persist(session)
        return session

    def get(self, session_id: str | None) -> McpSession | None:
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if session is None:
            snapshot = self._persistence.load(session_id)
            if snapshot is not None:
                session = McpSession.from_snapshot(snapshot)
                self._sessions[session_id] = session
        return session

    def touch(self, session: McpSession) -> None:
        session.touch()
        self._persist(session)

    def destroy(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._persistence.delete(session_id)

    def expire_stale(self) -> int:
        """Destroy idle sessions and report how many were reclaimed."""
        now = datetime.now(timezone.utc)
        stale: list[McpSession] = []
        for session in self._sessions.values():
            try:
                last_active = datetime.fromisoformat(session.last_active)
            except ValueError:
                continue
            idle = (now - last_active).total_seconds()
            if idle > self._idle_timeout_seconds:
                stale.append(session)
        for session in stale:
            self.destroy(session.session_id)
        return len(stale)

    def publish(self, session_id: str, payload: dict[str, Any]) -> bool:
        """Enqueue a server-initiated event for delivery over SSE."""
        session = self.get(session_id)
        if session is None:
            return False
        session.events.put_nowait(payload)
        self.touch(session)
        return True

    def _persist(self, session: McpSession) -> None:
        self._persistence.save(session.snapshot())
