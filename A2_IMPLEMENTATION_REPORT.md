# A2_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A2 (Recupera y relaciona)**
**Fecha:** 2026-10-17
**Decisión aplicada:** **Opción A — `memory_recall` en paralelo a `memory_converse`.**
**Alcance:** `records_between()` + `memory_timeline.py` + `recall_engine.py` + tests.
**No se hizo:** integración con Voice Dock / Dashboard / MCP, reemplazo de V1, commits, push.

---

## 1. Archivos creados y modificado

### 1.1 Modificado (1 — único cambio de archivo existente autorizado)

| Archivo | Cambio | Líneas añadidas |
|---|---|---|
| `src/infrastructure/services/memory_service.py` | **`records_between()`** — método **puroamente aditivo**. No toca ningún método, atributo ni el store existente. | +28 |

```python
def records_between(
    self,
    since: float | None = None,
    until: float | None = None,
    *,
    location: str | None = None,
    risk: str | None = None,
) -> list[MemoryRecord]:
```
- Bounds `None` = sin límite en ese lado; inclusivos (`>=` / `<=`).
- Orden **cronológico ascendente**, desempate por `id` → timeline estable.
- Filtro `risk` case-insensitive (misma semántica que `count_events`).
- **No muta el store** (verificado por test).

### 1.2 Nuevos (2 en producción)

| Archivo | Líneas | Contenido |
|---|---|---|
| `src/infrastructure/services/memory_timeline.py` | 135 | `Episode`, `TimelineGap`, `build_episodes()`, `timeline_gaps()`, `episodes_before()`, `episode_key()`, `labels_of()` |
| `src/infrastructure/services/recall_engine.py` | 295 | `RecallEngine.execute()` → **retrieve → relate → synthesize**; `ENGINE_NAME`, `ENGINE_VERSION` |

### 1.3 Nuevos (3 tests)

| Archivo | Líneas | Tests |
|---|---|---|
| `tests/unit/test_memory_records_between.py` | — | 12 |
| `tests/unit/test_memory_timeline.py` | — | 19 |
| `tests/unit/test_recall_engine.py` | — | 24 |

---

## 2. Tests añadidos — 55

### `test_memory_records_between.py` (12)
`test_records_between_filters_window` · `test_records_between_window_bounds_are_inclusive` · `test_records_between_unbounded_when_none` · `test_records_between_only_since` · `test_records_between_only_until` · `test_records_between_orders_ascending` · `test_records_between_filters_location` · `test_records_between_filters_risk_case_insensitive` · `test_records_between_returns_empty_outside_window` · `test_records_between_is_deterministic_on_equal_timestamps` · `test_records_between_empty_store` · `test_records_between_does_not_mutate_the_store`

### `test_memory_timeline.py` (19)
`test_episode_key_is_location_and_sorted_labels` · `test_episode_key_differs_on_location` · `test_labels_of_is_sorted_and_stringified` · `test_build_episodes_empty_input` · `test_build_episodes_orders_ascending` · `test_build_episodes_coalesces_within_gap` · `test_build_episodes_splits_when_gap_exceeded` · `test_build_episodes_splits_on_different_location` · `test_build_episodes_splits_on_different_labels` · `test_episode_labels_are_union_and_sorted` · `test_episode_risk_is_the_highest_severity` · `test_episode_count_and_duration` · `test_build_episodes_is_deterministic` · `test_timeline_gaps_detects_silences` · `test_timeline_gaps_ignores_short_silences` · `test_timeline_gaps_single_episode_is_empty` · `test_episodes_before_filters_by_target` · `test_episodes_before_all_after_target_is_empty` · `test_episode_is_frozen`

### `test_recall_engine.py` (24)
`test_engine_exposes_identity` · `test_execute_returns_recall_result` · **`test_execute_abstains_when_memory_is_empty`** · `test_execute_with_no_ops_abstains` · `test_execute_is_deterministic` · `test_execute_last_seen_returns_most_recent_match` · `test_execute_range_respects_the_window` · `test_execute_search_returns_matching_evidence` · `test_execute_trace_records_every_operation` · `test_execute_trace_evidence_ids_match_evidence` · `test_execute_dedupes_records_across_operations` · `test_execute_orders_evidence_chronologically` · **`test_execute_timeline_relation_exposes_episodes_and_gaps`** · **`test_execute_before_after_limits_episodes_to_the_target`** · **`test_execute_spatial_relation_groups_and_flags_degradation`** · `test_execute_correlation_relation_groups_by_location` · **`test_execute_session_start_anchor_uses_the_injected_anchor`** · `test_execute_session_start_without_anchor_degrades_to_unbounded` · `test_execute_count_aggregation_exposes_the_value` · `test_execute_summary_aggregation_exposes_label_counts` · `test_execute_current_state_reports_unavailable` · `test_execute_needs_only_the_memory_store` · **`test_execute_full_pipeline_from_a_natural_query`** · `test_execute_does_not_mutate_the_store`

### Cobertura funcional de A2
| Requisito | Test |
|---|---|
| `Range(window)` → ventana arbitraria | `test_execute_range_respects_the_window` |
| Episodios reconstituibles (gap 30 s, `(location, labels)`) | `test_build_episodes_*` |
| Silencios del timeline | `test_timeline_gaps_detects_silences` |
| `before(target)` (base) | `test_execute_before_after_limits_episodes_to_the_target` |
| Ancla de sesión | `test_execute_session_start_anchor_uses_the_injected_anchor` |
| Degradación honesta (sin inventar) | `test_execute_abstains_when_memory_is_empty`, `test_execute_spatial_relation_groups_and_flags_degradation` |
| Determinismo | `test_execute_is_deterministic`, `test_build_episodes_is_deterministic` |
| LLM-free | `test_execute_needs_only_the_memory_store` |
| Composición A1+A2 | `test_execute_full_pipeline_from_a_natural_query` |

---

## 3. Gates

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `.venv\Scripts\python.exe -m pytest -q` | **301 passed** |
| Lint | `.venv\Scripts\python.exe -m flake8 src tests` | **0 violaciones** |
| Formato | `.venv\Scripts\python.exe -m black --check src tests --line-length 88` | **76 files unchanged** |
| Dependencias nuevas | `requirements.txt` | **ninguna** |

---

## 4. Resultado pytest

```
301 passed in 6.91s
```

| | Tests | Total |
|---|---|---|
| Baseline V1+A1 (antes de A2) | 246 | 246 |
| Nuevos A2 | +55 | — |
| **Total** | | **301** |

**0 regresiones:** los 246 preexistentes siguen verdes y **ninguno fue editado**.

---

## 5. Prueba de impacto cero sobre V1

### 5.1 Huella SHA-256 (antes/después)
Se capturó la huella de **los 77 archivos existentes** (`src/**`, `tests/**`, `alexa_skill/**`, `conftest.py`, `pytest.ini`, `setup.cfg`, `requirements.txt`) **antes** de crear el primer archivo de A2, y se recomparó al cerrar:

```
changed/missing: 1
CHANGED: src\infrastructure\services\memory_service.py      ← único cambio autorizado
```

> El artefacto `A2_BASELINE.sha256` se **eliminó tras la verificación** para no dejar ficheros fuera del alcance pedido.

### 5.2 Un solo archivo tocado, y es el autorizado
`memory_service.py` cambió **únicamente** por la adición de `records_between()`. Ningún método existente, ningún campo de `MemoryRecord` y ninguna constante fue alterado.

### 5.3 Aislamiento probado
Búsqueda de referencias en **todo** `src/`:
- `recall_engine` → importado por **nadie** (nadie lo invoca todavía).
- `memory_timeline` → importado **sólo** por `recall_engine.py`.
- `records_between` → llamado **sólo** por `recall_engine.py`.
- **Ningún archivo V1 importa los nuevos módulos.**

### 5.4 Superficies protegidas
| Superficie | Estado |
|---|---|
| `memory_converse` (texto literal de salida) | ✅ intacto |
| `MemoryBridge` | ✅ intacto |
| `VectorMemoryService` (métodos existentes) | ✅ intactos — sólo +1 método nuevo |
| Dashboard (`src/static/dashboard.html`) | ✅ intacto |
| Android / Vivotek | ✅ intacto |
| `MEMORY_TOOL_NAMES`, `AGENTIC_TOOL_CATALOG`, `tools.py` | ✅ sin tocar |
| `main.py`, `memory_resolvers.py`, `tool_resolvers.py` | ✅ sin tocar |
| `requirements.txt` | ✅ sin dependencias nuevas |

> **Nota sobre `git status`:** los `M` en `requirements.txt`, `http_phone_camera_adapter.py`, `ambient_watch_service.py`, `main.py`, `dashboard.html` y `test_ambient_watch_service.py` son cambios **previos a A2, sin commitear**. La huella §5.1 (capturada al arrancar A2) demuestra que **A2 no los tocó**.

### 5.5 Canal paralelo confirmado (Opción A)
El engine **no** está cableado a `memory_converse`, a `/api/converse`, al Voice Dock ni al Dashboard. Es un segundo camino, inerte hasta A3, que añade el tool `memory_recall` **sin reemplazar nada**.

---

## 6. Qué implementa el engine

| Etapa | Implementación |
|---|---|
| **retrieve** | Dispatch por `RetrieveKind` → `last_seen` / `search_memory` / `records_between` / `top_events`·`recent_*` / `label_counts`·`count_occurrences`·`count_events` |
| **relate** | `EPISODE` → episodios · `TIMELINE` → episodios + silencios · `BEFORE_AFTER` → episodios hasta `until` · `SPATIAL`/`CORRELATION` → agrupación por `location` (**degradada y marcada `degraded: true`**) |
| **synthesize** | `render_utterance(evidence, lang, now)` de A1 → redacción **condicionada a la evidencia recuperada**, no al intent. Evidencia vacía ⇒ **abstención**. |
| **trace** | `ops_executed` = una entrada por op (`op`, `filters`, `returned_ids`, `count`) + una entrada por relación. `RecallTrace` serializable. |

---

## 7. Desviaciones y limitaciones (documentadas, sin tocar V1)

| # | Punto | Decisión |
|---|---|---|
| 1 | `RetrieveOp.entity` (label) no filtraba en `Range` | Lo filtré **en el engine** (`_has_label`), no ampliando `records_between` → la ventana queda como lectura pura de tiempo, la semántica vive en el engine. |
| 2 | `SPATIAL`/`CORRELATION` agrupan por `location` | `camera_id`/`zone` son **A4**. El trace marca `degraded: true` + `reason` → **degradación honesta**, no respuesta inventada (caso 4 del diseño). |
| 3 | `CURRENT_STATE` → `status: unavailable` | Requiere cablear `AmbientWatchService` (fuera del alcance de 3 ficheros de A2). Abstiene en vez de fingir. |
| 4 | `episodes_before()` | Implementado como **filtro base**; la segmentación completa de `before()` es **fase B/C** (diseño §6). |
| 5 | `session_start` es **parámetro inyectado** | El registro del ancla al abrir sesión MCP es **A3/C**; sin él, la ventana degrada a sin límite inferior. |
| 6 | Narración de `COUNT` | El valor del conteo va al **trace** (`entry["value"]`); la redacción plena de agregados es **fase B** (diseño §10). |
| 7 | `Episode` no persiste `episode_id` | Los episodios se **reconstruyen** desde el store (no desde RAM). Persistir `episode_id` es **fase C**. |

---

## 8. Incidente durante el desarrollo (resuelto, sin daño)

En un gate de formato pasé `src` completo a `black` en lugar de sólo los ficheros nuevos. **Comprobado inmediatamente por huella SHA-256:** sólo cambió `memory_service.py` (autorizado) → **ningún fichero V1 fue reformateado**. A partir de ahí los gates de formato se ejecutan con `--check` (sólo lectura).

---

## 9. Criterios de aceptación de A2

| # | Criterio | Estado |
|---|---|---|
| 1 | 246 tests previos verdes, ninguno editado | ✅ **301 passed** incluye los 246 |
| 2 | `records_between()` implementado y aditivo | ✅ +28 líneas, 12 tests |
| 3 | `memory_timeline.py` implementado | ✅ episodios + silencios + before |
| 4 | `recall_engine.py` implementado | ✅ retrieve → relate → synthesize |
| 5 | `flake8` limpio | ✅ 0 |
| 6 | `black` limpio | ✅ 76 unchanged |
| 7 | Cero cambios fuera de lo autorizado | ✅ `changed=1` (sólo `memory_service.py`) |
| 8 | Cero dependencias nuevas | ✅ |
| 9 | Determinismo | ✅ |
| 10 | Sin LLM | ✅ |
| 11 | Abstención sin inventar | ✅ |
| 12 | V1 sin cablear al engine (canal paralelo) | ✅ |

**A2 → DoD cumplido.**

---

## 10. Siguiente paso: A3 (pendiente de tu aprobación)

A3 haría **visible** el canal paralelo, y es el único tramo que sí toca ficheros V1 (lista cerrada, +1 rama):

| Fichero | Cambio | Riesgo |
|---|---|---|
| `src/domain/models/tools.py` | + `MEMORY_RECALL` al catálogo | bajo |
| `src/infrastructure/adapters/mcp/memory_resolvers.py` | + `"memory_recall"` en `MEMORY_TOOL_NAMES` **y** rama en `build_memory_resolver` | **obligatorio hacer ambos a la vez** (`test_memory_resolvers.py:154`) |
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | **nuevo** — `build_memory_recall_resolver(engine)` | nulo |
| `src/main.py` | + `/api/recall` | bajo |
| tests | nuevos | nulo |

**Confirmar para iniciar A3**, o indicar si prefieres revisar primero el código de A2.
