"""QW6 goldens: state questions answer honestly through the real HTTP routes.

Both surfaces are exercised on the same app: ``/api/converse`` (V1) and the
experimental ``/api/recall`` channel. A live-like watchdog is injected so the
mandatory answers are pinned end to end, and the idle snapshot is checked for
its honest "no dispongo" degradation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.services.memory_service import VectorMemoryService
from src.main import compose, mount_memory_api_routes


class _Watch:
    """Duck-typed watchdog exposing only what the routes read."""

    def __init__(self, state: dict[str, object]) -> None:
        self.last_state = state


def _live_state() -> dict[str, object]:
    return {
        "risk": "LOW",
        "signals": [],
        "detections": [],
        "temperature_c": 22.4,
        "smoke_density": 0.02,
        "gate_open": False,
        "door_open": False,
        "pet_proximity": 0.12,
        "motion_score": 0.0,
        "source": "live",
        "ts": 1_760_000_000.0,
    }


def _app_with(state: dict[str, object]) -> FastAPI:
    app = FastAPI()
    mount_memory_api_routes(app, VectorMemoryService(), watch=_Watch(state))
    return app


async def _converse(app: FastAPI, query: str, lang: str | None = None) -> str:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/converse", json={"query": query, "lang": lang})
        return resp.json()["response"]


@pytest.mark.asyncio
async def test_converse_goldens_with_live_state_es() -> None:
    app = _app_with(_live_state())
    assert await _converse(app, "¿La reja está cerrada?") == (
        "Sí. La reja se encuentra cerrada actualmente."
    )
    assert await _converse(app, "¿Hay movimiento ahora?") == (
        "No detecto movimiento activo."
    )
    assert await _converse(app, "¿Qué temperatura hay?") == (
        "La temperatura actual es 22.4°C."
    )
    assert await _converse(app, "¿Cuál es el riesgo actual?") == (
        "El nivel de riesgo actual es LOW."
    )


@pytest.mark.asyncio
async def test_converse_golden_en_with_live_state() -> None:
    app = _app_with(_live_state())
    assert await _converse(app, "Is the gate closed?", lang="en") == (
        "Yes. The gate is currently closed."
    )


@pytest.mark.asyncio
async def test_converse_overview_keeps_pinned_v1_answer() -> None:
    app = _app_with(_live_state())
    assert await _converse(app, "¿Qué ocurre ahora?") == (
        "Actualmente no tengo detecciones activas."
    )


@pytest.mark.asyncio
async def test_converse_idle_state_degrades_honestly() -> None:
    idle = {"risk": "LOW", "source": "idle", "detections": [], "announcement": ""}
    app = _app_with(idle)
    assert await _converse(app, "¿La reja está cerrada?") == (
        "No dispongo del estado actual de la reja."
    )
    assert await _converse(app, "¿Qué temperatura hay?") == (
        "No dispongo de la temperatura actual."
    )
    assert await _converse(app, "¿Cuál es el riesgo actual?") == (
        "El nivel de riesgo actual es LOW."
    )


@pytest.mark.asyncio
async def test_observed_bug_query_no_longer_searches_memory() -> None:
    app = _app_with(_live_state())
    answer = await _converse(app, "¿La reja está cerrada?")
    assert "No he encontrado recuerdos" not in answer
    assert answer == "Sí. La reja se encuentra cerrada actualmente."


@pytest.mark.asyncio
async def test_recall_api_answers_state_from_snapshot() -> None:
    app = _app_with(_live_state())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/recall", json={"query": "¿La reja está cerrada?"}
        )
        data = resp.json()

    assert data["is_error"] is False
    assert data["response"] == "Sí. La reja se encuentra cerrada actualmente."
    assert data["evidence"] == []
    assert data["trace"]["plan"]["state_topic"] == "gate"
    assert data["trace"]["plan"]["state_polarity"] == "closed"
    ops = data["trace"]["ops"]
    assert ops[0]["op"] == "retrieve:current_state"
    assert ops[0]["status"] == "ok"
    assert ops[0]["state"]["gate_open"] is False


@pytest.mark.asyncio
async def test_recall_api_is_honest_with_idle_watchdog() -> None:
    # compose() leaves the watchdog idle: no gate_open/temperature_c present.
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/recall", json={"query": "¿La reja está cerrada?"}
        )
        data = resp.json()
    assert data["response"] == "No dispongo del estado actual de la reja."
    assert data["evidence"] == []
    ops = data["trace"]["ops"]
    assert ops[0]["status"] == "ok"
    assert "gate_open" not in ops[0]["state"]
