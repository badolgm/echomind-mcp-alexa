"""QW5: state questions become live-state plans and answer from the snapshot."""

from __future__ import annotations

from typing import Any

from src.domain.services.recall_plan import RetrieveKind, plan_to_dict
from src.domain.services.recall_planner import understand
from src.domain.services.recall_synthesis import render_synthesis
from src.infrastructure.adapters.mcp.recall_resolvers import recall
from src.infrastructure.services.memory_service import VectorMemoryService

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


def _op_entry(status: str = "ok", **state: object) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "op": "retrieve:current_state",
        "index": 0,
        "filters": {},
        "returned_ids": [],
        "count": 0,
        "status": status,
    }
    if status == "ok":
        entry["state"] = state
    return entry


def test_understand_gate_question_becomes_state_plan() -> None:
    plan = understand("¿La reja está cerrada?", now=NOW)
    assert plan.state_topic == "gate"
    assert plan.state_polarity == "closed"
    assert plan.lang == "es"
    assert [op.kind for op in plan.ops] == [RetrieveKind.CURRENT_STATE]


def test_understand_overview_question_becomes_state_plan() -> None:
    plan = understand("¿Qué ocurre ahora?", now=NOW)
    assert plan.state_topic == "overview"


def test_understand_memory_question_stays_a_memory_plan() -> None:
    plan = understand("¿Cuándo viste una mascota?", now=NOW)
    assert plan.state_topic is None
    assert plan.state_polarity is None
    assert all(op.kind is not RetrieveKind.CURRENT_STATE for op in plan.ops)


def test_plan_to_dict_exposes_state_fields() -> None:
    plan = understand("¿Hay movimiento ahora?", now=NOW)
    data = plan_to_dict(plan)
    assert data["state_topic"] == "motion"
    assert data["state_polarity"] is None


def test_synthesis_policy_zero_renders_the_live_state() -> None:
    plan = understand("¿La reja está cerrada?", now=NOW)
    ops = [_op_entry("ok", **_state())]
    answer = render_synthesis(plan, (), ops, (), now=NOW, lang="es")
    assert answer == "Sí. La reja se encuentra cerrada actualmente."


def test_synthesis_policy_zero_answers_overview_from_snapshot() -> None:
    plan = understand("¿Qué ocurre ahora?", now=NOW)
    ops = [_op_entry("ok", **_state())]
    answer = render_synthesis(plan, (), ops, (), now=NOW, lang="es")
    assert answer.startswith("El nivel de riesgo actual es LOW.")


def test_synthesis_policy_zero_is_honest_without_live_state() -> None:
    plan = understand("¿La reja está cerrada?", now=NOW)
    ops = [_op_entry("unavailable")]
    answer = render_synthesis(plan, (), ops, (), now=NOW, lang="es")
    assert answer == "No dispongo del estado actual de la reja."


def test_synthesis_ignores_the_op_when_the_plan_has_no_topic() -> None:
    plan = understand("¿Cuándo viste una mascota?", now=NOW)
    ops = [_op_entry("ok", **_state())]
    answer = render_synthesis(plan, (), ops, (), now=NOW, lang="es")
    assert answer != "El nivel de riesgo actual es LOW."


def test_recall_threads_the_provider_into_the_state_answer() -> None:
    result = recall(
        VectorMemoryService(),
        "¿El riesgo actual?",
        now=NOW,
        state_provider=_state,
    )
    assert result.utterance == "El nivel de riesgo actual es LOW."
    assert result.evidence == ()
    assert result.trace.ops_executed[0]["status"] == "ok"
