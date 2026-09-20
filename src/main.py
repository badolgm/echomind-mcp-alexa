"""Application entry point: hexagonal composition root.

Wires the concrete adapters (Bedrock, fallback engine, tool resolvers, session
manager, telemetry) into the FastAPI MCP server and exposes the resulting
application to uvicorn.

Run locally with::

    python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

Configuration is read from environment variables so the same binary can run
in AWS Lambda (via ASGI wrapper), ECS/Fargate or a Docker container.
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from src.infrastructure.adapters.aws.bedrock_adapter import BedrockLLMAdapter
from src.infrastructure.adapters.aws.fallback_llm_adapter import (
    ResilientLLMAdapter,
    RuleBasedLLMAdapter,
)
from src.infrastructure.adapters.mcp.fastapi_mcp_adapter import FastAPIMCPServer
from src.infrastructure.adapters.mcp.session_manager import SessionManager
from src.infrastructure.adapters.mcp.tool_resolvers import (
    build_agentic_tool_registry,
)
from src.infrastructure.adapters.mcp.web_dashboard import mount_dashboard
from src.infrastructure.adapters.iot.vivotek_adapter import (
    DEFAULT_HOST as VIVOTEK_DEFAULT_HOST,
)
from src.infrastructure.adapters.iot.vivotek_adapter import (
    VivotekCameraAdapter,
    mount_camera_routes,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.config.telemetry import Telemetry

_ENV_MODEL_ID = "ECHOMIND_BEDROCK_MODEL_ID"
_ENV_REGION = "ECHOMIND_BEDROCK_REGION"
_ENV_IDLE_TIMEOUT = "ECHOMIND_SESSION_IDLE_TIMEOUT"
_ENV_KEEPALIVE = "ECHOMIND_SSE_KEEPALIVE_SECONDS"
_ENV_FALLBACK_COOLDOWN = "ECHOMIND_FALLBACK_COOLDOWN_SECONDS"
_ENV_VIVOTEK_IP = "ECHOMIND_VIVOTEK_IP"

HEALTH_ROUTE = "/health"
METRICS_ROUTE = "/metrics"


def _read_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def compose() -> FastAPI:
    """Build the application graph starting from the environment.

    The LLM port is wrapped in the resilient adapter so Bedrock quota or
    credit failures fail over transparently to the local rule engine without
    breaking the MCP/Alexa+ session. The telemetry registry observes the MCP
    server (latency, tool calls) and listens for fallback activations.
    """
    telemetry = Telemetry()
    event_hub = EventHub()
    llm_service = ResilientLLMAdapter(
        primary=BedrockLLMAdapter(
            model_id=os.environ.get(_ENV_MODEL_ID, "amazon.nova-micro-v1:0"),
            region_name=os.environ.get(_ENV_REGION, "us-east-1"),
        ),
        fallback=RuleBasedLLMAdapter(),
        cooldown_seconds=_read_env_int(_ENV_FALLBACK_COOLDOWN, 300),
        on_fallback=telemetry.fallback_listener,
    )
    camera = VivotekCameraAdapter(
        host=os.environ.get(_ENV_VIVOTEK_IP, VIVOTEK_DEFAULT_HOST)
    )
    mcp_service = build_agentic_tool_registry(llm_service, camera=camera)
    session_manager = SessionManager(
        idle_timeout_seconds=_read_env_int(_ENV_IDLE_TIMEOUT, 300)
    )
    server = FastAPIMCPServer(
        mcp_service=mcp_service,
        session_manager=session_manager,
        keepalive_seconds=_read_env_int(_ENV_KEEPALIVE, 15),
        telemetry=telemetry,
        event_hub=event_hub,
    )
    app = server.app
    app.add_api_route(HEALTH_ROUTE, _health, methods=["GET"])
    app.add_api_route(METRICS_ROUTE, _metrics(telemetry, llm_service), methods=["GET"])
    mount_dashboard(app, event_hub)
    mount_camera_routes(app, camera)
    return app


async def _health() -> dict[str, str]:
    return {"status": "ok", "transport": "mcp/streamable-http"}


def _metrics(telemetry: Telemetry, llm_service: object | None = None):
    """Return a route handler exposing the telemetry snapshot as JSON."""

    async def handler() -> dict:
        snapshot = telemetry.snapshot()
        if llm_service is not None:
            snapshot["provider"] = {
                "active_provider": getattr(llm_service, "active_provider", "primary"),
                "is_degraded": bool(getattr(llm_service, "is_degraded", False)),
                "stats": getattr(llm_service, "stats", {}),
            }
        return snapshot

    return handler


app = compose()


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=os.environ.get("ECHOMIND_HOST", "0.0.0.0"),
        port=_read_env_int("ECHOMIND_PORT", 8000),
    )
