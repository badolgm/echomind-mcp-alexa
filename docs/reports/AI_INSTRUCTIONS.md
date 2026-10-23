# AI_INSTRUCTIONS — Operating guide for AI assistants in this repository

This file is the single source of truth for any AI assistant working on
`echomind-mcp-alexa`. Read it before touching code. Non-compliance is a defect.

## 0. Mission

`echomind-mcp-alexa` is a multimodal agentic ecosystem for Alexa+ built on the Model Context
Protocol (MCP, HTTP Streamable transport) and AWS Bedrock, for the Amazon Hackathon 2026. The
architecture is **Hexagonal (Ports & Adapters)** with **Domain-Driven Design** and **strict
typing**.

## 1. Layering rules (non-negotiable)

- `src/domain/` is the **pure core**. No FastAPI, no boto3, no MCP SDK, no HTTP, no IO. Only the
  standard library (`dataclasses`, `abc`, `enum`, `typing`). Entities and value objects are
  immutable (`@dataclass(frozen=True, slots=True)`) and never import from `src/infrastructure/`.
- `src/application/` contains **use cases** and **DTOs**. They depend only on the domain and their
  own DTOs. No framework/SDK imports.
- `src/infrastructure/` contains **adapters** only: transports (MCP/FastAPI), providers (AWS
  Bedrock, local fallback engine) and resolvers. This is the only layer allowed to touch
  frameworks and SDKs.
- Dependency arrows always point toward the domain. Never `import src.infrastructure` from
  `src/domain` or `src/application`.
- Adding a capability follows the pattern: domain model → port method → use case →
  adapter → resolver → registry → tests.

## 2. Code conventions

- **Strict typing**: annotate every function signature and attribute. Use `str | None`, tuples,
  `Mapping`, etc. Enable and respect mypy-style discipline even if mypy is not wired in CI.
- **Single Responsibility**: one class/function = one reason to change. Keep helpers private
  (underscore prefix) unless another module legitimately reuses them.
- **Immutability at the core**: domain models are frozen dataclasses; validation lives in
  `__post_init__`.
- **Do not add comments** unless the user asks for them or the comment is necessary to convey a
  non-obvious contract invariant.
- Match the existing style (docstrings are used at module and public-API level; black line
  length 88).

## 3. Quality gates — mandatory before declaring a phase done

Run all three; all must pass with **zero** violations:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m flake8 src tests
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```

- Tests must run **offline**: ports are mocked, no network, no AWS.
- Configuration: `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`), `setup.cfg`
  (`max-line-length = 88`, `extend-ignore = E203,W503`).
- If a change forces a long line, split strings/expressions so black (which does not split
  strings) and flake8 both stay green.

## 4. Git rules

- **Never** `git commit` or `git push` autonomously. Only when the user explicitly asks.
- Before any requested commit: review `git status`, `git diff`, `git log --oneline -10`; stage
  only intended files; never commit secrets or `.local/` scratch.
- Do not force-push, amend, or alter git config.

## 5. Scratch space

- `.local/` is the **only** place for scratch scripts, experiments and throwaway notes
  (gitignored). Simulator and ad-hoc tooling belong in `.local/scripts/`.
- Clean up temporary files you create outside the workspace (e.g. under the OS temp dir used by
  the assistant).

## 6. Testing responsibilities

- Add a unit test for every new domain model, use case, port implementation and resolver.
- Add integration tests for anything touching the MCP session/SSE lifecycle.
- Feed the model double via a thin `LLMServicePort` fake; never hit AWS in tests.
- New tools in the catalog (`AGENTIC_TOOL_CATALOG`) need: catalog test, resolver test, and a
  registry-exposure test.

## 7. Reporting

- Report phase results factually: test counts, gate status, files touched, live-verification
  evidence (e.g. simulator/uvicorn runs).
- Do not over-summarize; include the verification steps actually executed.

## 8. Environment reference

- Windows PowerShell 5.1; worktree root is the repo root.
- Python 3.11 virtualenv at `.venv\` (use `.venv\Scripts\python.exe` explicitly).
- Run the server with `python -m uvicorn src.main:app`; use the simulator from
  `.local/scripts/alexa_mcp_simulator.py`.