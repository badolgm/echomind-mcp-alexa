"""Integration tests for the experimental /api/recall route.

Proves the parallel recall channel answers with real evidence and an auditable
trace, while /api/converse keeps its verbatim V1 narrative on the very same app.
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.services.evidence import render_abstention
from src.main import compose


@pytest.mark.asyncio
async def test_recall_api_requires_query() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/recall", json={"query": "   "})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_error"] is True
        assert data["response"] == ""


@pytest.mark.asyncio
async def test_recall_api_abstains_before_any_seed() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/recall", json={"query": "¿cuándo viste?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_error"] is False
        assert data["response"] == render_abstention(lang="es")
        assert data["evidence"] == []
        assert data["engine"] == {"name": "echo-recall", "version": 1}
        assert data["trace"]["evidence_ids"] == []


@pytest.mark.asyncio
async def test_recall_api_returns_evidence_and_trace_after_seeding() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        seed = await client.post("/api/demo/seed")
        assert seed.json()["seeded"] == 5

        resp = await client.post(
            "/api/recall", json={"query": "¿cuándo viste una mascota?"}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_error"] is False
        assert "PET" in data["response"]
        assert "patio" in data["response"]

        ids = [item["id"] for item in data["evidence"]]
        assert ids == ["seed-01-pet-patio"]
        assert data["trace"]["evidence_ids"] == ids
        assert data["trace"]["plan"]["lang"] == "es"

        ops = [str(entry.get("op", "")) for entry in data["trace"]["ops"]]
        assert ops == ["retrieve:last_seen", "retrieve:range"]

        first = data["evidence"][0]
        assert first["location"] == "patio"
        assert first["labels"] == ["PET", "GATE_OPEN"]
        assert first["risk"] == "HIGH"
        assert first["confidence"] == 0.95


@pytest.mark.asyncio
async def test_recall_api_honours_session_start_anchor() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/api/demo/seed")
        session_start = time.time() - 3_600.0
        resp = await client.post(
            "/api/recall",
            json={
                "query": "que pase mientras estaba fuera",
                "session_start": session_start,
            },
        )
        data = resp.json()
        assert data["is_error"] is False
        # Every retrieve op is planned against the injected session anchor.
        windows = [
            entry["filters"]["since"]
            for entry in data["trace"]["ops"]
            if str(entry.get("op", "")).startswith("retrieve:")
        ]
        assert windows
        assert all(value == pytest.approx(session_start) for value in windows)


@pytest.mark.asyncio
async def test_converse_and_recall_coexist_on_the_same_app() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/api/demo/seed")

        converse = await client.post(
            "/api/converse", json={"query": "¿Cuándo viste una mascota?"}
        )
        recalled = await client.post(
            "/api/recall", json={"query": "¿Cuándo viste una mascota?"}
        )

        v1 = converse.json()
        v2 = recalled.json()

        assert v1["is_error"] is False and v2["is_error"] is False
        # V1 keeps its verbatim narrative byte for byte.
        assert v1["response"] == (
            "La última detección de una mascota ocurrió hace 6 días en patio."
        )
        # The parallel channel answers from the same store but stays distinct:
        # the HTTP route returns the narration plus the structured evidence.
        assert v2["response"] != v1["response"]
        assert v2["evidence"] != []
