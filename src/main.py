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

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.infrastructure.adapters.aws.bedrock_adapter import BedrockLLMAdapter
from src.infrastructure.adapters.aws.fallback_llm_adapter import (
    ResilientLLMAdapter,
    RuleBasedLLMAdapter,
)
from src.infrastructure.adapters.camera.http_phone_camera_adapter import (
    DEFAULT_PHONE_CACHE_TTL,
    DEFAULT_PHONE_TIMEOUT,
    DEFAULT_PHONE_URL,
    HttpPhoneCameraAdapter,
    mount_phone_camera_routes,
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
    CameraFrameSource,
    VivotekCameraAdapter,
    mount_camera_routes,
)
from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.config.telemetry import Telemetry
from src.infrastructure.services.ambient_watch_service import AmbientWatchService
from pydantic import BaseModel

from src.infrastructure.adapters.mcp.memory_resolvers import (
    build_memory_converse_resolver,
)
from src.infrastructure.adapters.mcp.recall_resolvers import (
    recall,
    recall_result_payload,
)
from src.infrastructure.services.demo_seed_service import seed_demo_memory
from src.infrastructure.services.memory_bridge import MemoryBridge
from src.infrastructure.services.memory_service import VectorMemoryService
from src.infrastructure.services.sensor_bus import SimulatedSensorBus

_ENV_MODEL_ID = "ECHOMIND_BEDROCK_MODEL_ID"
_ENV_REGION = "ECHOMIND_BEDROCK_REGION"
_ENV_IDLE_TIMEOUT = "ECHOMIND_SESSION_IDLE_TIMEOUT"
_ENV_KEEPALIVE = "ECHOMIND_SSE_KEEPALIVE_SECONDS"
_ENV_FALLBACK_COOLDOWN = "ECHOMIND_FALLBACK_COOLDOWN_SECONDS"
_ENV_VIVOTEK_IP = "ECHOMIND_VIVOTEK_IP"
_ENV_CAMERA = "CAMERA"
_ENV_PHONE_URL = "PHONE_CAM_URL"
_ENV_PHONE_TIMEOUT = "PHONE_TIMEOUT"
_ENV_PHONE_CACHE_TTL = "PHONE_CACHE_TTL"
_SIMULATION_HOST = "127.0.0.1"

HEALTH_ROUTE = "/health"
METRICS_ROUTE = "/metrics"


def _read_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _read_env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _build_camera() -> CameraFrameSource:
    """Select the active vision source from the environment.

    ``CAMERA=phone`` (or simply defining ``PHONE_CAM_URL``) points EchoMind at an
    Android phone running IP Webcam. ``CAMERA=simulation`` keeps the
    deterministic clean test frame without contacting any hardware. Anything else
    preserves the historical Vivotek FD8367 behaviour.
    """
    mode = os.environ.get(_ENV_CAMERA, "").strip().lower()
    phone_url = os.environ.get(_ENV_PHONE_URL)
    if mode == "phone" or (not mode and phone_url):
        return HttpPhoneCameraAdapter(
            url=phone_url or DEFAULT_PHONE_URL,
            timeout=_read_env_float(_ENV_PHONE_TIMEOUT, DEFAULT_PHONE_TIMEOUT),
            cache_ttl=_read_env_float(_ENV_PHONE_CACHE_TTL, DEFAULT_PHONE_CACHE_TTL),
        )
    if mode == "simulation":
        return VivotekCameraAdapter(host=_SIMULATION_HOST, timeout=0.05)
    return VivotekCameraAdapter(
        host=os.environ.get(_ENV_VIVOTEK_IP, VIVOTEK_DEFAULT_HOST)
    )


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
    camera = _build_camera()
    vivotek_camera = VivotekCameraAdapter(
        host=os.environ.get(_ENV_VIVOTEK_IP, VIVOTEK_DEFAULT_HOST)
    )
    phone_camera = HttpPhoneCameraAdapter(
        url=os.environ.get(_ENV_PHONE_URL, DEFAULT_PHONE_URL),
        timeout=_read_env_float(_ENV_PHONE_TIMEOUT, DEFAULT_PHONE_TIMEOUT),
        cache_ttl=_read_env_float(_ENV_PHONE_CACHE_TTL, DEFAULT_PHONE_CACHE_TTL),
    )
    watch = AmbientWatchService(
        camera=camera,
        sensor_bus=SimulatedSensorBus(),
        event_hub=event_hub,
    )
    memory_service = VectorMemoryService()
    memory_bridge = MemoryBridge(event_hub=event_hub, memory=memory_service)
    mcp_service = build_agentic_tool_registry(
        llm_service,
        camera=camera,
        event_hub=event_hub,
        memory=memory_service,
        current_state_provider=lambda: watch.last_state,
    )
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
    if os.environ.get("ECHOMIND_DEMO_SEED", "0").lower() in ("1", "true", "yes"):
        seed_demo_memory(memory_service)
    mount_dashboard(app, event_hub)
    mount_camera_routes(app, vivotek_camera, watch=watch)
    mount_phone_camera_routes(app, phone_camera, watch=watch)
    mount_memory_api_routes(app, memory_service, watch=watch)
    _attach_watchdog_lifespan(
        app, watch, memory_bridge, cameras=[camera, vivotek_camera, phone_camera]
    )
    return app


class ConverseRequest(BaseModel):
    query: str
    lang: str | None = None


class RecallRequest(BaseModel):
    query: str
    lang: str | None = None
    session_start: float | None = None


def mount_memory_api_routes(
    app: FastAPI,
    memory: VectorMemoryService,
    watch: AmbientWatchService | None = None,
) -> None:
    """Mount lightweight JSON endpoints for dashboard demo seed and converse."""

    @app.post("/api/demo/seed")
    async def post_demo_seed() -> dict[str, object]:
        records = seed_demo_memory(memory)
        return {
            "status": "ok",
            "seeded": len(records),
            "records": [r.id for r in records],
        }

    @app.post("/api/converse")
    async def post_converse(payload: ConverseRequest) -> dict[str, object]:
        query = payload.query.strip()
        if not query:
            return {
                "error": "query is required",
                "is_error": True,
                "response": "",
            }
        state_provider = (lambda: watch.last_state) if watch else None
        resolver = build_memory_converse_resolver(memory, current_state=state_provider)
        resp = await resolver({"query": query, "lang": payload.lang})
        text = resp.content[0].data if resp.content else ""
        return {"response": text, "is_error": resp.is_error}

    @app.post("/api/recall")
    async def post_recall(payload: RecallRequest) -> dict[str, object]:
        """Experimental parallel channel: recall engine answers with evidence."""
        query = payload.query.strip()
        if not query:
            return {
                "error": "query is required",
                "is_error": True,
                "response": "",
            }
        result = recall(
            memory,
            query,
            lang=payload.lang,
            session_start=payload.session_start,
            state_provider=(lambda: watch.last_state) if watch else None,
        )
        return recall_result_payload(result)


def _attach_watchdog_lifespan(
    app: FastAPI,
    watch: AmbientWatchService,
    memory_bridge: MemoryBridge | None = None,
    cameras: list[CameraFrameSource] | None = None,
) -> None:
    """Start/stop the ambient watchdog and memory bridge with the app lifecycle."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = [asyncio.create_task(watch.run())]
        if memory_bridge is not None:
            tasks.append(asyncio.create_task(memory_bridge.run()))
        yield
        watch.stop()
        if memory_bridge is not None:
            memory_bridge.stop()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        for cam in cameras or []:
            try:
                await cam.aclose()
            except Exception:
                pass

    app.router.lifespan_context = lifespan


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
