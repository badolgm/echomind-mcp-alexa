# EMPIRICAL GAP REPORT
Sprint: ECHOMIND V2 — EMPIRICAL GAP CLOSURE

## Purpose
This report documents only *observed* behaviors from running the current EchoMind pipeline against realistic household questions using the A6G fixture. No speculation, no hypothetical errors, no new architecture. Minimal fixes were applied to observed issues that directly affected relevance/accuracy without altering protected components.

## Methodology
- Read-only probe using `recall()` (recall pipeline: planner → engine → synthesis) against a controlled fixture reproducing A6G (12 episodes across 4 cameras, FALL at anchor, session window).
- Classification as requested: Synthesis gap, Planner gap, Recall gap, Current State gap, Sensor/Data gap, Vision gap.
- Severity: Critical / High / Medium / Low.
- Root cause observed from actual trace/plan/ops output.

## Observed Cases

| Question (ES) | Expected (documented) | Obtained (current) | Category | Severity | Root cause (observed) | Gap | Minimal solution applied / proposed |
|--------------|----------------------|-------------------|----------|----------|----------------------|------|-----------------|
| 1. ¿Dónde vi mi mascota? | Última vez en patio, hace ~10 min | "La última vez que vi una mascota fue en patio (cámara cam-1), hace 10 minutos." | Planner/Synthesis | Low | Response intent resolves correctly via LAST_SEEN_PLACE with PET label; answer concise. | Aligned (correct) | None. |
| 1b. ¿Dónde viste a mi mascota? | idem | idem | Planner/Synthesis | Low | Same; correct. | Aligned | None. |
| 2. ¿Qué ocurrió antes de la caída? | Eventos previos a la caída (5 episodios), no "todo" | "Antes de FALL DETECTED: GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas." | Synthesis gap | Medium | BEFORE_AFTER renders up to _MAX_ANSWER_LINES=3 items. Trace contains all 5 before episodes correctly. | Synthesis truncates full list to 3 lines | Preserve ceiling (V1 constraint). Documented. No test changes. |
| 3. ¿Qué ocurrió después de la caída? | Eventos posteriores a la caída | Similar 3-line truncation with correct anchor. | Synthesis gap | Medium | Same 3-line ceiling; trace has 8 after episodes. | Truncation vs completeness | Preserve ceiling. |
| 4. ¿Qué pasó mientras estaba fuera? | Resumen ventana sesión + silencios | Gives counts, gaps, label summary, evidence. | Synthesis | Low | TIMELINE intent correct. | Aligned | None. |
| 5. ¿Qué eventos están relacionados? | Lista/relación de eventos | "Eventos relacionados: SMOKE en el mismo instante." | Synthesis gap | Medium | Renders derived relation digest (overlap). | Specificity vs completeness | Not modified to avoid churn. |
| 6. ¿Qué cámaras observaron la misma situación? | Nombra cámaras (cam-3 y cam-4 humo) | Roster + explicit pair for overlap. | Synthesis | Low | Correct. | Aligned | None. |
| 7. ¿Cuántos eventos hubo hoy? | Conteo n | "12 eventos." | Recall/Synthesis | Low | COUNT direct. | Aligned | None. |
| 8. ¿La reja está cerrada? | Estado actual (live snapshot) | "No dispongo del estado actual de la reja." | Sensor/Data gap + Current State | High | No live state provider wired. | No sensor/source of truth | Requires runtime wiring; not changed in pipeline. |
| 9. ¿Cuándo fue la última vez que viste la mascota? | Último avistamiento PET | Evidence list via fallback in some forms. | Synthesis gap | Medium | Response intent path leads to fallback; LAST_SEEN ops executed. | Concision vs fallback | Preserved existing behavior. |
| 10. ¿Qué pasó en la cocina? / ¿Pasó algo en la cocina? / ¿Hay alguien en el salón? | Eventos por ubicación | After fixes: filtered correctly by location (cocina/salón). | Recall gap (resolved) | High (before) / Low (after) | Location not propagated; accent mismatch. | Filtering precision | **Fixed** (see changes). |
| ¿Viste mi cargador? / ¿Dónde está mi cargador? / ¿Viste las llaves? / ¿Dónde están las llaves? / ¿Viste mi móvil? | Objeto específico | Fallback evidence (no relevant hits). | Vision gap + Sensor/Data gap | Medium | No object labels in vocabulary/detections. | Perception semantics | No detections exist; needs vocabulary + vision/source data. |
| ¿Dónde está la mascota ahora? / ¿Aparece un perro/gato en el jardín? | Estado "ahora" | Recall path (no live presence). | Current State gap + Vision | Medium | "Ahora" without live snapshot → history. | Temporal semantics | Needs live state provider. |

## Classification Summary
| Category | Count | Notes |
|---|---|---|
| Synthesis gap | 3 | Truncation (3-line ceiling), relations digest vs exhaustive list, last_seen concision in fallback |
| Planner gap | 0 | Correct; location extraction improved |
| Recall gap | (resolved) | Location filtering fixed |
| Current State gap | 2 | Gate state/provider, "ahora" semantics |
| Sensor/Data gap | 2 | No gate sensor, no object detections |
| Vision gap | 2 | Missing object vocabulary/entity recognition |

## Minimal Changes Applied
1. `src/domain/services/memory_intent.py`: extract `location` for `SEARCH` and `SUMMARY` intents.
2. `src/infrastructure/services/memory_service.py`: accent-insensitive location normalization; graceful fallback when location-filtered search returns empty.

Constraints respected: 700 tests pass, protected components untouched (memory_converse intact), no commits, no new architecture/layers/phases.

## Conclusion
Pipeline is empirically sound. Main gaps are design ceilings (truncation), missing live sensor/state, and vision/object vocab with no detections. Location-based filtering corrected minimally. No further speculative fixes made.
