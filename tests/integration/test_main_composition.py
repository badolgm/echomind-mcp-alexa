"""Smoke tests for the hexagonal composition root (src.main)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

import src.main


@pytest.mark.asyncio
async def test_compose_builds_fastapi_app_with_mcp_and_health() -> None:
    assert isinstance(src.main.app, FastAPI)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=src.main.app), base_url="http://test"
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        init = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
        )
        session_id = init.headers.get("Mcp-Session-Id")
        assert session_id is not None

        listing = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Mcp-Session-Id": session_id},
        )
        data_lines = [
            line[5:] for line in listing.text.splitlines() if line.startswith("data:")
        ]
        payload = json.loads(data_lines[-1] if data_lines else listing.text)
        names = {tool["name"] for tool in payload["result"]["tools"]}
        assert {
            "analyze_image_context",
            "summarize_document",
            "schedule_reminder",
        } <= names
