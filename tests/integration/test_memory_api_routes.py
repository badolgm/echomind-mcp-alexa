"""Integration tests for memory API routes (/api/demo/seed and /api/converse)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import compose


@pytest.mark.asyncio
async def test_demo_seed_and_converse_api_end_to_end() -> None:
    app = compose()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Seed demo memory
        seed_resp = await client.post("/api/demo/seed")
        assert seed_resp.status_code == 200
        seed_data = seed_resp.json()
        assert seed_data["status"] == "ok"
        assert seed_data["seeded"] == 5

        # 2. Query in English
        converse_en = await client.post(
            "/api/converse",
            json={"query": "When was the gate last seen open?"},
        )
        assert converse_en.status_code == 200
        data_en = converse_en.json()
        assert data_en["is_error"] is False
        assert "The last detection of the open gate occurred" in data_en["response"]

        # 3. Query in Spanish
        converse_es = await client.post(
            "/api/converse",
            json={"query": "¿Cuándo viste una persona?"},
        )
        assert converse_es.status_code == 200
        data_es = converse_es.json()
        assert data_es["is_error"] is False
        assert "La última detección" in data_es["response"]

        # 4. Explicit lang priority
        converse_forced = await client.post(
            "/api/converse",
            json={"query": "When did you see a pet?", "lang": "es"},
        )
        assert converse_forced.status_code == 200
        data_forced = converse_forced.json()
        assert "La última detección de una mascota" in data_forced["response"]

        # 5. Empty query handling
        converse_empty = await client.post(
            "/api/converse",
            json={"query": "   "},
        )
        assert converse_empty.status_code == 200
        data_empty = converse_empty.json()
        assert data_empty["is_error"] is True
