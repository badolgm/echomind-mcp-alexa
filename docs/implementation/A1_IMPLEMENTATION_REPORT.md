# A1_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A1 (Recall Engine Core)**
**Fecha:** 2026-10-17
**Plan ejecutado:** `PHASE_A_IMPLEMENTATION_PLAN.md` (paso 0 → 5)
**Alcance:** crear únicamente los 3 módulos de dominio + sus tests.
**No se hizo:** integración con `memory_converse`, A2, Recall Engine, commits, push.

---

## 1. Archivos creados

**7 archivos nuevos. 0 archivos existentes modificados, movidos ni eliminados.**

### 1.1 Código de producción (`src/domain/services/`)

| Archivo | Líneas | Contenido |
|---|---|---|
| `recall_plan.py` | 129 | Enums `RelationKind`, `RetrieveKind`, `Aggregation`, `Anchor`; dataclasses `TimeWindow`, `EntitySlot`, `RetrieveOp`, `RecallPlan`; `plan_to_dict()` |
| `evidence.py` | 168 | `Evidence` (+ `from_record`), `RecallTrace`, `RecallResult`; `render_utterance()`, `render_abstention()`, `format_relative_time()`, `truncate_snippet()` |
| `recall_planner.py` | 204 | `understand()` + helpers: `_detect_relations`, `_detect_anchor`, `_build_window`, `_build_entities`, `_build_ops` |

### 1.2 Tests (`tests/unit/`)

| Archivo | Líneas | Tests |
|---|---|---|
| `test_recall_plan.py` | 87 | 7 |
| `test_evidence.py` | 175 | 12 |
| `test_recall_planner.py` | 106 | 16 (con parametrizado) |
| `test_domain_purity.py` | 55 | 3 (guard de pureza) |

---

## 2. Tests añadidos — 38

### `test_recall_plan.py` (7)
`test_time_window_defaults` · `test_entities_and_ops_default_to_empty_tuple` · `test_plan_is_frozen_and_slot_sealed` · `test_plan_to_dict_is_json_safe` · `test_plan_to_dict_is_deterministic` · `test_retrieve_kind_values_are_stable` · `test_relation_kind_values_are_stable`

### `test_evidence.py` (12)
`test_evidence_frozen_with_optional_defaults` · `test_from_record_reads_detections_duck_typed` · `test_from_record_missing_fields_degrade` · `test_from_record_confidence_is_max` · `test_from_record_does_not_import_memory_record` · `test_render_abstention_bilingual` · `test_render_utterance_deterministic` · `test_render_utterance_never_invents` · `test_render_utterance_bilingual` · `test_format_relative_time_matches_v1_semantics` · `test_truncate_snippet_limit` · `test_recall_result_serializable`

### `test_recall_planner.py` (16)
`test_understand_ops_never_empty` · `test_understand_fallback_when_nothing_recognized` · `test_understand_respects_explicit_lang` · `test_understand_detects_lang_when_absent` · `test_understand_is_deterministic` · `test_understand_uses_injected_now` · `test_understand_relations_deduplicated` · `test_understand_empty_query_returns_fallback_plan` · `test_understand_reuses_public_classifier_api` · `test_understand_never_returns_none` · **`test_understand_four_target_cases`** (4 casos parametrizados) · **`test_understand_location_becomes_camera_or_zone`** (2 casos parametrizados)

### `test_domain_purity.py` (3)
`test_new_modules_import_only_stdlib_and_domain` · `test_no_time_or_network_calls_in_domain` · `test_required_future_import_present`

### Cobertura funcional de A1
| Requisito de aceptación | Test |
|---|---|
| Los 4 casos objetivo producen plan correcto | `test_understand_four_target_cases` |
| `plan.ops` nunca vacío | `test_understand_ops_never_empty` + `test_understand_empty_query_returns_fallback_plan` |
| Determinismo | `test_understand_is_deterministic`, `test_plan_to_dict_is_deterministic`, `test_render_utterance_deterministic` |
| Abstención / no inventar | `test_render_utterance_never_invents`, `test_render_abstention_bilingual` |
| Tiempo inyectado, sin reloj de pared | `test_understand_uses_injected_now`, `test_no_time_or_network_calls_in_domain` |
| Pureza del dominio (sin infra/IO/LLM) | `test_domain_purity.py` (3) |
| Sin import inverso V1→A1 | verificado en §4.2 |

---

## 3. Resultado pytest

### 3.1 Gates finales (los 3 comandos exigidos)

```powershell
# .venv\Scripts\python.exe -m pytest -q
246 passed in 5.37s

# .venv\Scripts\python.exe -m flake8 src tests
> OK — 0 violaciones  (max-line-length=88, extend-ignore=E203,W503)

# .venv\Scripts\python.exe -m black --check src tests --line-length 88
> 71 files would be left unchanged.
```

### 3.2 Resultado por tramo (gate tras cada paso, como dicta §11 del plan)

| Tramo | Comando | Resultado |
|---|---|---|
| Baseline (antes de A1) | `pytest -q` | **208 passed** (6.59s) |
| + 3 módulos de dominio | `pytest -q` | **208 passed** (5.36s) — nadie importa aún los nuevos |
| + 4 archivos de test | `pytest -q` | 15 failed → **corregidos los tests** (no el producto V1) |
| Cierre | `pytest -q` | **246 passed** (5.37s) |

### 3.3 Cuentas

| | |
|---|---|
| Tests preexistentes (V1) | **208 — todos verdes, sin editar ninguno** |
| Tests nuevos A1 | **38** |
| **Total** | **246 passed** |

---

## 4. Impacto cero sobre V1

### 4.1 Prueba por huella SHA-256
Antes de crear el primer archivo se capturó la huella de **los 70 archivos preexistentes** (`src/**`, `tests/**`, `alexa_skill/**`, `conftest.py`, `pytest.ini`, `setup.cfg`, `requirements.txt`). Al cerrar A1 se recomparó:

```
baseline entries compared: 70
changed = 0     missing = 0
```

> El artefacto temporal `A1_BASELINE.sha256` se **eliminó tras la verificación** para respetar la instrucción de crear *únicamente* los 3 módulos + tests.

### 4.2 Aislamiento probado (no sólo afirmado)
Búsqueda de imports de los módulos nuevos en todo `src/` y `tests/`:

- `recall_plan.py` → importado **sólo** por `recall_planner.py` (y tests).
- `evidence.py` → importado **sólo** por tests.
- **Ningún archivo V1 importa ninguno de los 3 nuevos.**
- Al revés: los nuevos **no** importan `memory_resolvers`, `memory_service`, `memory_bridge`, `tools`, `main`.

### 4.3 Superficies protegidas — sin cambios
| Superficie | Estado |
|---|---|
| `memory_converse` (resolver + respuestas literales) | ✅ intacto — `tests/unit/test_memory_converse.py` sigue pasando |
| `MemoryBridge` | ✅ intacto |
| `VectorMemoryService` | ✅ intacto |
| Dashboard (`src/static/dashboard.html`) | ✅ intacto |
| Android / Vivotek | ✅ intacto |
| `MEMORY_TOOL_NAMES`, `AGENTIC_TOOL_CATALOG` | ✅ sin tocar → `test_memory_resolvers.py:154` y `test_agent_tools.py` sin ajustes |
| `requirements.txt` | ✅ sin dependencias nuevas |

> **Nota sobre `git status`:** aparecen `M` en 6 ficheros (`requirements.txt`, `http_phone_camera_adapter.py`, `ambient_watch_service.py`, `main.py`, `dashboard.html`, `test_ambient_watch_service.py`). Son cambios **previos a A1, sin commitear**, del trabajo anterior. La huella §4.1 (capturada al arrancar A1) demuestra que **A1 no los tocó**.

### 4.4 Efectos no regresivos por construcción
- `slots=True` + `frozen=True` en todas las dataclasses → cero estado compartido.
- `now` se inyecta por parámetro → sin `time.time()`, tests paralelizables.
- Sin LLM → se conserva `assert fake_llm.calls == 0`.
- Sin `@skip`/`xfail`, sin editar `pytest.ini`, sin subir umbrales de `flake8`.

---

## 5. Desviaciones respecto al plan (documentadas)

| # | Plan decía | Implementado | Motivo |
|---|---|---|---|
| 1 | `RecallPlanner` como clase | función `understand()` + helpers de módulo | No hay estado en A1; evita clases vacías. La clase aparece en A2 si el engine necesita caché. |
| 2 | Nueva tabla `_AGGREGATION_PHRASES` | derivado de `MemoryIntent` público vía `_INTENT_AGGREGATION` | `MemoryIntentClassifier` ya conoce `EVENT_COUNT`/`SUMMARY`/`TOP_EVENTS`; añadir tabla duplicaría ese conocimiento. |
| 3 | `now = now or 0.0` (siempre) | `now: float \| None = None`; sólo si se inyecta se calcula `since`/`until` | Evita épocas negativas artificiales (`now=0.0 → since=-86400`) y mantiene el plan reproducible. |
| 4 | `RetrieveOp` sin `aggregation` | añadido `aggregation: Aggregation \| None` | Deja cada op autocontenido y ejecutable por el motor (A2) sin mirar el plan. |

**Desviaciones detectadas en ejecución y corregidas sobre el código nuevo (nunca sobre V1):**
- `RetrieveOp.location` quedaba **nunca poblado** → lo cableé en `_build_ops` (campo antes muerto).
- Añadí `cámara/camaras/donde` a la tabla de relaciones (el caso "qué mostraron las cámaras" no detectaba `CORRELATION`).

---

## 6. Limitaciones conocidas de A1 (para A2)

1. **`label`/`location` sólo se extraen en la rama `LAST_SEEN`** de `MemoryIntentClassifier` (`memory_intent.py:249-255`). En intenciones `SUMMARY`/`EVENT_COUNT`/`SEARCH` `RetrieveOp.entity` queda `None`.
   - **Causa raíz:** es comportamiento de V1, verificado en línea. **A1 no lo parcheó** para respetar "cero impacto sobre V1".
   - **Resolución:** refactor del clasificador en **A2** (extraer slots en todas las ramas) — ya es un cambio en V1, por lo que debe ir **junto a su test de regresión**, nunca en A1.
   - Prueba de que se resuelve con la API pública actual: `¿dónde estuvo la mascota en el patio por última vez?` → `('label','PET') + ('zone','patio')`.
2. **`format_relative_time` duplica los umbrales** de `memory_resolvers._relative_time` (`memory_resolvers.py:93`) porque éste es privado y vive en infraestructura, inaccesible desde dominio.
   - **Resolución (A3):** mover a helper de dominio y que V1 delegue; con test de equivalencia para garantizar salida idéntica.
3. **`RecallTrace.ops_executed` está preparado pero vacío** por diseño: A1 no ejecuta nada (el motor es A2). Se pobló en tests con `()`.

---

## 7. Checklist de aceptación de A1

| # | Criterio | Estado |
|---|---|---|
| 1 | 208 tests previos verdes, ninguno editado | ✅ `246 passed` incluye los 208 |
| 2 | Tests nuevos ≥ 232 (objetivo ≈240) | ✅ **246** (+38) |
| 3 | `flake8` limpio | ✅ 0 |
| 4 | `black` limpio | ✅ 71 unchanged |
| 5 | Cero archivos modificados | ✅ `changed=0 missing=0` sobre 70 |
| 6 | Cero dependencias nuevas | ✅ `requirements.txt` sin cambios |
| 7 | Pureza del dominio | ✅ `test_domain_purity.py` (3) |
| 8 | Los 4 casos objetivo → plan correcto | ✅ |
| 9 | `plan.ops` nunca vacío | ✅ |
| 10 | Determinismo | ✅ (planner, plan_to_dict, render) |
| 11 | Abstención sin inventar | ✅ |
| 12 | Tiempo inyectado, sin `time.time()` | ✅ |
| 13 | Sin LLM | ✅ |
| 14 | Salida V1 byte idéntica | ✅ intocada |
| 15 | Catálogo/tools V1 intactos | ✅ |
| 16 | Ningún import inverso V1→A1 | ✅ §4.2 |

**A1 → DoD cumplido.**

---

## 8. Siguiente paso (pendiente de tu aprobación)

Falta la decisión de **§13 de `ECHOMIND_V2_PHASE_A_RECALL_ENGINE.md`**, que A2 exige resolver antes de empezar:

- **Opción A (recomendada):** `memory_recall` corre **en paralelo** a `memory_converse` → cero riesgo, migración de `memory_converse` al engine se difiere a la **fase G** con garantía de salida idéntica.
- **Opción B:** migrar `memory_converse` al engine ya (pasa por V1 → mayor riesgo).

**A2 no empieza hasta recibir esa instrucción.**
