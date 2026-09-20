# Echosystem — Active Ambient Awareness for Alexa+ (MCP × AWS Bedrock)

**Echosystem** is a multimodal, agentic ecosystem purpose-built for **Alexa+**. It bridges the
**Model Context Protocol (MCP)** — over the HTTP **Streamable** transport — with **Amazon
Bedrock** foundation models, giving Alexa+ skills an extensible, tool-using reasoning core that
**cares proactively** about the people and pets in the room.

Built for the **Amazon Hackathon (Build, Ship, Shape 2026)** under strict **Hexagonal
Architecture (Ports & Adapters)** and **Domain-Driven Design (DDD)**: a pure domain core, decoupled
ports, swappable adapters, and 100% test coverage that runs offline.

---

## The disruptive value: Active Ambient Awareness

Instead of waiting for a voice command, Echosystem pushes **proactive safety intelligence** into
the home conversation:

- **Elder care** — falls, immobility and "person on the floor" detection with CRITICAL severity.
- **Pet wellbeing** — unattended or distressed pets are flagged and followed up.
- **Anomaly & security** — smoke/fire indicators, intrusions and unknown persons.
- **Multimodal grounding** — images, video, audio and PDF documents are fed straight to the model.
- **Control Center** — an interactive dark-mode web dashboard (`/dashboard`) with live latency
  sparklines, simulated camera feeds with detection boxes, the MCP pipeline viewer, a streaming
  tools log (SSE) and a live **Quota Fallback Mode** badge.

Every snapshot is graded by a **deterministic safety gate** and by a reasoning model, so critical
signals are never dropped — even when the cloud is not reachable.

## The resilience promise: 24/7 via the Quota Fallback Protocol

Amazon Bedrock is the primary LLM provider. When AWS **throttles**, rejects **credentials** or
**exhausts model quota**, the built-in `ResilientLLMAdapter` fails over transparently to a
deterministic local rule engine that implements the same `LLMServicePort` contract. The MCP
session with Alexa+ never breaks. Verified live: with zero AWS credentials on the host, the server
still answered an ambient CRITICAL alert end-to-end.

---

## Architecture

All business rules live in an agnostic core; frameworks, SDKs and IO live at the edges and are
injected through ports:

```
┌────────────────────────────────────────────────────────────────┐
│                       ADAPTERS (edges)                         │
│  FastAPI MCP Streamable HTTP  ·  AWS Bedrock  ·  Local rule    │
│  engine (fallback)             ·  Tool resolvers               │
└───────────────▲───────────────────────────▲────────────────────┘
                │         implements        │
   ┌────────────┴──────────┐   ┌────────────┴─────────────┐
   │  MCPServerPort        │   │  LLMServicePort          │
   │  (output / domain)    │   │  (output / domain)       │
   │  ResilientLLMAdapter  │   │                          │
   └────────────▲──────────┘   └────────────▲─────────────┘
                │            depends on      │
   ┌────────────┴────────────────────────────┴─────────────┐
   │              APPLICATION (use cases)                  │
   │      ProcessIntentUseCase / ProcessMultimodalIntent   │
   └────────────────────────▲─────────────────────────────┘
                            │
   ┌────────────────────────┴─────────────────────────────┐
   │        DOMAIN (pure core, zero dependencies)          │
   │  UserIntent · AgentTool catalog · Value Objects · Ports│
   └───────────────────────────────────────────────────────┘
```

### Dependency rule

- `src/domain/` — **pure core.** No FastAPI, no boto3, no MCP SDK, no IO. Only dataclasses,
  `abc` and `typing`.
- `src/application/` — orchestrates use cases through domain **ports**; depends only on the
  domain and its own DTOs.
- `src/infrastructure/` — concrete **adapters** (Bedrock via boto3, Streamable HTTP via FastAPI,
  local fallback engine, tool resolvers). The only layer that touches frameworks and SDKs.
- `tests/` — unit and integration suites run against mocked ports **without network or AWS**.

## Multimodal support

`LLMRequest.attachments` carries images, video, audio and documents (PDF, DOCX, XLSX, CSV, TXT,
MD). The Bedrock adapter translates them into Converse content blocks; every tool in the catalog
declares its supported modalities. No media type leaks into the domain.

---

## Project layout

```
.
├── .local/                        # scratch scripts (gitignored)
├── src/
│   ├── domain/
│   │   ├── models/                # intent.py · tools.py (agentic catalog)
│   │   └── ports/output/          # llm_port.py · mcp_port.py (contracts)
│   ├── application/
│   │   ├── dtos/intent_dto.py
│   │   └── use_cases/             # process_intent.py · process_multimodal_intent.py
│   ├── infrastructure/adapters/
│   │   ├── aws/                   # bedrock_adapter.py · fallback_llm_adapter.py
│   │   ├── mcp/                   # fastapi_mcp_adapter.py · session_manager.py
│   │   │                          # tool_resolvers.py
│   │   └── config/                # telemetry.py (p50/p95/p99 metrics)
│   └── main.py                    # composition root (IoC) + uvicorn entry
├── alexa_skill/skill.json         # Alexa+ Agent Skill manifest (MCP streamable)
├── Dockerfile / docker-compose.yml
└── tests/
    ├── unit/                      # domain, use cases, adapters, fallback
    └── integration/               # SSE session lifecycle, composition smoke
```

## Agentic tool catalog

| Tool | Category | What it does |
| ---- | -------- | ------------ |
| `analyze_image_context` | Analysis | Multimodal image/video understanding |
| `summarize_document` | Knowledge | Faithful document summarisation |
| `schedule_reminder` | Productivity | Time-based reminders |
| `analyze_ambient_stream` | **Safety** | Continuous home monitoring: falls, pets, smoke/fire, intrusions |

---

## Getting started

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the test suite + quality gates (no AWS required)
pytest -q
flake8 src tests
black --check src tests --line-length 88

# 4. Start the MCP Streamable HTTP server
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Open the **EchoMind MCP Control Center** at [http://localhost:8000](http://localhost:8000/) — the
interactive dark-mode dashboard (agent metrics with sparklines, live **Vivotek IP camera** feed with
AI-predicted detection boxes, simulated multimodal cameras, MCP pipeline viewer, live tools log via
SSE and Bedrock/QFP utilization gauges). If the camera is unreachable the server serves a clean
synthetic frame and the dashboard falls back to the simulated view.

> AWS credentials come from the standard chain (`~/.aws/credentials`, env vars, IAM role).
> **Never commit credentials.** Without any credentials, the Quota Fallback Protocol keeps the
> server fully operational using the local rule engine.

### Drive it with the Alexa+ simulator

`{ .local/scripts/alexa_mcp_simulator.py }` is an interactive MCP client that emulates Alexa+:
session negotiation, SSE listener and JSON-RPC tool calls, including base64 multimodal
attachments.

```powershell
# One-shot ambient analysis
python .local/scripts/alexa_mcp_simulator.py --server http://localhost:8000 `
    --tool analyze_ambient_stream `
    --arguments '{"location":"kitchen","observation":"smoke coming from the oven"}'

# One-shot with a media attachment
python .local/scripts/alexa_mcp_simulator.py --server http://localhost:8000 `
    --tool analyze_image_context --attachment photo.jpg --prompt "Describe this"

# Interactive REPL (list / call / session / quit)
python .local/scripts/alexa_mcp_simulator.py --server http://localhost:8000 --interactive
```

### One-command demo with live metrics

`run_demo.py` boots the server, replays ambient events (fall, smoke, lonely pet) through
`analyze_ambient_stream` and prints the telemetry report:

```powershell
python .local/scripts/run_demo.py
```

It prints the MCP session handshake, the CRITICAL/MEDIUM verdicts and the `/metrics` report.

### Observability

`GET /metrics` exposes a dependency-free snapshot: uptime, per-tool call counts, quota-fallback
activations and request latency percentiles (p50/p95/p99):

```powershell
curl http://localhost:8000/metrics
```

```json
{
  "uptime_seconds": 12.53,
  "tool_calls": { "analyze_ambient_stream": 3 },
  "total_tool_calls": 3,
  "fallbacks_activated": 1,
  "latency_ms": {
    "tools/call": { "count": 3, "mean_ms": 0.96, "p50_ms": 0.15, "p95_ms": 2.62, "p99_ms": 2.62 }
  }
}
```

### Deploy with Docker

```powershell
docker compose up --build -d
curl http://localhost:8000/health
```

The image is a multi-stage build on `python:3.11-slim` with a uvicorn healthcheck. In production
inject AWS credentials via an IAM role (ECS/Fargate) or environment variables; the container runs
the full Quota Fallback Protocol if they are absent.

### Configuration (environment variables)

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `ECHOMIND_BEDROCK_MODEL_ID` | `amazon.nova-micro-v1:0` | Primary Bedrock model |
| `ECHOMIND_BEDROCK_REGION` | `us-east-1` | AWS region |
| `ECHOMIND_FALLBACK_COOLDOWN_SECONDS` | `300` | Circuit-breaker cooldown before probing Bedrock again |
| `ECHOMIND_SESSION_IDLE_TIMEOUT` | `300` | MCP session idle expiry (seconds) |
| `ECHOMIND_SSE_KEEPALIVE_SECONDS` | `15` | SSE heartbeat interval |
| `ECHOMIND_HOST` / `ECHOMIND_PORT` | `0.0.0.0` / `8000` | uvicorn bind |
| `ECHOMIND_VIVOTEK_IP` | `192.168.40.10` | Vivotek FD8367 camera host for live ambient frames |

---

## Measured latency

In-process round trips over the Streamable HTTP transport (this laptop, ASGI):

| Operation | Mean | p50 | p95 | Throughput |
| --------- | ---- | --- | --- | ---------- |
| `tools/list` | 0.73 ms | 0.69 ms | 0.94 ms | ≈ 1 360 req/s |
| `tools/call` | 0.77 ms | 0.69 ms | 1.19 ms | ≈ 1 300 req/s |

## Quality gates

```powershell
pytest -q          # 79 tests
flake8 src tests   # zero violations
black --check src tests --line-length 88
```

---

## Roadmap

- [x] **Phase 1** — Pure domain core, ports, use case, adapters, unit tests.
- [x] **Phase 2** — Multimodal tools, dynamic MCP tool registry, Bedrock Converse blocks.
- [x] **Phase 3** — Persistent sessions, SSE streaming, simulator, production entry point.
- [x] **Phase 4** — Active Ambient Awareness tool, Quota Fallback Protocol, master docs.
- [x] **Phase 5** — Alexa+ skill manifest, observability (`/metrics`), Docker packaging, demo runner.
- [x] **Phase 6** — EchoMind MCP Control Center: interactive web dashboard (SSE tools log, live metrics, QFP badge).
- [x] **Phase 7** — Live Vivotek IP camera integration: real-time snapshot feed, graceful fallback frame, AI detection overlay on the dashboard.

---

## License

MIT © 2026 Badolgm. See [LICENSE](LICENSE).