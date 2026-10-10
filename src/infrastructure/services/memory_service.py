"""Local vectorial memory service (Qdrant Edge inspired) for EchoMind MCP.

Persists and recalls ``camera_alert``-shaped observations as vector points.
Each :class:`MemoryRecord` is embedded as a deterministic, hashed
term-frequency vector (L2-normalized) so similarity is a pure dot product with
no external model, index or network — the edge engine keeps reasoning behind
the Quota Fallback Protocol. A :class:`MemoryVectorStorePort` contracts the
future Qdrant Edge adapter (collection schema, Cosine distance, payload
filters); that adapter is deliberately **not** implemented yet.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

EMBED_DIMENSIONS = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_RISK_SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """One persisted observation in the local memory store."""

    id: str
    timestamp: float
    location: str
    source: str
    detections: tuple[dict[str, object], ...]
    risk: str
    model_analysis: str


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(text.lower()))


def embed_text(text: str) -> tuple[float, ...]:
    """Deterministic hashed term-frequency embedding (no model, no network)."""
    vector = [0.0] * EMBED_DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % EMBED_DIMENSIONS
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return (0.0,) * EMBED_DIMENSIONS
    return tuple(round(value / norm, 6) for value in vector)


def _cosine_similarity(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(first, second))


def _record_has_label(record: MemoryRecord, label: str) -> bool:
    return any(str(item.get("label")) == label for item in record.detections)


class MemoryVectorStorePort(Protocol):
    """Qdrant Edge contract (future adapter target, not implemented).

    point_id -> ``MemoryRecord.id``
    vector   -> ``embed_text(...)``
    payload  -> MemoryRecord fields minus ``id``
    filters  -> payload equality on ``location`` / ``risk`` / ``source``
    distance -> Cosine
    limit    -> top-k by score, descending
    """

    def upsert(self, record: MemoryRecord, vector: tuple[float, ...]) -> None: ...

    def query(
        self,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: dict[str, str],
    ) -> list[tuple[str, float]]: ...

    def delete(self, record_id: str) -> bool: ...


class VectorMemoryService:
    """In-memory vector store implementing the memory capabilities.

    The local engine is authoritative today; swapping ``_records``/``_vectors``
    for :class:`MemoryVectorStorePort` keeps the same public API.
    """

    def __init__(self, max_records: int = 2000) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._max_records = max_records

    def store_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Persist an observation and compute its embedding."""
        if len(self._records) >= self._max_records and record.id not in self._records:
            raise MemoryError("local memory store is full")
        sources = [record.location, record.source, record.risk, record.model_analysis]
        sources.extend(str(item.get("label") or "") for item in record.detections)
        self._records[record.id] = record
        self._vectors[record.id] = embed_text(" ".join(sources))
        return record

    def search_memory(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        location: str | None = None,
        risk: str | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Return the top-k relevant memories, nearest semantic match first."""
        query_vector = embed_text(query)
        scored: list[tuple[MemoryRecord, float]] = []
        for record_id, vector in self._vectors.items():
            record = self._records[record_id]
            if location is not None and record.location != location:
                continue
            if risk is not None and record.risk != risk:
                continue
            score = _cosine_similarity(query_vector, vector)
            if score >= min_score:
                scored.append((record, round(score, 4)))
        scored.sort(key=lambda pair: (-pair[1], -pair[0].timestamp))
        return scored[:limit]

    def last_seen(
        self,
        *,
        label: str | None = None,
        location: str | None = None,
        source: str | None = None,
    ) -> MemoryRecord | None:
        """Return the most recent memory matching the optional filters.

        ``label`` matches the canonical detection label carried by the record
        (for example ``GATE_OPEN``, ``PET`` or ``PERSON_ELDERLY``).
        """
        latest: MemoryRecord | None = None
        for record in self._records.values():
            if label is not None and not _record_has_label(record, label):
                continue
            if location is not None and record.location != location:
                continue
            if source is not None and record.source != source:
                continue
            if latest is None or record.timestamp > latest.timestamp:
                latest = record
        return latest

    def count_occurrences(
        self,
        label: str,
        *,
        since: float | None = None,
        location: str | None = None,
    ) -> int:
        """Count stored memories that carry a canonical detection label.

        ``since`` filters to records with ``timestamp >= since``.
        """
        count = 0
        for record in self._records.values():
            if location is not None and record.location != location:
                continue
            if since is not None and record.timestamp < since:
                continue
            if _record_has_label(record, label):
                count += 1
        return count

    def label_counts(
        self,
        *,
        since: float | None = None,
        location: str | None = None,
    ) -> dict[str, int]:
        """Aggregate per-label occurrence counts across stored memories."""
        counts: dict[str, int] = {}
        for record in self._records.values():
            if location is not None and record.location != location:
                continue
            if since is not None and record.timestamp < since:
                continue
            for item in record.detections:
                label = str(item.get("label") or "")
                if label:
                    counts[label] = counts.get(label, 0) + 1
        return counts

    def forget_memory(self, record_id: str) -> bool:
        """Remove one memory by id; returns ``True`` when it existed."""
        if record_id not in self._records:
            return False
        del self._records[record_id]
        self._vectors.pop(record_id, None)
        return True

    def count_events(
        self,
        risk: str | None = None,
        *,
        since: float | None = None,
        location: str | None = None,
    ) -> int:
        """Count stored events, optionally filtered by risk level."""
        normalized_risk = risk.upper() if risk else None
        count = 0
        for record in self._records.values():
            if normalized_risk is not None and record.risk.upper() != normalized_risk:
                continue
            if location is not None and record.location != location:
                continue
            if since is not None and record.timestamp < since:
                continue
            count += 1
        return count

    def top_events(
        self,
        *,
        since: float | None = None,
        location: str | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Return the most relevant events: severest risk, most recent first."""
        ranked = [
            record
            for record in self._records.values()
            if _RISK_SEVERITY.get(record.risk.upper(), 0) >= 2
            and (location is None or record.location == location)
            and (since is None or record.timestamp >= since)
        ]
        ranked.sort(
            key=lambda record: (
                -_RISK_SEVERITY.get(record.risk.upper(), 0),
                -record.timestamp,
            )
        )
        return ranked[:limit]

    def recent_high_risk_events(
        self,
        *,
        since: float | None = None,
        location: str | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Return the most recent HIGH risk events."""
        return self._risk_events("HIGH", since=since, location=location, limit=limit)

    def recent_critical_events(
        self,
        *,
        since: float | None = None,
        location: str | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Return the most recent CRITICAL events."""
        return self._risk_events(
            "CRITICAL", since=since, location=location, limit=limit
        )

    def _risk_events(
        self,
        risk: str,
        *,
        since: float | None = None,
        location: str | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        matching = [
            record
            for record in self._records.values()
            if record.risk.upper() == risk.upper()
            and (location is None or record.location == location)
            and (since is None or record.timestamp >= since)
        ]
        matching.sort(key=lambda record: -record.timestamp)
        return matching[:limit]

    @property
    def size(self) -> int:
        return len(self._records)
