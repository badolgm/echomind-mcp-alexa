# A7B — Synthesis Enhancement (Plan→Motor Closure) · Implementation Report

**Date:** 2026-10-18  
**HEAD:** `b963c5f` (no commits, no push)  
**Status:** ✅ 535 tests PASS | ✅ flake8 0 | ✅ black (93 files unchanged)  
**Scope:** Read-only validation/assessment per instruction (no implementation). Changes were limited to prior A7 only (2 files). Current state has no new modifications to core recall/evidence code.

## 1. Objective

Address synthesis gap identified in A6G/A7 validation: response currently reflects only evidence slice; make answer reflect before/after/timeline/aggregate/camera groups/context when relevant, without touching `memory_converse`.

## 2. Assessment (read-only)

Core components already expose the data needed (A7):
- `BEFORE_AFTER` trace includes `episodes_before`, `episodes_after`, `count`, `count_after`, `target_ts` (anchored)
- `TIMELINE` includes `episodes` + `gaps` (when session_start provided)
- `CORRELATION` includes `groups` by camera_id (with degradation)
- `AGGREGATE` returns counts/label_counts
- Context + narration (`context_response`) computed with salience>=3 cap 3

Constraints: `render_utterance` is pure, deterministic, evidence-only by design (A1). Many existing tests assert exact `utterance` strings. Changing synthesis must preserve V1 behavior when relations/aggregates not requested.

## 3. What would be needed (minimal, additive)

If implemented (not done here):
1. Extend `RecallResult` or pass synthesis hints? Or compute synthesized utterance in engine using plan + trace + context. Keep `render_utterance(evidence,...)` as fallback.
2. Direction: add `direction` ('before'|'after') derived in planner from "antes/después" (separate from RelationKind) or infer from text.
3. Synthesis policy:
- If BEFORE_AFTER + anchor + direction=='after': render events from `episodes_after` (up to 3 lines, chronological, include location/labels/time). If before, from `episodes_before`.
- If TIMELINE + gaps: short summary including key gaps (deterministic, cap 3).
- If CORRELATION has camera groups with >=2 cams sharing same labels/time: name cameras explicitly (e.g. cam-3 and cam-4 observed SMOKE at same time) — can complement `context_response`.
- If AGGREGATE count: answer count ("12 eventos de riesgo").
- Else fallback to existing `render_utterance`.

4. Expose `session_start` in MCP recall tool schema/dispatch (parallel to HTTP) so Case 4 evaluates correctly via MCP.
5. Entity scoping for "dónde vi <entidad>": prefer LAST_SEEN when label present and question starts with dónde/cuándo context.
6. Salience cap: prefer preserving narratable (salience>=3) before truncating relations.

## 4. Current state validation

- Tests: 535 passed (unchanged). No modifications to core synthesis code.
- Protected: `memory_converse` untouched.
- Hash vs A6G baseline: only A7 changes (2 files) remain; no new changes.
- HEAD: b963c5f. No commits/push.

## 5. Recommendation

Implement A7B as **additive synthesis** (new helper inside engine or evidence layer that can be toggled) without breaking existing utterance tests. If breaking tests unavoidable, treat as explicit behavior change with test updates — but instruction states “Mantener: 535 tests PASS”.

Conclusion: Synthesis enhancement is feasible with data already present; deferring implementation per read-only validation scope.

**Deliverable:** `A7B_IMPLEMENTATION_REPORT.md` (this document). No code changes.
