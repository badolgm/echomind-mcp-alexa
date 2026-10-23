"""QW3/QW4: the live-state provider reaches the recall engine's op.

The engine reports the real snapshot on a ``CURRENT_STATE`` op (or
``unavailable`` when nothing is wired), and never touches the memory store to
do it. Rendering that snapshot into an answer is A7C policy 0 (QW5).
"""

from __future__ import annotations

import pytest

from src.domain.services.recall_plan import (
    Anchor,
    RecallPlan,
    RetrieveKind,
    RetrieveOp,
    TimeWindow,
)
from src.infrastructure.services.memory_service import VectorMemoryService
from src.infrastructure.services.recall_engine import RecallEngine

NOW = 1_700_000_000.0


def _state() -> dict[str, object]:
    return {
        "risk": "LOW",
        "detections": [],
        "temperature_c": 22.4,
        "gate_open": False,
        "door_open": False,
        "source": "live",
    }


def _plan(*ops: RetrieveOp) -> RecallPlan:
    return RecallPlan(
        lang="es",
        window=TimeWindow(anchor=Anchor.NOW),
        ops=ops or (RetrieveOp(kind=RetrieveKind.CURRENT_STATE),),
    )


def test_current_state_op_reports_live_snapshot() -> None:
    engine = RecallEngine(memory=VectorMemoryService(), state_provider=_state)
    result = engine.execute(_plan(), now=NOW)
    entry = result.trace.ops_executed[0]
    assert entry["op"] == "retrieve:current_state"
    assert entry["status"] == "ok"
    assert entry["state"]["gate_open"] is False
    assert entry["state"]["temperature_c"] == 22.4
    assert result.evidence == ()


def test_current_state_op_without_provider_is_unavailable() -> None:
    engine = RecallEngine(memory=VectorMemoryService())
    result = engine.execute(_plan(), now=NOW)
    assert result.trace.ops_executed[0]["status"] == "unavailable"


def test_current_state_op_survives_a_failing_provider() -> None:
    def boom() -> dict[str, object]:
        raise RuntimeError("camera down")

    engine = RecallEngine(memory=VectorMemoryService(), state_provider=boom)
    result = engine.execute(_plan(), now=NOW)
    assert result.trace.ops_executed[0]["status"] == "unavailable"


def test_current_state_op_does_not_touch_the_store() -> None:
    service = VectorMemoryService()
    engine = RecallEngine(memory=service, state_provider=_state)
    before = service.size
    engine.execute(_plan(), now=NOW)
    assert service.size == before


def test_state_provider_is_called_lazily() -> None:
    calls = {"n": 0}

    def provider() -> dict[str, object]:
        calls["n"] += 1
        return _state()

    engine = RecallEngine(memory=VectorMemoryService(), state_provider=provider)
    assert calls["n"] == 0
    engine.execute(_plan(), now=NOW)
    assert calls["n"] == 1


@pytest.mark.parametrize("kind", [RetrieveKind.LAST_SEEN, RetrieveKind.SEARCH])
def test_provider_not_consulted_for_other_ops(kind: RetrieveKind) -> None:
    calls = {"n": 0}

    def provider() -> dict[str, object]:
        calls["n"] += 1
        return _state()

    engine = RecallEngine(memory=VectorMemoryService(), state_provider=provider)
    engine.execute(_plan(RetrieveOp(kind=kind, entity="PET", query="mascota")), now=NOW)
    assert calls["n"] == 0
