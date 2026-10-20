# A3_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A3 (Canal paralelo visible)**
**Fecha:** 2026-10-18
**Decisión aplicada:** **`memory_recall` es experimental y coexiste; `memory_converse` sigue siendo el camino principal.**
**Alcance:** `MEMORY_RECALL` tool + `recall_resolvers.py` + `/api/recall` + tests.
**No se hizo:** migración de `memory_converse`, commits, push.

---

## 1. Archivos creados y modificados

### 1.1 Creados (3)

| Archivo | Líneas | Contenido |
|---|---|---|
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | 129 | `recall()`, `recall_result_payload()`, `build_memory_recall_resolver()` |
| `tests/unit/test_recall_resolvers.py` | 260 | 33 tests |
| `tests/integration/test_recall_api_route.py` | 134 | 5 tests |

### 1.2 Modificados (3 — lista cerrada y autorizada)

| Archivo | Cambio | Diff |
|---|---|---|
| `src/domain/models/tools.py` | `MEMORY_RECALL` (`AgentTool`) + entrada en `AGENTIC_TOOL_CATALOG` | +30 / −0 |
| `src/infrastructure/adapters/mcp/memory_resolvers.py` | `"memory_recall"` en `MEMORY_TOOL_NAMES` + rama de dispatch en `build_memory_resolver` | +16 / −1 |
| `src/main.py` | import de `recall`/`recall_result_payload`, `RecallRequest`, ruta `POST /api/recall` | +27 / −0 |

> El diff de `main.py` en git (50 líneas) **incluye cambios sin commitear previos a A3** (cámaras Vivotek/phone y sus rutas). Las líneas **propias de A3** son sólo el import, `RecallRequest` y `/api/recall`; ver §5.4.

---

## 2. Tests añadidos — 38

### `tests/unit/test_recall_resolvers.py` (33)
`test_memory_recall_tool_is_in_the_catalog_and_tool_names` · `test_memory_recall_declares_query_as_required` · `test_memory_recall_dispatch_routes_to_the_recall_engine` · `test_memory_recall_resolver_requires_query` · `test_memory_recall_answers_from_memory_with_evidence` · `test_memory_recall_abstains_on_an_empty_store` · **`test_memory_recall_is_llm_free_through_the_registry`** · `test_memory_recall_is_listed_by_the_tool_registry` · **`test_memory_recall_does_not_replace_memory_converse`** · `test_memory_recall_is_injected_now_is_wall_clock_independent` · `test_memory_recall_honours_explicit_english` · `test_recall_function_is_deterministic_and_llm_free` · `test_recall_result_payload_is_json_safe` · `test_recall_result_payload_exposes_engine_evidence_and_trace` · `test_recall_result_payload_reports_abstention_without_evidence` · **`test_v1_relative_time_matches_the_domain_helper`** (parametrizado × 18 deltas)

### `tests/integration/test_recall_api_route.py` (5)
`test_recall_api_requires_query` · `test_recall_api_abstains_before_any_seed` · **`test_recall_api_returns_evidence_and_trace_after_seeding`** · `test_recall_api_honours_session_start_anchor` · **`test_converse_and_recall_coexist_on_the_same_app`**

### Cobertura funcional de A3
| Requisito | Test |
|---|---|
| Tool en catálogo **y** en `MEMORY_TOOL_NAMES` | `test_memory_recall_tool_is_in_the_catalog_and_tool_names` |
| Rama de dispatch (sin `KeyError`) | `test_memory_recall_dispatch_routes_to_the_recall_engine` |
| Punta a punta: `understand → engine → narración` | `test_memory_recall_answers_from_memory_with_evidence` |
| Abstención sin inventar | `test_memory_recall_abstains_on_an_empty_store` |
| Sin LLM | `test_memory_recall_is_llm_free_through_the_registry` |
| **Coexistencia sin reemplazo** | `test_memory_recall_does_not_replace_memory_converse` |
| `/api/recall` con evidencia real (seed demo) | `test_recall_api_returns_evidence_and_trace_after_seeding` |
| **V1 intacto byte a byte por HTTP** | `test_converse_and_recall_coexist_on_the_same_app` |
| Determinismo / reloj inyectado | `test_memory_recall_is_injected_now_is_wall_clock_independent` |

---

## 3. Gates

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `.venv\Scripts\python.exe -m pytest -q` | **339 passed** |
| Lint | `.venv\Scripts\python.exe -m flake8 src tests` | **0 violaciones** |
| Formato | `.venv\Scripts\python.exe -m black --check src tests --line-length 88` | **79 files unchanged** |
| Dependencias nuevas | `requirements.txt` | **ninguna** |

---

## 4. Resultado pytest

```
339 passed in 9.86s
```

| | Tests | Total |
|---|---|---|
| Baseline V1+A1+A2 (antes de A3) | 301 | 301 |
| Nuevos A3 | +38 | — |
| **Total** | | **339** |

**0 regresiones:** los 301 preexistentes siguen verdes y **ninguno de ellos fue editado**.

---

## 5. Impacto sobre V1

### 5.1 Huella SHA-256 (antes/después)
Se capturó la huella de los **78 archivos existentes** antes de crear el primer archivo de A3 y se recomparó al cerrar:

```
changed/missing: 3
CHANGED: src\domain\models\tools.py
CHANGED: src\infrastructure\adapters\mcp\memory_resolvers.py
CHANGED: src\main.py
```

**Exactamente los 3 ficheros autorizados.** Cero `MISSING`. El artefacto `A3_BASELINE.sha256` se **eliminó tras la verificación**.

> El `black` de esta fase se ejecutó **sólo sobre ficheros nuevos** (`--check` en el gate global). El único archivo reescrito por formato fue `recall_resolvers.py`, que es nuevo.

### 5.2 `memory_converse` intacto
El cuerpo de `build_memory_converse_resolver` **no cambió**. En `memory_resolvers.py` sólo se añadieron:
- `"memory_recall"` al `frozenset` `MEMORY_TOOL_NAMES` (suma de nombre, sin alterar los existentes).
- Una rama `if tool_name == "memory_recall":` **después** de la rama de `memory_converse`, con **import local** para no tocar el grafo de imports de V1.

Prueba executable: `test_converse_and_recall_coexist_on_the_same_app` exige por HTTP que `/api/converse` siga devolviendo **literalmente** `"La última detección de una mascota ocurrió hace 6 días en patio."`, y el test V1 preexistente `tests/integration/test_memory_api_routes.py` (sin editar) sigue verde.

### 5.3 Superficies protegidas
| Superficie | Estado |
|---|---|
| `memory_converse` (texto literal) | ✅ intacto |
| `MemoryBridge` | ✅ intacto |
| Dashboard / Android / Vivotek / Voice Dock | ✅ intactos (fuera de la lista de 3) |
| `/api/converse`, `/api/demo/seed` | ✅ intactos |
| `MEMORY_TOOL_NAMES` existentes, catálogo, `tool_resolvers.py` | ✅ aditivo |
| `pytest.ini`, `setup.cfg`, `requirements.txt` | ✅ intactos |

### 5.4 Cambios de A3 en `main.py` (aislados)
```
+from src.infrastructure.adapters.mcp.recall_resolvers import (
+    recall,
+    recall_result_payload,
+)
+class RecallRequest(BaseModel):
+    query: str
+    lang: str | None = None
+    session_start: float | None = None
+    @app.post("/api/recall")
+    async def post_recall(payload: RecallRequest) -> dict[str, object]:
```
Puro añadido. `post_converse` no se tocó.

### 5.5 Canal paralelo confirmado
`memory_recall` es **experimental e inerte**: sólo responde cuando un llamante lo pide explícitamente por nombre. No hay conmutador, ni flag, ni reescritura del camino V1. La migración sigue quedando para la **fase G**.

---

## 6. Qué expone el canal nuevo

| Superficie | Salida |
|---|---|
| MCP `memory_recall` | narración + `evidencia:` (ids, labels, location, riesgo) + `trace: lang=… ops=…` |
| `POST /api/recall` | JSON: `response`, `is_error`, `lang`, `engine{name,version}`, `evidence[]`, `trace{plan, ops, evidence_ids}` |

La diferencia con `memory_converse` es deliberada y es el motivo de la fase: **trazabilidad**. Cada respuesta expone `plan + evidence + trace`, y **abstiene** cuando no hay evidencia.

---

## 7. Desviaciones y limitaciones (documentadas, sin tocar V1)

| # | Punto | Decisión |
|---|---|---|
| 1 | Unificación de `_relative_time` (plan A1 §5.4) | **No se delegó en V1.** En su lugar se añadió `test_v1_relative_time_matches_the_domain_helper`, que fija la equivalencia byte a byte entre `memory_resolvers._relative_time` y el helper de dominio `format_relative_time` sobre 18 deltas × 2 idiomas. La delegación queda **desbloqueada y probada**, pero sin tocar V1. |
| 2 | `search` no respeta la ventana temporal | El op `search` busca sobre todo el store (comportamiento heredado de A2). El trace **sí** registra `filters.since/until`, pero los resultados no se recortan por tiempo. Limitación conocida; corregirla alteraría A2 y queda fuera de A3. |
| 3 | `session_start` llega por payload, no del `SessionManager` | El ancla de sesión real (al abrir MCP) es **fase C**. A3 la expone como campo opcional para que el camino sea usable y testeable ya. |
| 4 | `CURRENT_STATE` sigue sin resolverse | Requiere `AmbientWatchService`; sigue degradando a `status: unavailable` con abstención. |
| 5 | Narración de `COUNT` | El valor va al `trace`; la redacción plena es **fase B**. |

---

## 8. Criterios de aceptación de A3

| # | Criterio | Estado |
|---|---|---|
| 1 | 301 tests previos verdes, ninguno editado | ✅ **339 passed** |
| 2 | `MEMORY_RECALL` en catálogo **y** en `MEMORY_TOOL_NAMES` | ✅ añadidos a la vez (regla obligatoria) |
| 3 | `recall_resolvers.py` creado | ✅ 129 líneas, LLM-free |
| 4 | `/api/recall` creado | ✅ con evidencia y trace |
| 5 | `memory_converse` no reemplazado | ✅ literal V1 verificado por HTTP |
| 6 | Cero cambios fuera de los 3 autorizados | ✅ `changed=3` |
| 7 | `flake8` / `black` limpios | ✅ / ✅ |
| 8 | Sin dependencias nuevas, sin commits, sin push | ✅ |

**A3 → DoD cumplido.**

---

## 9. Siguiente paso: A4 (pendiente de aprobación)

A4 añade la dimensión espacial sin tocar V1:

| Entrega | Detalle |
|---|---|
| `src/domain/services/memory_spatial.py` | nuevo, puro |
| `MemoryRecord` + `camera_id`/`zone` | campos **opcionales con default** (`frozen(slots=True)` compatible; construcciones por keyword siguen válidas) |
| degradación | con `camera_id=None` el engine agrupa por `location`, como hoy |

Es el primer paso que **añade campos a `MemoryRecord`**; se verificará por huella que toda construcción existente (`memory_bridge.py`, `demo_seed_service.py`, tests) sigue funcionando sin cambios.

**Confirmar para iniciar A4.**
