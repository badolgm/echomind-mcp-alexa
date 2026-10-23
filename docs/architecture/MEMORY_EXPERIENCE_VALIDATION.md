# MEMORY EXPERIENCE VALIDATION

**Date:** 2026-10-18
**Branch/HEAD:** b963c5f (no commits, no push)
**Test suite:** 535 passed
**Mode:** Read-only validation using A1–A7 as-is

## 1. Question central

**Does EchoMind already behave like a conversational memory, or are there still functional gaps?**

**Short answer:** It behaves as an **auditable memory reasoning system** (retrieves, groups, builds timeline/gaps, derives relations, produces context/narration) — but it **does not yet behave as a conversational responder**. The planner+engine now expose more structure (anchor inferred for before/after/timeline, BEFORE_AFTER includes `count_after`, vocab expanded) but the **spoken answer is still synthesized only from retrieved evidence via `render_utterance`**, not from aggregates/relations/gaps/anchors. So conversational behavior remains partial.

## 2. Validation setup (exactly as exists today)

Using the same fixture as A6G (12 records / 12 episodes, 4 cameras, realistic timings, FALL at ~1759985600, session_start = NOW-7h):

```python
NOW = 1760000000.0
HOUSEHOLD includes: m-01 GATE_OPEN patio/cam-1 (NOW-6h), m-02 PERSON patio/cam-1 (NOW-5h50m), m-03 PET jardin/cam-2 (NOW-5h), m-04 MOTION patio/cam-1 (NOW-4h3m), m-05 FALL DETECTED+PERSON patio/cam-1 (NOW-4h), m-06 PERSON_ELDERLY salon/cam-3 (NOW-3h57m30s), m-07 PERSON cocina/cam-4 (NOW-3h45m), m-08 SMOKE cocina/cam-4 (NOW-2h), m-09 SMOKE salon/cam-3 (NOW-2h), m-10 MOTION salon/cam-3 (NOW-1h), m-11 PET patio/cam-1 (NOW-30m), m-12 PET patio/cam-1 (NOW-10m)
SESSION_START = NOW - 7*3600
```

Paths exercised (read-only):
- `understand()` → `RecallPlan` (anchor inference for BEFORE_AFTER/TIMELINE, expanded relation vocab)
- `recall()` (MCP path, session_start=None) and `RecallEngine.execute()` (can accept session_start)
- Timeline (`build_episodes`, `episodes_before`, `episodes_after`, `timeline_gaps`)
- Spatial (`resolve_zone`, `resolve_camera`, grouping)
- Relations (`relate_episodes`, derived graph, cap 64)
- Context (`build_context`, salience ladder) + Narration (`render_context`, cap 3)

Note: `render_utterance` (V1) returns up to 3 lines from evidence ordered chronologically (oldest→newest in effect for that slice). `context_response` exists in payload/trace but **not surfaced by MCP `_render`** (as before).

## 3. Case by case

### Case 1: "¿Dónde vi mi mascota?"
- **understand()** (A7): intent likely SEARCH/LAST_SEEN? Classifier: "dónde vi mi mascota" doesn’t match LAST_SEEN_RE; entities.text only → ops [search, range] (no label). relations may include SPATIAL if detected. **plan.anchor=None**.
- **retrieval**: search/range over window → evidence includes PET events (m-03 jardin hace 5h, m-11 patio hace 30m, m-12 patio hace 10m).
- **relations/context**: derived graph exists; narratable includes correlation_overlapping in general but with cap 64 some may be cut (A6G: temporal_transition cut). Spatial grouping in trace.
- **real utterance (MCP):** `GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas.` (top 3 oldest evidence lines, not filtered to PET). 
- **context_response**: may include `"SMOKE en el mismo instante."` if overlapping present (m-08/m-09) and not cut from narratable set.
- **expected conversational:** "La última vez que vi la mascota fue en el patio, hace 10 minutos." (or list last sightings)
- **exact gap:** answer not entity-scoped (no PET filter in utterance). Planner doesn’t force `last_seen(PET)` from "dónde vi mi mascota" (label extraction only in LAST_SEEN branch). **Fixable by planner routing** (separate from engine).

**Status:** Partial (structure correct, response not scoped to question).

### Case 2: "¿Qué ocurrió antes de la caída?"
- **understand() (A7):** BEFORE_AFTER detected → **plan.anchor = FALL DETECTED** (inferred). relations=(BEFORE_AFTER,). ops typically [range, aggregate(summary)] depending on intent. window/hour may come from intent.
- **engine:** resolves anchor `m-05` (ts ~NOW-4h), sets `until = anchor.ts`, computes `before = episodes_before(..., target_ts=until)` and **now also `after = episodes_after(..., target_ts=until)`** (A7). Trace records `target_ts`, `episodes` (before), `episodes_after`, `count`, `count_after`.
- **retrieval/relate:** evidence in window; before_after cut at anchor is correct (5 episodes before in fixture). Derived relations + spatial/camera groups.
- **real utterance:** still evidence-based top 3 lines (unchanged by A7). 
- **expected conversational:** list of events before the fall (e.g. GATE_OPEN, PERSON crossing, MOTION shortly before, etc., in order) anchored to m-05.
- **exact gap:** `render_utterance` ignores the anchor and before/after sets — it just renders retrieved evidence slice. Trace is correct; synthesis is not question-directed.
- **working now:** anchor resolved + before/after computed + exposed in trace. Engine-capable.

**Status:** Partial (anchor+direction data exist; spoken answer not tailored to "antes de...").

### Case 3: "¿Qué ocurrió después de la caída?"
- **understand() (A7):** same as case 2 → `plan.anchor = FALL DETECTED`, `relations=(BEFORE_AFTER,)`. Direction word “después” present but RelationKind unchanged; no separate direction flag in plan yet.
- **engine:** computes both `before` and `after` (A7). Trace has `count_after` (8 in fixture). Anchor cut is correct.
- **real utterance:** identical to case 2 (evidence-slice) — no direction-based selection.
- **expected conversational:** events after fall (m-06 PERSON_ELDERLY salon, m-07 cocina, m-08/m-09 SMOKE, m-10 MOTION salon, m-11/m-12 PET patio, etc.)
- **exact gap:** plan has no `direction` (before/after) → synthesis cannot choose `after` set. Also `render_utterance` doesn’t consume BEFORE_AFTER results. 
- **working now:** data available (`episodes_after`, `count_after`) in trace; engine can cut correctly.

**Status:** Partial (data ready; direction not propagated to utterance).

### Case 4: "¿Qué pasó mientras estaba fuera?"
- **understand() (A7):** `"mientras estaba fuera"` → `Anchor.SESSION_START` detected (existing) and with BEFORE_AFTER/TIMELINE context maybe timeline relation; A7 also infers anchor in before_after/timeline cases — here session anchor is separate. relations include TIMELINE (planner maps “mientras…” to TIMELINE). 
- **engine:** with `session_start` provided, window anchored to session_start (when Anchor.SESSION_START). Timeline computes episodes + **gaps > max_gap** (DEFAULT_TIMELINE_GAP_SECONDS=300). Derived relations run.
- **retrieval:** all records in that window.
- **real utterance (MCP mode):** MCP resolver (`memory_recall` dispatch) **does not pass `session_start`** to recall(); only HTTP `/api/recall` accepts `session_start` (A6G B5). So MCP run uses `session_start=None` → window not session-restricted unless engine uses other logic. 
- **expected conversational:** summary of what happened during absence: events list + notable gaps (silences). 
- **exact gap:** boundary propagation: to see true “mientras estaba fuera” effect via MCP tool you must pass session_start; surface/schema doesn’t expose it in memory_recall tool (documented). Also utterance not timeline-aware.
- **working now:** timeline gaps computed correctly when session_start applied.

**Status:** Partial (timeline+gaps correct with proper boundary; boundary not exposed in MCP recall tool; utterance not timeline-driven).

### Case 5: "¿Qué eventos están relacionados?"
- **understand() (A7):** expanded vocab → `relacionado(s/as)/related/between/entre` map to **CORRELATION**. So `relations` likely includes CORRELATION (and possibly others). Case 5 now triggers relation detection (A6G B4 fixed). 
- **engine:** executes requested relations (correlation groups by camera/zone as appropriate), plus `_derive_relations` runs when any plan.relations set → builds full pairwise graph (capped at 64), produces context items (salience 1–3). Narration renders top narratable (salience>=3, cap 3). 
- **real utterance:** evidence-based slice (unchanged). 
- **context_response:** may be non-empty (e.g. `"SMOKE en el mismo instante."` if that pair is narratable and not cut). 
- **expected conversational:** coherent grouping/chain (e.g. reja→persona→caída related in space/time; smoke seen by two cameras at same instant). 
- **exact gap:** “related” is vague; answer should reflect correlation/timeline/transition. Current synthesis doesn’t turn derived context into a structured answer (it only renders evidence). Also cap can drop `temporal_transition` (A6G B7) — narration may miss some links. 
- **working now:** detection fixed (B4); relations+context+narration computed.

**Status:** Improved vs A6G (now triggers relations). Still partial as conversational answer.

### Case 6: "¿Qué cámaras observaron el mismo evento?"
- **understand() (A7):** “cámaras…” + “mismo…” map to CORRELATION (existing + expanded). relations include CORRELATION. May also get SPATIAL/TIMELINE depending on phrasing. 
- **engine:** `relate:correlation` groups by camera_id (degraded to source if missing). Derived relations include `correlation_overlapping` for events at same instant (m-08 cocina/cam-4 and m-09 salon/cam-3 share same timestamp → overlap 0 → narrated as “en el mismo instante”). 
- **real utterance:** evidence-based. 
- **context_response (narration):** contains `"SMOKE en el mismo instante."` (matches SMOKE pair). 
- **expected conversational:** “cam-4 y cam-3 observaron humo al mismo tiempo” (names cameras). 
- **exact gap:** narration describes labels/time (“SMOKE en el mismo instante”) but **does not name camera_ids** (narrative layer consumes relation facts like seconds/overlap/labels, not camera groups). Also utterance not camera-directed. MCP doesn’t surface `context_response` in its rendered text (only in JSON payload). 
- **working now:** camera groups exist in trace; overlapping detected.

**Status:** Partial (structure exists; answer not explicit about which cameras).

## 4. What works (today)

- **Planning (A7):** BEFORE_AFTER/TIMELINE get `plan.anchor` inferred (FALL DETECTED on caída). Relation vocab expanded (related/between/entre). 
- **Anchoring:** engine resolves anchor correctly; cuts before/after at anchor ts. 
- **BEFORE_AFTER direction data:** `episodes_after` and `count_after` exposed in trace (A7) — data layer complete for direction choice.
- **Timeline:** episodes + gaps computed; session_start respected when passed. 
- **Spatial/camera:** zone/camera grouping with degradation reported.
- **Relations + context + narration:** derived graph, salience, narratable selection (cap 3 sentences). Overlap==0 handled as “en el mismo instante”. 
- **Determinism + trace:** full audit (ops_executed, relations, evidence_ids, context). 535 tests green.
- **Parallel channel:** `/api/recall` returns full payload including `context_response`; engine pure and LLM-free.

## 5. What still lacks (functional gaps)

| Gap | Where | Effect | Suggested next step (non-implementing note) |
|---|---|---|---|
| **G1. Response not question-directed** | `recall_engine.execute()` uses `render_utterance(evidence, ...)` only; doesn’t use BEFORE_AFTER (before/after sets), aggregate results, timeline gaps, or camera groups to shape answer. | All 6 cases produce generic top-3 evidence lines (same pattern) rather than answering the specific question. | Synthesis policy: if BEFORE_AFTER + anchor → render “before/after of <anchor>” from episodes_before/after (respect direction). If aggregate requested → summarize counts. If TIMELINE → include key gaps. If CORRELATION groups by camera → name cameras. Keep `render_utterance` for fallback only. |
| **G2. Direction (before vs after) not propagated** | `RecallPlan` has no `direction` (or `before_after` intent); understand() can’t distinguish “después de…” vs “antes de…”. Both produce same RelationKind + same anchor. | Case 3 same answer as case 2. | Add optional `direction: 'before'|'after'|None` to plan (or set from phrase) and have synthesis pick episodes_before or episodes_after accordingly. (Engine already exposes both.) |
| **G3. MCP boundary: session_start not exposed** | `memory_recall` tool schema/dispatch (MCP path) doesn’t accept/pass `session_start`; only HTTP `/api/recall` does. | Case 4 “mientras estaba fuera” can’t be evaluated correctly via MCP recall tool in practice. | Expose `session_start` in MCP recall tool schema + pass through to `recall()` (parallel to HTTP). No change to memory_converse. |
| **G4. Narration doesn’t name cameras/anchors** | `context_narrative` renders time/labels/transition/overlap only; doesn’t emit camera_ids or anchor names. | “mismo evento” known (overlap) but which cameras not stated. | Extend narration facts to include camera groups (or emit a separate camera-correlation sentence) when correlation groups nontrivial. Keep deterministic and minimal. |
| **G5. Graph cap can drop narratable links** | `relate_episodes` caps at 64, ordered by `(kind, subject, object)` (alphabetic); `temporal_transition` (salience 3) can be truncated. | Some useful transitions may not reach narration (A6G observed). | Sort by salience desc before cap (or increase cap) so high-salience items preserved first. Low risk to existing tests (ordering of kept set changes, not presence of required relations). |
| **G6. Question-scoping (last_seen/where-pet)** | “¿Dónde vi mi mascota?” doesn’t become `last_seen(PET)`. | Answer includes non-pet lines. | Planner: if question contains “dónde vi <entidad>” and entity maps to label (PET/PERSON etc.) prefer LAST_SEEN or filter RANGE to that label (and order desc). |

## 6. Verdict

**EchoMind is an auditable memory reasoning engine, not yet a full conversational memory responder.**

- **Reasoning/audit:** ✅ Strong. Retrieval, anchoring, timeline+gaps, spatial/camera, relations, context, narration all work and are traceable.
- **Conversational answering:** ⚠️ Partial. The gap is synthesis (B3) — `render_utterance` from raw evidence doesn’t use the rich structure now available (before/after sets, direction, aggregates, timeline gaps, camera groups). A7 improved the planning/engine data (anchor, after-counts, vocab) but the spoken surface still reflects “top evidence lines”, not the question’s intent.
- **Pragmatic path:** close G1–G3 first (synthesis policy + direction + MCP session_start). These are additive and low-risk; they would make 5–6 of the cases read as genuine conversational answers while keeping V1 behavior intact where not needed.

**Bottom line:** Yes, the core memory experience is real and testable; the “conversational” feel is the remaining functional gap (synthesis layer), not the underlying engine.
