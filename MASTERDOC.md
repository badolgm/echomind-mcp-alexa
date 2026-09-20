# MASTERDOC — Echosystem · echomind-mcp-alexa

**Definitive technical document**
Amazon Developer Hackathon — Build, Ship, Shape 2026

| | |
| --- | --- |
| Product | Echosystem — Active Ambient Awareness for Alexa+ |
| Repo | `echomind-mcp-alexa` |
| Owner | Badolgm |
| License | MIT (2026) |
| Stack | Python 3.11 · FastAPI · AWS Bedrock (boto3) · MCP Streamable HTTP |

---

## 1. Problem

Smart-assistant skills today are **reactive and single-shot**: a user speaks, a model answers.
Nothing watches over the home. Falls of elderly adults go unnoticed, pets are left unattended,
smoke and intrusions are only reported if someone happens to ask. At the same time, connecting a
rich, tool-using model to a voice assistant is fragmented: every skill reinvents its own
tooling, state and I/O patterns.

## 2. Value proposition: Active Ambient Awareness

Echosystem turns Alexa+ into a **proactive caregiver and guardian**, not just a responder.
It continuously ingests ambient snapshots (visual, audio, sensor text) and produces **risk-graded
awareness reports** with a recommended action for Alexa+ to speak or escalate.

Four agentic tools back the ecosystem:

1. `analyze_ambient_stream` — **safety**: elder falls, immobility, smoke/fire, intrusions,
   unattended pets.
2. `analyze_image_context` — multimodal image/video understanding.
3. `summarize_document` — faithful document extraction (PDF, DOCX, XLSX, text, markdown).
4. `schedule_reminder` — time-based productivity.

Every ambient snapshot is graded twice, independently:

- a **deterministic safety gate** (zero dependencies, guaranteed output), and
- a **reasoning model** via Amazon Bedrock.

Critical signals are therefore reported even when the cloud is unavailable.

## 3. Why MCP × Alexa+

The **Model Context Protocol** decouples the assistant from the tools it uses. Alexa+ becomes a
client that discovers tools over a standard, typed JSON-RPC contract; the ecosystem evolves its
catalog without touching the skill. This repo implements the **HTTP Streamable transport**
(spec `2025-11-25`): a stateless-friendly, long-lived streaming connection that works behind
standard load balancers and cloud runtimes.

### 3.1 Session lifecycle

```
Alexa+ (client)                     MCP server
    │  POST initialize                  │
    ├───────────────────────────────────►│  create session
    │◄───────────────────────────────────┤  SSE stream: event: endpoint + mcp-jsonrpc result
    │               [Mcp-Session-Id]     │
    │  POST notifications/initialized    │
    ├───────────────────────────────────►│  mark ACTIVE → 202
    │  GET /mcp (SSE)  ◄─────────────────┤  server-initiated events + keep-alive
    │  POST tools/list · tools/call      │
    │◄───────────────────────────────────┤  JSON-RPC results (JSON or SSE per Accept)
    │  stream closes                     │
    │      ...                           │  session destroyed on stream end / idle expiry
```

Sessions are managed by `SessionManager` (lifecycle policy) over a `SessionPersistence` contract
(swappable: in-memory today, DynamoDB/Redis tomorrow) — state survives restart and can be restored
from a snapshot.

## 4. Hexagonal architecture & DDD layers

Strict dependency inversion: **domain → application → infrastructure**, never the reverse.

```
┌──────────────────────────────────────────────────────────────────┐
│                      ADAPTERS (edges)                            │
│  FastAPI MCP Streamable HTTP                                    │
│  AWS Bedrock (Converse) · ResilientLLMAdapter                   │
│  RuleBasedLLMAdapter (fallback) · Tool resolvers               │
└───────────────▲───────────────────────────▲─────────────────────┘
                │         implements        │
   ┌────────────┴──────────┐   ┌────────────┴──────────────┐
   │  MCPServerPort        │   │  LLMServicePort           │
   │  (output / domain)    │   │  (output / domain)        │
   └────────────▲──────────┘   └────────────▲──────────────┘
                │            depends on      │
   ┌────────────┴────────────────────────────┴──────────────┐
   │            APPLICATION (use cases)                     │
   │   ProcessIntentUseCase · ProcessMultimodalIntent       │
   └─────────────────────────▲──────────────────────────────┘
                             │
   ┌─────────────────────────┴──────────────────────────────┐
   │          DOMAIN (pure core, zero dependencies)          │
   │  UserIntent · AgentTool catalog · Modality             │
   │  Value Objects · Ports (ABC)                           │
   └─────────────────────────────────────────────────────────┘
```

### Contract guarantees

| Layer | Allowed dependencies | Forbidden |
| ----- | -------------------- | --------- |
| `src/domain/` | stdlib (`dataclasses`, `abc`, `typing`, `enum`) | FastAPI, boto3, MCP SDK, IO |
| `src/application/` | domain + own DTOs | direct framework/SDK calls |
| `src/infrastructure/` | anything (adapters) | business decisions |
| `tests/` | everything | network/AWS at runtime |

Consequences: new LLM providers, transports or persistence are **additive**; business logic never
changes when the cloud provider, framework version or session store changes.

## 5. Domain catalog

`src/domain/models/tools.py` is a pure domain module. `AgentTool` carries a JSON-Schema-like
`input_schema` and derives `required_fields` for argument validation. The `AGENTIC_TOOL_CATALOG`
is the single source of truth the infrastructure registers into MCP, one resolver per tool.

## 6. Multimodal reasoning (AWS Bedrock)

`BedrockLLMAdapter` implements `LLMServicePort` over the **Converse API**:

- input blocks for `image/ jpeg|png|gif|webp`, `video/ mp4|mov|webm|mkv`,
  `audio/ mp3|wav|flac`, `document/ pdf|docx|xlsx|csv|txt|md`, and `text`;
- synchronous boto3 wrapped with `asyncio.to_thread` so the event loop never blocks;
- MIME → format mapping and modality derivation live in infrastructure only.

## 7. Quota Fallback Protocol (QFP) — resilience procedure

**Objective.** Continued 24/7 operation of the MCP server and Alexa+ sessions even when the AWS
provider is throttled, quota-exhausted, credential-less or unreachable.

**Definition.** `ResilientLLMAdapter` decorators any `LLMServicePort` (primary = Bedrock).
On an AWS failure classified by `is_quota_error`, it switches to a deterministic local engine
(`RuleBasedLLMAdapter`) that implements the same contract. Full circuit-breaker semantics:

```
REQUEST → if degraded AND cooldown not elapsed ───► FALLBACK (skip primary)
        │
        ▼
        try PRIMARY ── success ──► RESET breaker, return primary response
        │
        error
        ▼
        is_quota_error?  no ──► propagate (real bug)
        │ yes
        ▼
        DEGRADE (cooldown = ECHOMIND_FALLBACK_COOLDOWN_SECONDS) → FALLBACK response
        │
        (after cooldown, probe primary again; success clears degradation)
```

**Trigger classification** (`is_quota_error`):

- `ClientError` codes: `Throttling`, `ThrottlingException`, `TooManyRequestsException`,
  `ServiceQuotaExceededException`, `QuotaExceededException`, `AccessDeniedException`,
  `ModelNotReadyException`, `ModelStreamLimitExceededException`, transient 429/5xx HTTP status;
- connection/timeout errors: `ConnectTimeoutError`, `ReadTimeoutError`,
  `EndpointConnectionError`, `HTTPClientError`;
- missing credentials: `NoCredentialsError`, `PartialCredentialsError`.

**Fallback engine (`RuleBasedLLMAdapter`).** Deterministic (same input → same output) and
domain-aware:

- CRITICAL — possible fall/immobility, smoke/fire, person on the floor;
- HIGH — security intrusion/unknown person;
- MEDIUM — unattended/distressed pet;
- classification mode emits strict JSON so the intent router keeps working;
- document, reminder and generic modes cover the rest of the catalog.

**Observability.** `active_provider`, `is_degraded` and `stats` (`primary_attempts`,
`fallback_calls`, `failovers`) make the current provider and failover count inspectable.

**Guarantees.** Traversal of the port contract (typed `LLMRequest` → `LLMResponse`), no import of
domain into infrastructure, no disruption to MCP `tools/call` semantics. Verified live: the server
answered a CRITICAL ambient alert with **no AWS credentials configured** on the host.

## 8. Ambient safety gate

`scan_ambient_signals` is an LLM-free risk grader exposed by the `analyze_ambient_stream`
resolver. Priority ladder CRITICAL > HIGH > MEDIUM > LOW with fixed recommendations, so safety
reporting never depends on model availability or cost budgets.

## 9. Performance (measured)

In-process round trips, Streamable HTTP over ASGI (development laptop):

| Operation | Mean | p50 | p95 | Throughput |
| --------- | ---- | --- | --- | ---------- |
| `tools/list` | 0.73 ms | 0.69 ms | 0.94 ms | ≈ 1 360 req/s |
| `tools/call` | 0.77 ms | 0.69 ms | 1.19 ms | ≈ 1 300 req/s |

## 10. Testing & quality gates

- 102 tests across `tests/unit` (domain, use cases, adapters, fallback, ambient, vivotek,
  dashboard, ambient watchdog/sensor bus) and `tests/integration` (SSE session lifecycle,
  composition smoke, telemetry, skill manifest).
- All ports are mocked: suite runs offline.
- Mandatory before completing any phase:
  ```powershell
  pytest -q
  flake8 src tests
  black --check src tests --line-length 88
  ```

## 11. Production entry point

`src/main.py` is the composition root (IoC): builds `ResilientLLMAdapter` → tool registry →
`SessionManager` → `FastAPIMCPServer`, exposes `/health` and `/metrics`, reads the environment
(`ECHOMIND_*`), and serves via `python -m uvicorn src.main:app`. The same ASGI app can run on
ECS/Fargate, AWS Lambda (Mangum-style wrapper) or the provided multi-stage Docker image without
code changes.

## 12. Observability & deployment

- `src/infrastructure/config/telemetry.py` — dependency-free, thread-safe registry: request
  latency percentiles (p50/p95/p99, nearest-rank), per-tool call counters and quota-fallback
  activations. Instrumented at the MCP transport (method-level) and wired to the resilience layer
  via a listener callback injected by the composition root.
- `GET /metrics` returns the JSON snapshot; used by `run_demo.py` and any Prometheus/Grafana
  scraper. `GET /health` feeds the Docker healthcheck.
- `alexa_skill/skill.json` — Alexa+ Agent Skill manifest bound to `https://<host>/mcp`
  (Streamable HTTP, protocol 2025-11-25, `Mcp-Session-Id` header) with camera/media permissions,
  multimodal input and streaming event channels.
- `Dockerfile` (multi-stage, `python:3.11-slim`) + `docker-compose.yml` (uvicorn, healthcheck,
  environment-driven AWS config). `.dockerignore` keeps the image lean.
- `.local/scripts/run_demo.py` boots the real server, replays fall/smoke/pet ambient events and
  prints the telemetry report — the live QFP demonstration.

## 13. Roadmap

- [x] Phase 1 — Pure domain core, ports, use cases, adapters, unit tests.
- [x] Phase 2 — Multimodal tools, dynamic registry, Bedrock Converse.
- [x] Phase 3 — Persistent sessions, SSE, simulator, production entry.
- [x] Phase 4 — Ambient awareness, Quota Fallback Protocol, master docs.
- [x] Phase 5 — Alexa+ skill manifest, observability, Docker packaging, demo runner.
- [x] Phase 6 — EchoMind MCP Control Center: interactive web dashboard (SSE tools log, live metrics, QFP badge).
- [x] Phase 7 — Live Vivotek IP camera: real-time snapshot feed, graceful fallback frame, AI detection overlay.
- [x] Phase 8 — Autonomous ambient watchdog: background prediction engine (sensors + frame motion), proactive hot-word alerts and Spanish text-to-speech on the dashboard.

## 14. Web Control Center

`/dashboard` (or `/`) serves the EchoMind MCP Control Center: a dark slate UI with neon cyan and
Amazon orange accents, pure HTML + Tailwind (CDN) + vanilla JS. It polls `/metrics` every 2 s and
consumes the `/dashboard/events` SSE stream (fed by the `EventHub` broadcast from
`FastAPIMCPServer._call_tool`) for the live tools log. The **QUOTA FALLBACK MODE ACTIVE (QFP)**
badge switches to orange warning state when `/metrics.provider.is_degraded` becomes true, which the
resilience layer sets on the first Bedrock quota/credential failure.

The **Dynamic Camera Viewer** (`cam-select`) offers four sources: CAM-01 (physical Vivotek FD8367
live feed), CAM-02 Living Room, CAM-03 Kitchen and CAM-04 Patio — the last three being agentic
simulations that cycle scenes and draw AI-predicted bounding boxes (PERSON / DOG / PACKAGE / FALL
DETECTED / SMOKE DETECTED). Selecting CAM-01 refreshes the live JPEG every **1.5 s** via
`refreshLiveSnapshot()` against `GET /api/cam/vivotek/snapshot?t=<timestamp>` (cache-busting); the
backend `httpx` client acts as an **asynchronous reverse proxy** so the browser never talks to the
camera directly (FD8367 MJPEG needs an ActiveX plugin and violates CORS). Critical labels raise an
orange **ALERT** (`ai-alert`); unreachable camera → clean synthetic test frame with `SIM FALLBACK`
badge.

The camera panel also renders the **AI Watchdog** readout — `AI Risk · Temp · Smoke · Gate · Motion`
— polling `GET /api/cam/vivotek/state` every 2 s. It consumes `/dashboard/events` not only for the
tools log but for `camera_alert` events broadcast by the watchdog over the **EventHub**: detection
boxes are drawn over the viewer and, for HIGH/CRITICAL risk, `speakAlexa()` announces the verdict
in **Spanish** (`window.speechSynthesis`, es-ES/es-MX voice, `cancel()` to avoid queue overlap),
using the server-generated `announcement` text ("¡Alerta crítica! Humo detectado…").

The right column includes the **Alexa Ecosystem Devices** catalogue with direct manufacturer links
(Echo Show 10 / Echo Hub `B08MQLD231`, Ring Indoor Cam / Outdoor `B0B6GH3M3B`, Blink Mini 2
`B0BGH83N2B`, Sonoff WiFi Smart Switch `B0786LH3A7`) and an "Añadir Nuevo Dispositivo MCP" button
that opens a modal explaining automatic device discovery over **JSON-RPC / MCP Streamable HTTP**
(`initialize` → handshake, `tools/list` → skills, `tools/call` → live invocation).

## 15. Live Vivotek camera integration (Phase 7)

`VivotekCameraAdapter` (`src/infrastructure/adapters/iot/vivotek_adapter.py`) is an async `httpx`
client for the FD8367 snapshot endpoint (`http://192.168.40.10/cgi-bin/viewer/video.jpg`, override
with `ECHOMIND_VIVOTEK_IP`). It caches the newest frame for `cache_ttl` seconds; unreachable,
timed-out or invalid responses produce a deterministic clean PNG test frame, so the pipeline stays
operational 24/7. Routes (mounted in `main.compose`):

- `GET /api/cam/vivotek/snapshot` — raw JPEG/PNG with `X-Source`, `X-Captured-At` and `no-store`;
  `?format=base64` returns JSON.
- `GET /api/cam/vivotek/detections` — JSON `{source, live, detections}` fed by the ambient resolver.
- `GET /api/cam/vivotek/state` — latest watchdog vision snapshot `{risk, temperature_c,
  smoke_density, gate_open, door_open, pet_proximity, motion_score, detections, announcement}`.

`build_ambient_resolver(llm_service, camera=None)` auto-attaches the latest **live** frame to the
Bedrock Converse request when no explicit media attachment is given, then `extract_detections`
derives AI-predicted labels (FALL DETECTED / SMOKE / FIRE / PERSON / PET / PACKAGE / LAPTOP /
INTRUDER) from the report text and records them on the camera adapter. The dashboard's CAM-01
selector refreshes the live image every **1.5 s**, overlays the predicted bounding boxes and
raises an orange ALERT for critical labels; when the camera fails it displays the simulated scenes
via `SIM FALLBACK`. The local rule engine (QFP) and `extract_detections` match safety keywords as
whole words, so tokens embedded in labels (e.g. `cat` inside `location`) never trigger false
detections.

## 16. Autonomous Ambient Watchdog (Phase 8)

**Problem solved.** Before Phase 8 the dashboard only reacted: snapshots refreshed but nothing
predicted unless a tool was explicitly invoked with text. There was no continuous cognition.

**Solution.** `AmbientWatchService` (`src/infrastructure/services/ambient_watch_service.py`) is an
autonomous background loop started/stopped with the ASGI application lifecycle
(`_attach_watchdog_lifespan` in `src/main.py`). Every 3 s it:

1. fetches the latest camera frame through `VivotekCameraAdapter.get_frame()`;
2. measures **real motion** between consecutive live frames with `frame_delta_ratio()` — the
   fraction of sampled bytes that differ between two JPEG payloads (static scenes are
   near-identical; changing scenes produce a high ratio; a deterministic fallback PNG yields 0);
3. reads home telemetry from `SensorBus` (`src/infrastructure/services/sensor_bus.py`), a
   deterministic, self-driven sensor network evolving over a repeating **120-second scenario
   cycle**: gate/door reed switches, smoke density, temperature and pet-collar proximity/movement;
4. runs `predict_ambient_state()` — an explainable, deterministic prediction engine combining
   thresholds and trends: smoke `≥0.20/0.45/0.75` → MEDIUM/HIGH/**CRITICAL** (FIRE at the top),
   temperature `≥26 °C` with a rising slope → MEDIUM/HIGH **TEMP_RISING**, gate open + pet at the
   exit → HIGH **PET_ESCAPING**, open gate/door → **GATE_OPEN**/**DOOR_OPEN**, and CV motion →
   **MOTION**;
5. records the predictions on the camera adapter (fresh `/detections`), caches them in
   `last_state` (served by `/api/cam/vivotek/state`) and publishes a **`camera_alert`** event to
   the `EventHub` (→ `/dashboard/events`) only when the risk is HIGH/CRITICAL, the fingerprint
   changes **and** the verdict is driven by a visual access trigger (`MOTION`, `GATE_OPEN`,
   `PET_ESCAPING`) — smoke/temperature readings never fire alerts on their own, keeping the
   transmission clean for demos — with a Spanish `announcement` such as *"¡Alerta crítica!
   Detecciones: humo, fuego. Llama a emergencias…"*.

The `analyze_ambient_stream` resolver (`tool_resolvers.py`) also broadcasts `camera_alert` events
(risk, location, detections) when it runs, so manual/agentic analysis and the autonomous watchdog
share the same alerting channel.

## 17. Alineación con el Hackathon Amazon 2026

- **Pista principal — Alexa+**: servidor **MCP Streamable HTTP** (spec `2025-11-25`,
  `Mcp-Session-Id`, SSE remoto), `alexa_skill/skill.json` (**Agent Skills**) y el **EchoMind MCP
  Control Center** como superficie operativa.
- **Minidesafío AWS Builder**: visión multimodal con la **Amazon Bedrock Converse API**
  (adjuntos image/video/audio/document en `BedrockLLMAdapter`) + **Resiliencia Graceful
  Fallback**, el **Quota Fallback Protocol (QFP)**: `ResilientLLMAdapter` failover determinista a
  `RuleBasedLLMAdapter` sin romper la sesión MCP (verificado en vivo sin credenciales AWS).
- **Minidesafío Código Abierto**: repositorio público, arquitectura hexagonal/DDD con capas
  puras, 100% tipado, suite **102/102 en verde** ejecutable offline (`pytest -q`), `flake8` en 0,
  `black` limpio y documentación completa (`README.md` + `MASTERDOC.md`).

## 18. Estado actual — Fases 7-8 completadas

**Camera.** Real integration of a **Vivotek FD8367**: `http.cgi-bin/viewer/video.jpg` snapshots
verified live (~**62 KB / JPEG frame** at `192.168.40.10`), night vision via built-in **IR LEDs**
(0.01 lx) without extra illumination, endpoint answered `200` even without credentials. The
`httpx` backend proxies each frame to the dashboard every 1.5 s; failures degrade to a
deterministic clean PNG test frame (24/7 availability).

**Resilience.** The **Quota Fallback Protocol (QFP)** keeps the MCP server fully operational when
AWS Bedrock is throttled/credential-less/unreachable: `ResilientLLMAdapter` fails over
deterministically to `RuleBasedLLMAdapter` (same `LLMServicePort` contract), verified end-to-end
with zero AWS credentials (CRITICAL ambient alert answered locally).

**Alexa device catalogue.** Dashboard panel with direct manufacturer links — Echo Show 10 / Echo
Hub (`B08MQLD231`), Ring Indoor Cam / Outdoor (`B0B6GH3M3B`), Blink Mini 2 (`B0BGH83N2B`), Sonoff
WiFi Smart Switch (`B0786LH3A7`) — and a JSON-RPC MCP discovery modal showing how each device
registers `initialize` / `tools/list` / `tools/call` over Streamable HTTP.

**Quality gates.** **102/102 tests green** (including the watchdog/sensor-bus suite), `flake8
src tests` → 0 violations, `black --check src tests --line-length 88` → clean.