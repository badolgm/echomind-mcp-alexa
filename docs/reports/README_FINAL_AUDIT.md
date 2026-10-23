# README_FINAL_AUDIT.md — EchoMind

**Audited:** `README.md` (identical in both uploads, `d1409b4d` = `32b48b58`, 475 lines) + the five final SVGs + `DIAGRAM_FINAL_PACKAGE.md`
**Date:** 2026-10-20 · **Mode:** audit only. README not modified, no README_V4 created, no features/AWS usage invented.

---

## 0. Verdict

| Score | Value |
| ----- | :---: |
| **Final README score** | **6.5 / 10** |
| **Final hackathon readiness** | **6 / 10** |
| **Final open-source readiness** | **5 / 10** |

### Decision: ❌ NOT READY FOR GITHUB PUBLICATION

The README is honest and well structured, and its core ideas (two truth sources, closed vocabulary, abstention,
"where Bedrock is and is not") are stronger than most hackathon submissions. It is **not publishable as is** for
these reasons, each one verified or reproducible in minutes:

1. **The documented demo cannot be run by anyone who clones the repo.** Every "Drive it like Alexa+" command points to `.local/scripts/`, which the README itself says is git-ignored (M3). There is also no seed step and no sample output anywhere (M4).
2. **None of the 5 diagrams is clickable, and all are illegible when embedded.** At README width (~880 px) their text renders at **5.9–8.9 px** (M1).
3. **Three of the five diagrams contradict the README text** (hero arrow from Recall to Bedrock, inverted router arrows, `ResponseIntent` drawn after synthesis) (M6).
4. **An AWS-facing claim is internally inconsistent.** The README claims image/video/audio/document input with default model `amazon.nova-micro-v1:0`; AWS documents Nova Micro as **text-only** (M5). An AWS Builder judge will catch this in one click.
5. **Several claims are unverifiable or probably overstated** (persistence, "live" sensors, "evidence and trace on every answer", "nothing is deleted") (M7).
6. **No test count, no CI evidence, no table of contents, and the LICENSE/deep-dive files cannot be confirmed to exist in the repo** (M2, M10, M11).

None of this requires redesign. Estimated effort to clear M1–M11: **2–3 hours**. Re-audit gate in §9.

---

## 1. Checklist results

| # | Item | Result | Evidence |
| - | ---- | :----: | -------- |
| 1 | Professional Table of Contents | ❌ missing | No TOC; 15 sections. Ready-to-paste block in §7 → **M2** |
| 2 | Section anchors | ✅ | 5/5 in-page links resolve (`#9-alexa-integration`, `#10-aws-builder-integration`, `#5-system-architecture`, `#15-license`) via GitHub-slug check. All 15 section slugs computed (§7) |
| 3 | Image references | ⚠️ | 5 `<img src="./*.svg">` → all 5 SVGs exist in the upload. Presence at **repo root** not verifiable here (preflight in §8). `domain-erd.svg` embeds a 7 KB C2PA manifest, the other four do not |
| 4 | Every SVG clickable | ❌ | `<a>` tags in README: **0**. 5 of 5 images are bare → **M1** |
| 5 | Every architecture reference exists | ⚠️ | `ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md` and `A7C_QUERY_ROUTER_ARCHITECTURE.md` are plain text (not links), existence in the tracked repo unverified, and both are Spanish → **M11** |
| 6 | LICENSE section | ⚠️ | `[LICENSE](LICENSE)` is a relative link; file existence/holder match unverifiable → **M11** |
| 7 | AWS Builder section | ❌ | Honest on scope, but Nova Micro vs multimodal contradiction → **M5**; no "verify Bedrock is live" path → R6 |
| 8 | Alexa+ section | ⚠️ | No account of how Alexa+ reaches the server or whether a real device was used → **M9**; language mechanism undocumented → R1 |
| 9 | Getting Started | ❌ | `.local/scripts`, no seed, PowerShell only, no Python version → **M3, M4**, R5 |
| 10 | Testing | ❌ | No test count, no CI, no mention of the invariant tests → **M10** |

---

## 2. Mandatory corrections (block publication)

> Tags: **[VERIFIED]** = confirmed from the files/tools in this audit. **[VERIFY-IN-REPO]** = needs the repo; command in §8.

### M1 — Make every SVG clickable (and legible) [VERIFIED]

**Where:** lines 3, 121, 161, 199, 243.
**Problem:** 0 links wrap the images. Rendered at ~880 px wide the text is:

| SVG | viewBox | 12 px text renders at | 13 px text renders at |
| --- | ------- | :-------------------: | :-------------------: |
| hero | 1280×720 | 8.2 px | 8.9 px |
| system-architecture | 1400×980 | 7.5 px | 8.2 px |
| memory-reasoning | 1400×900 | 7.5 px | 8.2 px |
| query-router | 1400×940 | 7.5 px | 8.2 px |
| domain-erd | 1800×1696 | **5.9 px** | **6.4 px** |

Clicking is therefore not cosmetic: it is the only way a reader can read them.
**Fix (pattern, apply to all five):**

```html
<p align="center">
  <a href="./system-architecture.svg">
    <img src="./system-architecture.svg" alt="…existing alt text…" width="100%"/>
  </a>
  <br/><sub>Click to open full size</sub>
</p>
```

For the hero (inside the centered `<div>`): `<a href="./hero.svg"><img src="./hero.svg" alt="…" width="100%"/></a>`.
**Verify:** `grep -c '<a href="./.*\.svg">' README.md` returns 5. Click each on github.com after push.

### M2 — Add the Table of Contents [VERIFIED]

Paste the block in §7 between the closing `</div>` (line 19) and `---` (line 21). All anchors were computed with the GitHub slug algorithm.

### M3 — `.local/scripts` references are dead for every reader [VERIFIED]

**Where:** lines 380–396 (`alexa_mcp_simulator.py` ×2, `run_demo.py`); line 382 says they are git-ignored.
**Problem:** a judge or contributor cloning the repo cannot run any of the three commands.
**Recommendation: Option B, move them to a tracked `scripts/` folder**, plus a script-free `curl` fallback. Full reasoning and procedure in §5.

### M4 — No runnable end-to-end path and no sample output [VERIFIED]

**Problem:** a fresh server has an empty store, so the hero example *"¿Cuándo viste a alguien por última vez?"* returns an abstention. `/api/demo/seed` exists in the code (see `DIAGRAM_FINAL_PACKAGE.md` §2, `demo_seed_service`) but the README never mentions it. The README's headline feature, "answer + evidence + trace", is never shown: there is **no sample `/api/recall` response, no screenshot, no GIF**.
**Fix:** add a "Try it in 60 seconds" block after step 3 of Getting Started:

1. seed the demo memory (use the HTTP method the route declares in `src/main.py`);
2. ask one present-tense question and one past-tense question;
3. show the **real** captured output (utterance + evidence + trace excerpt).

**Rule:** paste output from an actual run. Do not hand-write it. If a value cannot be captured, omit it.

### M5 — Nova Micro cannot do what the AWS section says [VERIFIED against AWS docs]

**Where:** lines 322–323.
**Problem:** the table lists *Multimodal input: images, video, audio and documents* and *Default model: `amazon.nova-micro-v1:0`*. The AWS model card for Nova Micro lists input modalities **Text only** (Audio ✗, Image ✗, Speech ✗, Video ✗); Converse is supported ([AWS model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html)). As written, an image sent to the default model is rejected by Bedrock.
**Why it is dangerous:** if `ResilientLLMAdapter` treats that rejection as a failure and falls back, `analyze_image_context` would silently run on `RuleBasedLLMAdapter` while the README presents it as Bedrock multimodal. That would be the single most damaging finding for the AWS Builder challenge.
**Fix:** state which model ID serves which modality (text vs multimodal) and make the default consistent with the claim. Do not claim audio/video unless a tested model and code path exist.
**Verify (needs live AWS credentials):** call `analyze_image_context` with a real image, then read `GET /metrics`. `fallbacks_activated` must stay `0`. Paste that result in the AWS section as proof.

### M6 — Diagram errors that contradict the README [VERIFIED from SVG source]

**(a) `hero.svg`:** dashed arrow `x1=860 y1=572 → y2=620` starts **inside the Memory Recall box** (box spans y 430–600) and points to the Bedrock box, i.e. it draws *Recall → Bedrock*. It also runs along the right edge of the Ingestion box (x=860), and the Bedrock rect overlaps the Ingestion rect by 10 px (x 850–860, y 630–670). This contradicts the dashed box's own label "NOT in the memory path" and README lines 153, 316–317. **Fix:** remove the arrow; show Bedrock as a branch off the MCP server ("multimodal/ambient tools") and keep it visually separate from Recall.

**(b) `query-router.svg`:** the green arrow `M700,380 → 780,365` (to CURRENT_STATE) leaves rows 1–2 (`count`, `memory-anchor`, y 302–422), which result in RECALL. The orange arrow `M700,640 → 780,640` (to RECALL) leaves row 5 (`overview`, y 614–670), which results in CURRENT_STATE. The arrows are visually inverted. **Fix:** draw from rows 4–5 to CURRENT_STATE and from rows 1–3 and 6 to RECALL.
 The same SVG callout and README lines 232–234 say *"present marker `cerrada`"*, but the rule-4 table (SVG and README line 212) lists present markers `está · hay · ahora · is · now · open · closed` and no `cerrada`. In *"¿La reja está cerrada?"* the present marker is `está`; `cerrada` provides polarity. **Fix:** correct the sentence (or the table, if `cerrada` really is in `_PRESENT_MARKERS`).

**(c) `memory-reasoning.svg`:** arrows `680→640` (Synthesize → ResponseIntent) and `340→300` (ResponseIntent → RecallResult) make `ResponseIntent` a stage **after** synthesis, and it is unnumbered. README lines 167–175 list 7 steps without it and line 170 says the plan carries `response_intent`; line 174 says synthesis dispatches by it. **Fix:** `Plan → ResponseIntent → Synthesize → RecallResult`. Also add a footnote that `CURRENT_STATE` appears in the plan's op list (box 2) yet the router answers present-tense questions without touching the store (README §7), so a reader does not see two contradictory `CURRENT_STATE`s.

**(d) `system-architecture.svg`:**
- Vivotek arrow `(815,213)→(800,270)` lands inside **INFRASTRUCTURE SERVICES** (x 540–1010) while the Android arrow lands in ADAPTERS. Both are adapters (`adapters/camera`, `adapters/iot` per the package doc).
- `HttpPhoneCameraAdapter` / `VivotekCameraAdapter` are never named (one line says "boto3/camera adapters"), although the package doc lists them as included entities.
- The domain's purple arrow `M1190,584 … 1240,640` ends at **OUTPUTS**, not at the ports box. Nothing points from the domain to `MCPServerPort`/`LLMServicePort`.
- The arrow `M600,610 L540,610 L540,600` ("infra depends on ports") floats between boxes and touches the ports box nowhere (ports start at y=640).
- The Bedrock box sits outside the ADAPTERS box though `adapters/aws/` is an adapter.
- Footer says *"pure domain (router/planner/engine)"* while `RecallEngine` is drawn inside INFRASTRUCTURE SERVICES. Same contradiction in README line 143 vs the table at line 131.
- No `application/` layer is drawn, though README line 149 lists it.

**(e) `domain-erd.svg` vs README §8:** the purple arrow `(675,311)→(675,420)` labelled `resolve_anchor` goes from **AnchorRef → Episode**. README line 271 says AnchorRef is resolved **from MemoryRecord**. Both can be true (anchor resolved from a record, then used to cut episodes), but only one is drawn. `RecallResult`/`RecallTrace` appear only as header text, not as entities.

### M7 — Truthfulness pass on claims that may be false or unprovable

| Claim | README line | Problem | Fix | Check |
| ----- | :---------: | ------- | --- | :---: |
| "evidence and trace on every answer" | 75 | `CURRENT_STATE` answers read snapshot fields, no records. Voice only speaks the `utterance`. V1 `memory_converse` returns fixed literals | "Every **recall** answer carries evidence and a trace on `/api/recall`; state answers cite the snapshot field" | [VERIFIED] |
| "persisted as vector memory" / "Persists coalesced…" | 52, 102 | The V2 design doc described the store as in-memory with Qdrant Edge as a future port. README never states restart behavior | State exactly: in-process store or on-disk, and what survives a restart | [VERIFY-IN-REPO] |
| "live snapshot", "home sensors" | 27, 51, 110, 308 | V2 design doc: `SimulatedSensorBus` baseline. The hero answer *"¿La reja está cerrada?"* reads `gate_open` | Say which signals are real (cameras) and which are simulated or demo-seeded. If `iot/` has real sensors, name them | [VERIFY-IN-REPO] |
| "Nothing is deleted; low-salience relations are demoted" | 278 | `relate_episodes` caps the graph at 64; A6G observed `temporal_transition` being truncated | Reword to "capped at N, ordered by …", or drop the claim if the cap is gone | [VERIFY-IN-REPO] |
| "A new relation type is a row in `relation_rules.py`" | 85, 185 | A new **rule** is a row; a new **kind** needs the closed vocabulary changed (`domain-erd.svg`: unknown kind → `ValueError` in `__post_init__`) | "A new rule is a table row; a new kind is a vocabulary change that tests guard" | [VERIFIED] |
| "pure domain (router / planner / engine)" | 143 | Engine is in `infrastructure/services` (line 131) | Fix the sentence or the layer table | [VERIFIED] |
| "Reason = router + current_state_reasoning" | 55 | The router is step 0 of every question (before Recall). Reasoning over memory is relations → context → synthesis | Make the router an explicit "step 0" and map Reason to relate/derive/synthesize | [VERIFIED] |

### M8 — "Pure domain" vs where the types live [VERIFIED wording, VERIFY-IN-REPO imports]

**Where:** lines 132, 246, 253–254, 131.
README §8 opens with *"Pure domain structures…"*, then lists `Episode` and `TimelineGap` in `memory_timeline.py` (an **infrastructure/services** module per §5) and admits `MemoryRecord` is in infrastructure, while `Evidence`/`relate_episodes` (domain) consume them. Either the domain imports infrastructure (which breaks the dependency rule on lines 146–151) or it uses structural typing. A maintainer reviewing the repo will grep for this.
**Fix:** state how the dependency rule is preserved (Protocols/duck typing/injection) or move the value objects into `domain/`. Reference `test_domain_purity.py` if it guards this. Command in §8.

### M9 — Alexa+ connectivity and evidence of a real integration [VERIFIED gap]

**Where:** §9.
The README says Alexa+ "calls EchoMind over Streamable HTTP", but never says (a) how a service on `localhost:8000` is reachable from Alexa+ (public HTTPS URL, tunnel, hosted deployment), (b) how `alexa_skill/skill.json` is registered, or (c) whether a real Alexa+ device/console session was used or only the maintainer simulator (which is git-ignored, M3).
**Fix:** one honest sentence: *"Validated with the MCP simulator (`scripts/…`) / validated on Alexa+ device"*, whichever is true, plus the connection steps. Do not imply device validation if it was not done.

### M10 — Testing section has no numbers and no CI [VERIFIED]

**Where:** lines 415–430. `668` (the figure you asked for in the first brief) and any test count are **absent**; and 668 predates A7D, so it is probably stale anyway.
**Fix:**
1. Run `pytest --collect-only -q | tail -1` and print the real count in the section.
2. Name the invariant suites that make the determinism claim credible (domain purity, determinism, forbidden vocabulary, zero-impact checks), if they exist as tests.
3. Add a GitHub Actions workflow (pytest + flake8 + black) and a status badge.
4. Say which requirements file installs `pytest`/`flake8`/`black` (line 348 installs only `requirements.txt`).

### M11 — Reference integrity [VERIFY-IN-REPO]

| Reference | Line | Risk |
| --------- | :--: | ---- |
| `LICENSE` | 468 | Link breaks if the file is missing; verify the holder matches the README |
| `ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md`, `A7C_QUERY_ROUTER_ARCHITECTURE.md` | 192, 236 | Plain text, not links; may live in a git-ignored folder; **both Spanish** while README is English |
| `alexa_skill/skill.json`, `src/domain/models/tools.py` | 290, 291 | Must be tracked |
| `docker-compose.yml`, `Dockerfile`, `requirements.txt` | 348, 367, 330 | Must be tracked |
| 5 SVGs at repo root | 3, 121, 161, 199, 243 | Must be tracked at exactly these paths (R3 suggests `docs/assets/`) |
| `DIAGRAM_FINAL_PACKAGE.md` | — | Contains session-process notes (*"sin commits, sin push"*, HEAD hash, mentions of artifacts that "do not exist"). **Do not publish it in the repo root.** Move to `docs/` or keep local |

---

## 3. Recommended corrections

| # | Item | Why |
| - | ---- | --- |
| **R1** | **Document how the language is chosen.** Add a "Language" subsection (see below) | "Bilingual" is a headline claim with no mechanism described |
| **R2** | Define **A1–A7D** and "Phases 1–8" in one table (what each added). Rename `## 1. Hero` → `## 1. Overview`. Merge §13 Status and §14 Roadmap. Fix footer typo `Alexa +` → `Alexa+` (line 472) | A7C/A7D are used (lines 181, 232, 447–448) but never defined; two phase schemes coexist |
| **R3** | Move the 5 SVGs to `docs/assets/` and update the 5 `src`/`href` pairs | Repo root clutter; keeps README first screen in file list clean |
| **R4** | SVG legibility and hygiene: keep each canvas ≤ 1000 px or ≥ 13 px at design size; split `domain-erd.svg` (1800×1696 renders at 5.9 px); add `<title>`/`<desc>` (all 5 have only `aria-label`); hero tagline `#64748b` on `#0b0f19` = **4.02:1** (< 4.5) | Accessibility and readability |
| **R5** | Getting Started: add bash/zsh equivalents, the Python version (Docker uses 3.11), `requirements-dev.txt` if separate, and a `.env.example` | Linux/macOS reviewers and judges |
| **R6** | AWS: add "Verify Bedrock is live": required IAM actions, model access enabled in the console, region, expected `/metrics` `fallbacks_activated: 0`, and one sentence on cost. State plainly which AWS services are used (Bedrock) and that nothing else is deployed if that is the case | AWS Builder judges want proof of real use, not only a fallback demo |
| **R7** | Security note: `/mcp`, `/api/*` and `/api/demo/seed` bind to `0.0.0.0` (line 351, 407). State whether any auth exists and that the server is for trusted networks | Open-source reviewers ask this first |
| **R8** | Domain Model accuracy: (a) cardinality row 1 reads *MemoryRecord 1..\* Episode*; it is **Episode groups 1..\* MemoryRecord** (`Episode.record_ids`); (b) row 2 *Episode 1..\* TimelineGap* is wrong: a gap sits **between two consecutive episodes**; (c) list the 12 relation kinds (5 temporal, 3 spatial, 4 correlational: `domain-erd.svg` already lists them); (d) `RelationKind` (5 plan-level values, line 180) and `KNOWN_RELATION_KINDS` (12) are different enums with confusing names; (e) `TimeWindow.anchor ∈ {NOW, SESSION_START, EXPLICIT}` vs `RecallPlan.anchor` (a label string) share a name; (f) `Relation.subject/object` are annotated *"(record id)"* in the ERD while relations are computed between episodes, so say how an episode is referenced | Reviewers cross-check README against ERD |
| **R9** | Router edge cases: the visible `_PAST_MARKERS` list has no *ayer / hace / estaba / yesterday / ago* and `abierta/cerrada` look like state words. Test and document the result of *"¿Estaba abierta la reja ayer?"*, *"Was the gate open an hour ago?"*, *"¿Hubo humo hace un rato?"*. If any returns live state, it is the first bug a judge will find | Present-vs-past is your headline decision |
| **R10** | Tool surface: list the 5 memory tools by name (`memory_last_seen`, `memory_search`, `memory_summary`, `memory_converse`, `memory_recall`), add `/api/demo/seed` to the route list (line 295), and add an env var for the Android camera if one exists (line 100 vs table at lines 400–408) | Line 292 names only 2 of the 5 |
| **R11** | Provide English summaries (or English versions) of the two "deep dive" documents, or label them *(Spanish)* | Amazon judges read English |
| **R12** | Repo hygiene: CI workflow and badge, `.gitignore` reviewed, `CONTRIBUTING.md`/`SECURITY.md` (short), release tag matching the submission | Open-source readiness |
| **R13** | State that the system is **single-turn per query** (no conversation state across questions) if true, and that "Reason" means computed comparison over stored facts, not model inference | Heads off the "where is the AI / is it conversational?" objection |

**Suggested `R1` text** (evidence: `query-router.svg` footer: *"router uses MemoryIntentClassifier only for language detection, so history and state paths always agree on es/en"*):

> **Language.** There is no language setting. EchoMind detects `es` or `en` from each question's text (`MemoryIntentClassifier`, used by the router for language detection) and answers in that language; `route_query(text, lang?)` accepts an explicit override. Answers are rendered from bilingual templates. The Alexa+ voice is chosen by the device/skill locale (see `alexa_skill/skill.json`). The Control Center's browser TTS speaks Spanish only.

Before publishing that paragraph, check: what happens with mixed or very short text (*"gate?"*), whether the *"No dispongo…"* message has an English twin, and which locales the skill manifest declares.

---

## 4. Optional improvements

| # | Item |
| - | ---- |
| O1 | A 20–30 s GIF of the seeded demo (ask → answer → evidence/trace) and a Control Center screenshot |
| O2 | A short "Limitations" section (single-turn, local store, simulated sensors if true, text/multimodal model scope) |
| O3 | A short "Design decisions" list (ADR style): deterministic memory path, no `confidence` on relations, closed vocabulary |
| O4 | Soften the comparison table in §3 (line 69–77); "chatbots: no" in several rows reads as a strawman |
| O5 | `<picture>` light/dark variants of the hero |
| O6 | Decide deliberately about the C2PA manifest embedded only in `domain-erd.svg`: it labels the file as AI-provided and inflates it by ~7 KB. Keep it on all files (consistent, transparent) or strip it everywhere (`svgo`). If the hackathon has an AI-disclosure rule, follow that |
| O7 | CI "diagram lint": a script that extracts module/class names from the SVGs and fails if they do not exist under `src/`. This guarantees diagrams cannot drift from code again |
| O8 | A `CHANGELOG.md` with the A1–A7D phases |
| O9 | A privacy note: the license line uses a full legal name; confirm that is intentional and consistent with the commit author |

---

## 5. Recommendation for `.local/scripts`

**Choose B: move the two scripts into a tracked `scripts/` folder**, and add a script-free `curl` quickstart (M4) so the README works even if the scripts break.

| | A) Remove the references | B) Move to tracked `scripts/` |
| - | ------------------------ | ----------------------------- |
| Reproducibility | Loses the only documented way to exercise MCP like Alexa+ (session negotiation, SSE, JSON-RPC, base64 attachments) | Keeps it; judges can run the exact commands in the README |
| Credibility | README would claim Alexa+ integration with nothing to test it | Supports M9: the simulator becomes evidence |
| Cost | Zero | ~20 min incl. secret scan |
| Risk | None | A private path, IP or credential might be inside the scripts or `.local` history |

**Why B wins:** the README's central claim is "Alexa+ calls EchoMind over MCP". The simulator is the only artifact that demonstrates it. Removing it leaves a claim with no test path, and the judge cannot confirm anything beyond `/health`.

**Procedure**
1. Scan before copying: `grep -rnE "AKIA|aws_secret|AWS_SECRET|password|token|192\.168\.|C:\\\\Users" .local/scripts` and fix anything found (make hosts/keys parameters or env vars).
2. Copy **only** `alexa_mcp_simulator.py` and `run_demo.py` to `scripts/`. Keep the rest of `.local/` ignored.
3. Make sure they import nothing from `.local/` and use only `requirements.txt` dependencies.
4. Add a short docstring/`--help` for each and one README line per script.
5. Update README lines 380–396: `python scripts/alexa_mcp_simulator.py …`, reword *"Maintainer scripts in the git-ignored `.local/scripts/`"* to *"Scripts in `scripts/` emulate Alexa+…"*.
6. Confirm history is clean: `git log --all --oneline -- .local` should show nothing (the files were never tracked).
7. `git ls-files scripts/` lists both before you tag the release.

---

## 6. Findings catalogue (requested documentation)

### 6.1 Technical inconsistencies

| ID | Finding | README / file | Fix |
| -- | ------- | :-----------: | :-: |
| T1 | Nova Micro is text-only but multimodal input is claimed with it as default | 322–323 | M5 |
| T2 | "present marker `cerrada`" vs marker table (`está…`) | 212 vs 233, SVG callout | M6b |
| T3 | `ResponseIntent` is plan-carried (README) but drawn after synthesis (SVG) | 170, 174 vs `memory-reasoning.svg` | M6c |
| T4 | Cardinalities inverted/incorrect (records→episode, episode→gap) | 266–267 | R8 |
| T5 | Two enums called relation kinds (5 vs 12), never reconciled | 180 vs 276 | R8 |
| T6 | "A new relation type is a row" vs closed vocabulary that raises on unknown kinds | 85, 185 | M7 |
| T7 | "Nothing is deleted" vs a 64-relation cap | 278 | M7 |
| T8 | `CURRENT_STATE` is both a `RetrieveKind` (engine op) and a router domain that never touches the store | 104, 179 vs 224–225 | M6c footnote |
| T9 | Test count absent (668 requested; now probably stale after A7D) | 415–430 | M10 |
| T10 | Env-var table has Vivotek IP but no Android camera setting | 100, 408 | R10 |
| T11 | Tool surface names 2 of the 5 memory tools; `/api/demo/seed` not listed | 292, 295 | R10 |
| T12 | `TimeWindow.anchor` (enum) and `RecallPlan.anchor` (label) share a name | `domain-erd.svg` | R8 |

### 6.2 Architectural inconsistencies

| ID | Finding | Where | Fix |
| -- | ------- | ----- | :-: |
| A1 | `RecallEngine` listed as infrastructure, described as pure domain in the query flow and the SVG footer | 131 vs 143; `system-architecture.svg` | M6d, M7 |
| A2 | §8 "Pure domain structures" lists types located in infrastructure modules | 246, 253–254 | M8 |
| A3 | `src/application/` has a dependency-rule bullet but no row in the layer table and no box in the SVG | 149 vs 127–134 | M6d |
| A4 | Domain arrow goes to OUTPUTS instead of ports; "infra depends on ports" arrow floats | `system-architecture.svg` | M6d |
| A5 | Both camera adapters are adapters, but one arrow lands in INFRASTRUCTURE SERVICES; adapters unnamed | `system-architecture.svg` | M6d |
| A6 | Stage table puts the router under "Reason", but it runs before Recall | 55 | M7 |
| A7 | ERD draws AnchorRef → Episode; README says resolved from MemoryRecord | `domain-erd.svg` vs 271 | M6e |
| A8 | Bedrock arrow from Recall in the hero contradicts "not in the memory path" | `hero.svg` vs 153, 316 | M6a |

### 6.3 Potential judge objections

| # | Objection | Answered in README today? | Fix |
| - | --------- | :-----------------------: | :-: |
| 1 | "Bedrock is outside your core. Why is this an AWS Builder entry?" | Partly (§10 is honest) | M5, R6 |
| 2 | "Nova Micro is text-only. How is this multimodal?" | **No** | M5 |
| 3 | "What survives a restart? Is memory persistent?" | **No** | M7 |
| 4 | "Are the sensors real or simulated?" | **No** | M7 |
| 5 | "Did you test on a real Alexa+? How does it reach your laptop?" | **No** | M9 |
| 6 | "Show me an actual answer with evidence and trace." | **No** | M4 |
| 7 | "Where is the AI? Is a rule table 'AI'?" | Partly (determinism is explained) | R13 |
| 8 | "Does a past-tense question ever return live state?" | **No** | R9 |
| 9 | "Your domain is 'pure' but imports infrastructure types?" | Partly | M8 |
| 10 | "How many tests; is there CI?" | **No** | M10 |
| 11 | "Can I run it on Linux without your private scripts?" | **No** | M3, R5 |
| 12 | "Is it conversational or single-turn?" | **No** | R13 |
| 13 | "Is there authentication on `/mcp` and `/api/*`?" | **No** | R7 |
| 14 | "Which languages, and how is it chosen?" | **No** | R1 |

### 6.4 Potential reproducibility issues

| ID | Issue |
| -- | ----- |
| P1 | `.local/scripts/` is git-ignored (M3) |
| P2 | No seed step, so a fresh server answers every memory question with an abstention (M4) |
| P3 | PowerShell-only commands; no bash/zsh (R5) |
| P4 | No Python version for the local path (Docker uses 3.11) (R5) |
| P5 | Dev tools (`pytest`, `flake8`, `black`) not tied to an install command (M10) |
| P6 | No `.env.example`; Vivotek default is a private LAN IP (`192.168.40.10`) with no "skip if you have no camera" note |
| P7 | Bedrock live run needs model access + IAM actions + region; not documented (R6) |
| P8 | Alexa+ cannot reach `localhost`; connection steps absent (M9) |
| P9 | Deep-dive docs may not be in the repo; Spanish only (M11, R11) |
| P10 | No expected output for `/health`, `/metrics` or any query (M4) |

### 6.5 Potential credibility issues

| ID | Issue |
| -- | ----- |
| C1 | Multimodal claim with a text-only default model (M5) |
| C2 | "Persisted", "live snapshot", "sensors" not qualified (M7) |
| C3 | "Evidence and trace on every answer" is not true for state answers or voice (M7) |
| C4 | "Nothing is deleted" while a cap exists (M7) |
| C5 | Hero diagram draws Recall → Bedrock; router arrows inverted (M6) |
| C6 | "Alexa+" integration with no stated validation on Alexa+ (M9) |
| C7 | Stale or absent test count (M10) |
| C8 | `DIAGRAM_FINAL_PACKAGE.md` process notes visible if published in the repo root (M11) |
| C9 | "Bilingual" with a Spanish-only dashboard TTS and Spanish-only deep dives (R1, R11) |

---

## 7. Table of Contents (ready to paste)

Place between the closing `</div>` of the header and the first `---`. Every anchor below was generated with the GitHub slug algorithm from the current headings and checked against them. If you rename `1. Hero` (R2), change `#1-hero` to `#1-overview`.

```markdown
## Contents

| | |
| --- | --- |
| **Understand** | [1. Overview](#1-hero) · [2. What is EchoMind](#2-what-is-echomind) · [3. Why it is different](#3-why-echomind-is-different) · [4. Core capabilities](#4-core-capabilities) |
| **Architecture** | [5. System architecture](#5-system-architecture) · [6. Memory reasoning pipeline](#6-memory-reasoning-pipeline) · [7. Query router](#7-query-router) · [8. Domain model](#8-domain-model) |
| **Integrations** | [9. Alexa+](#9-alexa-integration) · [10. AWS Builder](#10-aws-builder-integration) |
| **Run it** | [11. Getting started](#11-getting-started) · [12. Testing](#12-testing) |
| **Project** | [13. Status](#13-project-status) · [14. Roadmap](#14-roadmap) · [15. License](#15-license) |

> **Judges, 2-minute path:** [Overview](#1-hero) → [Query router](#7-query-router) → [Where Bedrock is, and is not](#10-aws-builder-integration) → [Getting started](#11-getting-started)
```

Slug table (computed): `1-hero`, `2-what-is-echomind`, `3-why-echomind-is-different`, `4-core-capabilities`, `5-system-architecture`, `6-memory-reasoning-pipeline`, `7-query-router`, `8-domain-model`, `9-alexa-integration`, `10-aws-builder-integration`, `11-getting-started`, `12-testing`, `13-project-status`, `14-roadmap`, `15-license`.

---

## 8. Preflight script (run inside the repo; resolves every [VERIFY-IN-REPO])

```bash
#!/usr/bin/env bash
# Run from the repository root. Read-only. Prints facts; edit nothing.
set -u

echo "== 1. Tracked files referenced by README =="
for f in README.md LICENSE hero.svg system-architecture.svg memory-reasoning.svg \
         query-router.svg domain-erd.svg alexa_skill/skill.json requirements.txt \
         Dockerfile docker-compose.yml src/domain/models/tools.py \
         ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md A7C_QUERY_ROUTER_ARCHITECTURE.md \
         scripts/alexa_mcp_simulator.py scripts/run_demo.py; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 && echo "tracked  $f" || echo "MISSING  $f"
done
git check-ignore -v .local/scripts/alexa_mcp_simulator.py 2>/dev/null

echo; echo "== 2. Domain imports infrastructure? (M8) =="
grep -rnE "^(from|import) (src\.)?(infrastructure|adapters)" src/domain || echo "none"

echo; echo "== 3. Where is the LLM port used? (Bedrock call sites, M5/M7) =="
grep -rn "LLMServicePort" src | grep -v "src/domain/ports" ; grep -rn "amazon.nova" src

echo; echo "== 4. Persistence of the memory store (M7) =="
grep -nE "json\.dump|sqlite|pickle|shelve|open\(.*['\"][wa]b?['\"]" \
  src/infrastructure/services/memory_service.py src/infrastructure/services/memory_bridge.py || echo "no file/db writes found"

echo; echo "== 5. Sensors: simulated or real? (M7) =="
grep -rn "SimulatedSensorBus\|SensorBus(" src/main.py src/infrastructure | head

echo; echo "== 6. Relation cap (M7) =="
grep -nE "MAX_|cap|64" src/domain/services/relation_rules.py | head

echo; echo "== 7. Router markers and language detection (M6b, R1, R9) =="
grep -nE "_PRESENT_MARKERS|_PAST_MARKERS|_STATE_SUBJECTS" -A8 src/domain/services/query_router.py | head -60
grep -n "lang" src/domain/services/query_router.py | head

echo; echo "== 8. Tool surface (R10) =="
grep -n "MEMORY_TOOL_NAMES" -A8 src/domain/models/tools.py

echo; echo "== 9. Test count (M10) =="
pytest --collect-only -q 2>/dev/null | tail -2

echo; echo "== 10. Secrets before moving scripts (§5) =="
grep -rnE "AKIA|aws_secret|AWS_SECRET|password|token|192\.168\." .local/scripts scripts 2>/dev/null || echo "none found"
git log --all --oneline -- .local | head -3
```

Then the manual cold-start test (10 min, fresh clone in an empty directory): install → start → seed → ask one present and one past question in Spanish and one in English → read `/metrics`. If any step needs a file that is not in the clone, the README is not ready.

---

## 9. Scoring rationale and re-audit gate

| Dimension | Weight | Score | Reason |
| --------- | :----: | :---: | ------ |
| Story and positioning | 20% | 8.5 | Clear thesis, explicit non-goals, honest Bedrock boundary |
| Technical accuracy | 25% | 5.5 | 12 technical + 8 architectural inconsistencies; Nova Micro contradiction |
| Navigation | 10% | 4 | No TOC; images not clickable; sections fine, anchors valid |
| Reproducibility / DX | 25% | 4.5 | Dead `.local` commands, no seed, no sample output, PowerShell only |
| Diagram quality | 10% | 5.5 | Content is detailed and mostly code-grounded, but 4 of 5 contain misleading arrows and text renders at 5.9–8.9 px |
| Evidence (tests, CI, demo) | 10% | 3.5 | No count, no CI, no output |
| **README score** | | **6.5** | |

**Hackathon readiness 6/10:** strong concept and honesty; weak on proof (no sample output, no Alexa+ validation statement, AWS contradiction).
**Open-source readiness 5/10:** unverifiable LICENSE/deep-dive files, ignored scripts, no CI/community files, Spanish-only deep dives, process notes in the repo.

**Re-audit gate (flip to READY FOR GITHUB PUBLICATION when all hold):**
1. M1–M11 done; §8 preflight shows no `MISSING` and no unexpected domain→infrastructure imports.
2. Cold-start test passes on a clean clone.
3. M5 verified with live AWS credentials (`fallbacks_activated: 0`) **or** the claim is narrowed to text-only.
4. M9 states precisely how Alexa+ was validated.
5. CI is green and the test count in the README matches `pytest --collect-only`.

*Sources for the one external fact used: [Amazon Nova Micro model card, AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html) (input modalities: text only; Converse API supported).*
