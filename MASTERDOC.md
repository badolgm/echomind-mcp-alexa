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

- 74 tests across `tests/unit` (domain, use cases, adapters, fallback, ambient) and
  `tests/integration` (SSE session lifecycle, composition smoke, telemetry, skill manifest).
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