# Echosystem - Multimodal Agentic Ecosystem for Alexa+ (MCP x AWS Bedrock)

**Echosystem** is an open-source, multimodal agentic ecosystem designed for **Alexa+**. It
bridges the **Model Context Protocol (MCP)** — using the HTTP **Streamable** transport — with
**Amazon Bedrock** foundation models to give Alexa+ skills an extensible, tool-using reasoning
core.

Built for the **Amazon Hackathon (Build, Ship, Shape 2026)**, this repository is the Phase 1
skeleton: a strictly layered, testable core following **Hexagonal Architecture (Ports &
Adapters)** and **Domain-Driven Design (DDD)**.

---

## Architecture

The system follows a strict **Hexagonal / Ports & Adapters** layout. All business rules live in
an agnostic core; frameworks, SDKs, and IO live at the edges and are *injected* via ports.

```
┌──────────────────────────────────────────────────────────────┐
│                        ADAPTERS (edges)                      │
│  infra: FastAPI MCP Streamable HTTP  ·  AWS Bedrock (boto3)  │
└───────────────▲──────────────────────────▲───────────────────┘
                │        implements        │
   ┌────────────┴──────────┐   ┌───────────┴────────────┐
   │  MCPServerPort        │   │  LLMServicePort        │
   │  (output / domain)    │   │  (output / domain)      │
   └────────────▲──────────┘   └───────────▲────────────┘
                │      depends on           │
   ┌────────────┴───────────────────────────┴────────────┐
   │         APPLICATION (use cases)                     │
   │         ProcessIntentUseCase                        │
   └───────────────────────▲────────────────────────────┘
                           │
   ┌───────────────────────┴────────────────────────────┐
   │         DOMAIN (pure core, zero dependencies)      │
   │         UserIntent  ·  Value Objects  ·  Ports      │
   └────────────────────────────────────────────────────┘
```

### Dependency rule

- `src/domain/` — **pure core**. No FastAPI, no boto3, no MCP SDK, no IO. Only dataclasses,
  `abc`, and `typing`.
- `src/application/` — orchestrates use cases through domain **ports**; depends only on the
  domain and its own DTOs.
- `src/infrastructure/` — concrete **adapters** (Bedrock via `boto3`, MCP Streamable HTTP via
  FastAPI). This is the only layer that touches frameworks and SDKs.
- `tests/` — the use case is unit-tested against **mocked ports** (no network, no AWS).

This inverses dependency: the domain never imports the infrastructure, and new adapters (e.g. a
local Ollama model, a WebSocket MCP server) can be swapped in without touching business logic.

---

## Project layout

```
.
├── .local/                     # local scratch space (scripts, notes, backups) — gitignored
├── requirements.txt
├── src/
│   ├── domain/
│   │   ├── models/intent.py            # UserIntent aggregate + Value Objects
│   │   └── ports/output/
│   │       ├── llm_port.py             # LLMServicePort (ABC) — reasoning contract
│   │       └── mcp_port.py             # MCPServerPort (ABC) — tools/context contract
│   ├── application/
│   │   ├── dtos/intent_dto.py          # ProcessIntentRequest / ProcessIntentResult
│   │   └── use_cases/process_intent.py # ProcessIntentUseCase orchestration
│   └── infrastructure/
│       ├── adapters/aws/bedrock_adapter.py       # boto3 → LLMServicePort
│       └── adapters/mcp/fastapi_mcp_adapter.py   # FastAPI → MCPServerPort
└── tests/
    └── unit/test_process_intent.py     # mocked-port unit tests
```

---

## The MCP standard and Alexa+

Alexa+ will consume this ecosystem through the **Model Context Protocol**, an open standard
that lets an LLM application expose *tools* and *resources* to a host. This project targets the
**HTTP Streamable transport** for MCP: a long-lived streaming connection over HTTP that keeps the
server stateless, works with standard load balancers, and enables incremental tool/context
delivery.

The FastAPI adapter exposes the MCP lifecycle (initialize, tools/list, tools/call,
resources/list, etc.) over that transport, while the domain `ProcessIntentUseCase` decides which
tool to invoke based on the user's intent.

## Amazon Bedrock reasoning

Natural-language intents are resolved by a foundation model running on **Amazon Bedrock**
(Claude, Nova, etc.). The `bedrock_adapter` implements the domain `LLMServicePort` so the use
case can request *either* a structured intent classification *or* a free-form reasoning response
without knowing which AWS service backs it. The domain contract keeps `boto3` completely out of
the core.

## Getting started

```powershell
# 1. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the unit tests (mocked ports, no AWS required)
pytest -v

# 4. (Optional) run the MCP Streamable HTTP server
uvicorn src.infrastructure.adapters.mcp.fastapi_mcp_adapter:app --reload
```

> AWS credentials are read from the standard credential chain (`~/.aws/credentials` or
> environment variables). Never commit credentials; see `.gitignore`.

## Roadmap (Phase 1 → N)

- [x] Phase 1 — Pure domain core, ports, use case, initial adapters, unit tests.
- [ ] Phase 2 — Full MCP Streamable HTTP lifecycle + tool definitions.
- [ ] Phase 3 — Bedrock intent classification & grounding with multi-modal inputs.
- [ ] Phase 4 — Alexa+ skill integration, streaming UX, observability.

---

## License

MIT © 2026 Badolgm. See [LICENSE](LICENSE).