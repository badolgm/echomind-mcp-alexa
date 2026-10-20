"""Recall engine: executes a :class:`RecallPlan` against the local memory.

Pipeline **retrieve → relate → synthesize**, entirely over
:class:`VectorMemoryService`. It makes no model calls, performs no IO beyond
reading the store, and never mutates V1 state: it is a second, parallel
channel alongside the conversational resolver.

Synthesis is *evidence driven*: :func:`render_synthesis` composes a
question-directed answer (count, direction, timeline, cameras, places) from
the executed trace and the evidence that was actually retrieved, and falls
back to the V1 three-line narration when no structural answer applies — so an
empty result abstains instead of inventing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping

from src.domain.services.context import ContextItem, build_context
from src.domain.services.context_narrative import render_context
from src.domain.services.evidence import (
    Evidence,
    RecallResult,
    RecallTrace,
    render_abstention,
)
from src.domain.services.memory_anchor import AnchorRef, anchor_from_record
from src.domain.services.memory_spatial import resolve_camera, resolve_zone
from src.domain.services.recall_plan import (
    Aggregation,
    Anchor,
    RecallPlan,
    RelationKind,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
    plan_to_dict,
)
from src.domain.services.recall_synthesis import render_synthesis
from src.domain.services.relation import relation_to_dict
from src.domain.services.relation_rules import (
    DEFAULT_MAX_RELATIONS,
    relate_episodes,
)
from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)
from src.infrastructure.services.memory_timeline import (
    DEFAULT_EPISODE_GAP_SECONDS,
    DEFAULT_TIMELINE_GAP_SECONDS,
    Episode,
    build_episodes,
    episodes_before,
    episodes_after,
    timeline_gaps,
)

ENGINE_NAME = "echo-recall"
ENGINE_VERSION = 1

DEFAULT_ANCHOR_SPAN_SECONDS = 300.0


class RecallEngine:
    """Deterministic, LLM-free executor for composable recall plans."""

    def __init__(
        self,
        *,
        memory: VectorMemoryService,
        episode_gap: float = DEFAULT_EPISODE_GAP_SECONDS,
        timeline_gap: float = DEFAULT_TIMELINE_GAP_SECONDS,
        max_relations: int = DEFAULT_MAX_RELATIONS,
        state_provider: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        self._memory = memory
        self._episode_gap = episode_gap
        self._timeline_gap = timeline_gap
        self._max_relations = max_relations
        self._state_provider = state_provider

    def execute(
        self,
        plan: RecallPlan,
        *,
        now: float,
        session_start: float | None = None,
    ) -> RecallResult:
        """Run one plan and return narration, evidence and an audit trace."""
        since, until = _resolve_window(
            plan.window, now=now, session_start=session_start
        )
        ops_executed: list[dict[str, Any]] = []
        records: list[MemoryRecord] = []

        anchor: AnchorRef | None = None
        if plan.anchor is not None:
            anchor = self._resolve_anchor(plan.anchor, ops_executed=ops_executed)
            if anchor is None:
                return _abstain(plan, ops_executed)
            span = _anchor_span(plan.window)
            since, until = anchor.ts - span, anchor.ts + span

        for index, op in enumerate(plan.ops):
            found = self._execute_op(
                op, since=since, until=until, ops_executed=ops_executed, index=index
            )
            records.extend(found)

        ordered = _dedupe_chronological(records)
        evidence = tuple(Evidence.from_record(record) for record in ordered)
        raw_relations, context = self._relate(
            plan,
            ordered,
            ops_executed,
            until=anchor.ts if anchor is not None else until,
        )
        utterance = render_synthesis(
            plan, evidence, ops_executed, context, now=now, lang=plan.lang
        )

        return RecallResult(
            utterance=utterance,
            evidence=evidence,
            trace=RecallTrace(
                lang=plan.lang,
                plan=plan_to_dict(plan),
                ops_executed=tuple(ops_executed),
                evidence_ids=tuple(item.record_id for item in evidence),
                relations=raw_relations,
            ),
            lang=plan.lang,
            context=context,
            context_utterance=render_context(context, lang=plan.lang),
        )

    def _resolve_anchor(
        self, label: str, *, ops_executed: list[dict[str, Any]]
    ) -> AnchorRef | None:
        """Resolve ``label`` to its most recent occurrence, or report the miss.

        The candidate count is recorded so an ambiguous anchor stays visible in
        the trace instead of looking like a unique match.
        """
        entry: dict[str, Any] = {"op": "anchor", "label": label, "found": False}
        record = self._memory.last_seen(label=label)
        if record is None:
            ops_executed.append(entry)
            return None
        anchor = anchor_from_record(
            record,
            label=label,
            candidates=self._memory.count_occurrences(label),
        )
        entry.update(
            {
                "found": True,
                "record_id": anchor.record_id,
                "ts": anchor.ts,
                "candidates": anchor.candidates,
            }
        )
        ops_executed.append(entry)
        return anchor

    def _execute_op(
        self,
        op: RetrieveOp,
        *,
        since: float | None,
        until: float | None,
        ops_executed: list[dict[str, Any]],
        index: int,
    ) -> list[MemoryRecord]:
        filters: dict[str, Any] = {
            "since": since,
            "until": until,
            "location": op.location,
            "risk": op.risk,
            "entity": op.entity,
        }
        found: list[MemoryRecord] = []
        extra: dict[str, Any] = {}

        if op.kind is RetrieveKind.LAST_SEEN:
            record = self._memory.last_seen(label=op.entity, location=op.location)
            if record is not None:
                found = [record]
        elif op.kind is RetrieveKind.SEARCH:
            results = self._memory.search_memory(
                str(op.query or ""),
                limit=op.limit,
                min_score=op.min_score,
                location=op.location,
                risk=op.risk,
            )
            found = [record for record, _score in results]
            filters["query"] = str(op.query or "")
        elif op.kind is RetrieveKind.RANGE:
            found = self._memory.records_between(
                since, until, location=op.location, risk=op.risk
            )
            if op.entity:
                found = [r for r in found if _has_label(r, op.entity)]
        elif op.kind is RetrieveKind.TOP:
            found = self._execute_top(op, since=since)
        elif op.kind is RetrieveKind.AGGREGATE:
            found, extra = self._execute_aggregate(op, since=since, until=until)
        elif op.kind is RetrieveKind.CURRENT_STATE:
            extra.update(self._read_state())

        entry: dict[str, Any] = {
            "op": f"retrieve:{op.kind.value}",
            "index": index,
            "filters": filters,
            "returned_ids": [record.id for record in found],
            "count": len(found),
        }
        entry.update(extra)
        ops_executed.append(entry)
        return found

    def _read_state(self) -> dict[str, Any]:
        """Read the live snapshot for a CURRENT_STATE op, degrading honestly.

        With no provider wired (or one that raises) the op reports
        ``unavailable`` so the synthesizer abstains instead of inventing a
        state. A live provider yields its snapshot verbatim, which the
        synthesizer renders from the real fields only.
        """
        if self._state_provider is None:
            return {"status": "unavailable"}
        try:
            snapshot = self._state_provider() or {}
        except Exception:  # noqa: BLE001 - live state is best-effort
            return {"status": "unavailable"}
        return {"status": "ok", "state": dict(snapshot)}

    def _execute_top(
        self, op: RetrieveOp, *, since: float | None
    ) -> list[MemoryRecord]:
        risk = str(op.risk or "").upper()
        if risk == "CRITICAL":
            return self._memory.recent_critical_events(
                since=since, location=op.location, limit=op.limit
            )
        if risk == "HIGH":
            return self._memory.recent_high_risk_events(
                since=since, location=op.location, limit=op.limit
            )
        return self._memory.top_events(
            since=since, location=op.location, limit=op.limit
        )

    def _execute_aggregate(
        self, op: RetrieveOp, *, since: float | None, until: float | None
    ) -> tuple[list[MemoryRecord], dict[str, Any]]:
        if op.aggregation is Aggregation.COUNT:
            if op.entity:
                value = self._memory.count_occurrences(
                    op.entity, since=since, location=op.location
                )
            else:
                value = self._memory.count_events(
                    op.risk, since=since, location=op.location
                )
            return [], {"aggregation": "count", "value": value}
        if op.aggregation is Aggregation.LIST:
            records = self._memory.top_events(
                since=since, location=op.location, limit=op.limit
            )
            return records, {"aggregation": "list"}
        records = self._memory.records_between(
            since, until, location=op.location, risk=op.risk
        )
        if op.entity:
            records = [r for r in records if _has_label(r, op.entity)]
        counts = self._memory.label_counts(since=since, location=op.location)
        if op.entity:
            counts = {op.entity: counts.get(op.entity, 0)}
        return records, {"aggregation": "summary", "label_counts": counts}

    def _relate(
        self,
        plan: RecallPlan,
        records: list[MemoryRecord],
        ops_executed: list[dict[str, Any]],
        *,
        until: float | None,
    ) -> tuple[tuple[dict[str, object], ...], tuple[ContextItem, ...]]:
        for relation in plan.relations:
            entry: dict[str, Any] = {"op": "relate", "relation": relation.value}
            if relation is RelationKind.EPISODE:
                entry["episodes"] = _episodes_to_dicts(
                    build_episodes(records, gap_seconds=self._episode_gap)
                )
            elif relation is RelationKind.TIMELINE:
                episodes = build_episodes(records, gap_seconds=self._episode_gap)
                entry["episodes"] = _episodes_to_dicts(episodes)
                entry["gaps"] = [
                    {"start": gap.start, "end": gap.end, "seconds": gap.seconds}
                    for gap in timeline_gaps(episodes, max_gap=self._timeline_gap)
                ]
            elif relation is RelationKind.BEFORE_AFTER:
                episodes = build_episodes(records, gap_seconds=self._episode_gap)
                before = (
                    episodes_before(episodes, target_ts=until)
                    if until is not None
                    else ()
                )
                after = (
                    episodes_after(episodes, target_ts=until)
                    if until is not None
                    else ()
                )
                entry["target_ts"] = until
                entry["episodes"] = _episodes_to_dicts(before)
                entry["episodes_after"] = _episodes_to_dicts(after)
                entry["count"] = len(before)
                entry["count_after"] = len(after)
            elif relation is RelationKind.SPATIAL:
                entry.update(_group_by_zone(records))
            elif relation is RelationKind.CORRELATION:
                entry.update(_group_by_camera(records))
            ops_executed.append(entry)

        raw: tuple[dict[str, object], ...] = ()
        ctx: tuple[ContextItem, ...] = ()
        if plan.relations:
            raw, ctx = self._derive_relations(records)
            ops_executed.append(
                {
                    "op": "relate",
                    "relation": "derived",
                    "count": len(raw),
                    "relations": list(raw),
                }
            )
        return raw, ctx

    def _derive_relations(
        self, records: list[MemoryRecord]
    ) -> tuple[tuple[dict[str, object], ...], tuple[ContextItem, ...]]:
        """Compute the pairwise relation graph over the retrieved episodes.

        Returns both views A6e asks for: the raw graph for the audit trace and
        the graded digest for the narrator that arrives in A6f. No text.
        """
        episodes = build_episodes(records, gap_seconds=self._episode_gap)
        relations = relate_episodes(episodes, max_relations=self._max_relations)
        raw = tuple(relation_to_dict(item) for item in relations)
        return raw, build_context(relations)


def _anchor_span(window: TimeWindow) -> float:
    """Seconds of context gathered on each side of a resolved anchor."""
    if window.hours is not None:
        return max(0.0, window.hours) * 3600.0
    return DEFAULT_ANCHOR_SPAN_SECONDS


def _abstain(plan: RecallPlan, ops_executed: list[dict[str, Any]]) -> RecallResult:
    """Answer with nothing when an anchored plan has no anchor to stand on.

    Without the anchor there is no window to rebuild and no comparison to make,
    so the engine abstains rather than answering the unanchored question.
    """
    return RecallResult(
        utterance=render_abstention(lang=plan.lang),
        evidence=(),
        trace=RecallTrace(
            lang=plan.lang,
            plan=plan_to_dict(plan),
            ops_executed=tuple(ops_executed),
            evidence_ids=(),
        ),
        lang=plan.lang,
    )


def _resolve_window(
    window: TimeWindow, *, now: float, session_start: float | None
) -> tuple[float | None, float | None]:
    """Resolve a plan window into absolute bounds, degrading honestly."""
    until = window.until if window.until is not None else now
    if window.anchor is Anchor.SESSION_START and session_start is not None:
        since = session_start
    elif window.since is not None:
        since = window.since
    elif window.hours is not None:
        since = until - window.hours * 3600.0
    else:
        since = None
    return since, until


def _has_label(record: MemoryRecord, label: str) -> bool:
    """Whether a record carries a canonical detection label."""
    return any(str(item.get("label")) == label for item in record.detections)


def _dedupe_chronological(
    records: list[MemoryRecord],
) -> list[MemoryRecord]:
    unique: dict[str, MemoryRecord] = {}
    for record in records:
        unique.setdefault(record.id, record)
    return sorted(unique.values(), key=lambda record: (record.timestamp, record.id))


def _episodes_to_dicts(episodes: list[Episode] | tuple[Episode, ...]) -> list[dict]:
    return [
        {
            "start": episode.start,
            "end": episode.end,
            "location": episode.location,
            "labels": list(episode.labels),
            "risk": episode.risk,
            "count": episode.count,
            "record_ids": list(episode.record_ids),
        }
        for episode in episodes
    ]


def _group_by_zone(records: list[MemoryRecord]) -> dict[str, Any]:
    """Group evidence by zone, degrading to ``location`` when zone is absent."""
    return _spatial_group(records, resolve_zone, "zone", "location")


def _group_by_camera(records: list[MemoryRecord]) -> dict[str, Any]:
    """Group evidence by camera, degrading to ``source`` when camera is absent."""
    return _spatial_group(records, resolve_camera, "camera_id", "source")


def _spatial_group(
    records: list[MemoryRecord],
    resolve: Any,
    field: str,
    fallback: str,
) -> dict[str, Any]:
    """Group ``records`` by a spatial identity, reporting any degradation.

    A record without the precise field is folded into the coarser fallback
    identity, so a store that carries no spatial metadata still groups exactly
    as it did before the spatial fields existed. The entry is only marked
    ``degraded`` when at least one record actually had to fall back, which is
    what keeps the trace honest about the precision of the grouping.
    """
    groups: dict[str, list[str]] = {}
    used_fallback = False
    for record in records:
        key, degraded = resolve(record)
        used_fallback = used_fallback or degraded
        groups.setdefault(key, []).append(record.id)
    if not used_fallback:
        return {"groups": groups, "degraded": False}
    return {
        "groups": groups,
        "degraded": True,
        "reason": f"{field} missing on at least one record; grouped by {fallback}",
    }
