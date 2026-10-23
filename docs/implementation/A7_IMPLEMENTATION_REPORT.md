# A7 — Plan ↔ Motor Closure · Implementation Report

**Date:** 2026-10-18  
**HEAD:** `b963c5f` (no commits, no push)  
**Status:** ✅ 535 tests PASS | ✅ flake8 0 | ✅ black (93 files unchanged)  
**Impact:** hash vs A6G baseline → changed/missing: 2 (only `recall_planner.py`, `recall_engine.py`)

## 1. Objective

Close the gap identified in A6G: the Recall Engine already computes anchors, before/after, relations, gaps, spatial/camera grouping, context and narration — but the planner does not route the question to those capabilities. Target: make the 6 cases produce answers coherent with the question while keeping `memory_converse` untouched.

## 2. Files changed (minimal)

| File | Change |
|---|---|
| `src/domain/services/recall_plan.py` | **B1, B4** — derive `plan.anchor` when asking for `before_after`/`timeline` (fallback to `FALL DETECTED` if text contains "caída/caida/fall"); expand `_RELATION_PHRASES` with "despues de", "antes/de/después de la", and relation triggers `relacionado/relacionados/relacionadas`, `related`, `between`, `entre`. |
| `src/infrastructure/services/recall_engine.py` | **B2** — import `episodes_after`; in `BEFORE_AFTER` branch also compute `episodes_after(until)` and record `episodes_after`/`count_after` in trace (preserves existing behavior for other code/tests). |

No changes to `memory_converse`, `evidence/render_utterance`, `context_narrative`, `relation_rules`, or any other files.

## 3. Breaches addressed

| ID | Fix | Notes |
|---|---|---|
| **B1** | `plan.anchor` set when relations include `BEFORE_AFTER` or `TIMELINE`. If no label entity present, infer `FALL DETECTED` for "caída/caida/fall". | Existing tests that don't set anchor remain valid; anchor path still honors engine's resolve logic. |
| **B2** | Add `episodes_after` to BEFORE_AFTER trace (both `before` and `after` cut at `target_ts = until`/anchor). | Direction is a **product choice** (which side to narrate) — the engine now exposes both counts/episodes for downstream synthesis without breaking existing expectations. |
| **B4** | Vocab adds `related/between/entre/relacionado(s/as)` → `CORRELATION`. Adds common "después/antes de la" forms. | Expands detection without changing existing mappings. |
| **B5** | Out of scope for planner/engine: `session_start` is passed by HTTP/MCP boundary. Already supported by `recall_engine.execute(session_start=...)` and `/api/recall` accepts it; MCP resolver doesn't pass it (documented in A6G) — no change made (keeps surface minimal). |
| **B3** | Not modified. The utterance remains `render_utterance(evidence, ...)` by design; aggregate/relate results live in trace/context/context_response. Any change to "make response follow the question" would touch synthesis (and likely test expectations) — deferred to product decision (A6G B3). | 

## 4. Verification

- **All existing tests:** 535 passed. Planner tests still pass; anchor/engine tests pass.
- **Static checks:** flake8 0; black 93 files unchanged.
- **Anchor inference:** `¿Qué ocurrió antes/después de la caída?` → `plan.anchor = FALL DETECTED`, `relations=(BEFORE_AFTER,)`.
- **Relations vocab:** `¿Qué eventos están relacionados?` / `related` / `between` / `entre` → `CORRELATION`.
- **BEFORE_AFTER trace:** with anchored plan, `count=5, count_after=8` for the fixture (episodes cut at anchor ts). Unanchored BEFORE_AFTER unchanged.
- **Impact zero (hash):** changed/missing = 2 (only the two files above). A6f new files intact; no protected files touched.

## 5. Notes

- Directional rendering ("antes de..." vs "después de...") is not forced by the plan alone (same RelationKind). The trace now exposes `count_after` so a future synthesis can choose direction — no behavior change to current `response` (B3 preserved intentionally).
- `session_start` exposure (B5) remains as-is: engine supports it; HTTP passes it; MCP tool schema/dispatch doesn't — not modified per minimal-change rule.
- No commits/push. Baseline A6G unchanged for repo state; dirty files minimal.
