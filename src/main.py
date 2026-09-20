"""Application entry point: hexagonal composition root.

Wires the concrete adapters (Bedrock, tool resolvers, session manager) into
the FastAPI MCP server and exposes the resulting application to uvicorn.

Run locally with::

    python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

Configuration is read from environment variables so the same binary can run
in AWS Lambda (via ASGI wrapper), ECS/Fargate or a local sandbox.
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from src.infrastructure.adapters.aws.bedrock_adapter import BedrockLLMAdapter
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import FastAPIMCPServer
from src.infrastructure.adapters.mcp.session_manager import SessionManager
from src.infrastructure.adapters.mcp.tool_resolvers import (
    build_agentic_tool_registry,
)

_ENV_MODEL_ID = "ECHOMIND_BEDROCK_MODEL_ID"
_ENV_REGION = "ECHOMIND_BEDROCK_REGION"
_ENV_IDLE_TIMEOUT = "ECHOMIND_SESSION_IDLE_TIMEOUT"
_ENV_KEEPALIVE = "ECHOMIND_SSE_KEEPALIVE_SECONDS"

HEALTH_ROUTE = "/health"


def _read_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def compose() -> FastAPI:
    """Build the application graph starting from the environment."""
    llm_service = BedrockLLMAdapter(
        model_id=os.environ.get(_ENV_MODEL_ID, "amazon.nova-micro-v1:0"),
        region_name=os.environ.get(_ENV_REGION, "us-east-1"),
    )
    mcp_service = build_agentic_tool_registry(llm_service)
    session_manager = SessionManager(
        idle_timeout_seconds=_read_env_int(_ENV_IDLE_TIMEOUT, 300)
    )
    server = FastAPIMCPServer(
        mcp_service=mcp_service,
        session_manager=session_manager,
        keepalive_seconds=_read_env_int(_ENV_KEEPALIVE, 15),
    )
    app = server.app
    app.add_api_route(HEALTH_ROUTE, _health, methods=["GET"])
    return app


async def _health() -> dict[str, str]:
    return {"status": "ok", "transport": "mcp/streamable-http"}


app = compose()


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=os.environ.get("ECHOMIND_HOST", "0.0.0.0"),
        port=_read_env_int("ECHOMIND_PORT", 8000),
    )
