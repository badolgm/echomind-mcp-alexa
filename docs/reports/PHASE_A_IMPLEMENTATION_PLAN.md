# PHASE_A_IMPLEMENTATION_PLAN.md

**Sprint:** ECHOMIND V2 PHASE A — **A1 (Recall Engine Core, síntesis pura)**
**Tipo:** Plan de implementación completo (**NO se implementa; sin commits; sin push**)
**Fecha:** 2026-10-17
**Base aprobada:** `ECHOMIND_V2_PHASE_A_RECALL_ENGINE.md`
**Baseline verificado en esta máquina:** `pytest -q` → **`208 passed in 6.59s`**

---

## 1. Estructura exacta de carpetas

A1 **solo crea archivos**. Ningún archivo existente se modifica, mueve ni elimina.

```
src/domain/                              # paquete puro (nunca importa FastAPI/boto3/MCP/IO)
├── __init__.py                          = SIN CAMBIOS (declara la regla de pureza)
└── services/
    ├── __init__.py                      = SIN CAMBIOS (solo docstring)
    ├── memory_intent.py                 = SIN CAMBIOS  ◀─ se importa (léctura, no escritura)
    ├── recall_plan.py                   ★ NUEVO  (value objects del plan)
    ├── recall_planner.py                ★ NUEVO  (understand → RecallPlan)
    └── evidence.py                      ★ NUEVO  (Evidence + narrativa determinista)

tests/                                   # testpaths=tests (pytest.ini)
├── conftest.py                          = SIN CAMBIOS
└── unit/
    ├── test_recall_plan.py              ★ NUEVO
    ├── test_recall_planner.py           ★ NUEVO
    ├── test_evidence.py                 ★ NUEVO
    └── test_domain_purity.py            ★ NUEVO (guard de la regla de dependencias)
```

**Resto del árbol: SIN CAMBIOS** (lista cerrada en §8.1).

> **Nota A2 (no ahora):** `src/infrastructure/services/` **no** tiene `__init__.py` (paquete de nombres) — los futuros `recall_engine.py`, `memory_timeline.py`, `memory_spatial.py` se insertan ahí sin tocar nada.

**Total A1:** 3 módulos nuevos de dominio + 4 archivos de test. **0 archivos modificados.**

---

## 2. Contratos públicos

### 2.1 Convenciones obligatorias (extraídas del código real)

| Convención | Referencia |
|---|---|
| `from __future__ import annotations` en todo módulo | `memory_intent.py:9`, `memory_service.py:12` |
| Dataclasses `@dataclass(frozen=True, slots=True)` | `memory_intent.py:28`, `memory_service.py:25`, `tools.py:43` |
| `Enum` plano con `.value` de texto | `MemoryIntentType`, `ToolCategory`, `Modality` |
| Tipos modernos `X \| None`, `tuple[...]` | todo el repo |
| Imports **absolutos** `from src.…` | todo el repo |
| Dominio = **stdlib únicamente** (sin excepción) | `src/domain/__init__.py` |
| Línea máx. **88** (black + flake8) | `setup.cfg` (`extend-ignore = E203, W503`), CLI `--line-length 88` |
| `asyncio_mode = auto` → marcador opcional | `pytest.ini:3` |
| Raíz en `sys.path` vía `conftest.py` | `conftest.py` |

### 2.2 Contratos públicos nuevos (A1)

```python
# src/domain/services/recall_plan.py
class RelationKind(Enum): ...        # EPISODE|SPATIAL|CORRELATION|TIMELINE|BEFORE_AFTER
class RetrieveKind(Enum): ...        # LAST_SEEN|SEARCH|RANGE|TOP|AGGREGATE|CURRENT_STATE
class Aggregation(Enum): ...         # COUNT|LIST|SUMMARY
class Anchor(Enum): ...              # NOW|SESSION_START|EXPLICIT

@dataclass(frozen=True, slots=True) class TimeWindow: ...
@dataclass(frozen=True, slots=True) class EntitySlot: ...
@dataclass(frozen=True, slots=True) class RetrieveOp: ...
@dataclass(frozen=True, slots=True) class RecallPlan: ...

def plan_to_dict(plan: RecallPlan) -> dict[str, object]: ...

# src/domain/services/evidence.py
@dataclass(frozen=True, slots=True) class Evidence: ...
@dataclass(frozen=True, slots=True) class RecallTrace: ...
@dataclass(frozen=True, slots=True) class RecallResult: ...

def render_utterance(evidence, *, lang: str, now: float) -> str: ...
def render_abstention(*, lang: str) -> str: ...
def format_relative_time(ts: float, now: float, lang: str = "es") -> str: ...
def truncate_snippet(text: str, limit: int = 120) -> str: ...

# src/domain/services/recall_planner.py
def understand(text: str, lang: str | None = None, *, now: float | None = None) -> RecallPlan: ...
def _detect_lang(text: str, lang: str | None) -> str: ...   # privado
```

### 2.3 Invariantes que A1 garantiza
1. **No hay dependencia hacia infraestructura**: `recall_planner` solo importa de `src.domain…` y stdlib (verificado por `test_domain_purity.py`).
2. **Sin IO, sin red, sin `time.time()` en el núcleo** — el tiempo entra por parámetro `now` (inyección) → determinismo.
3. **Sin LLM.** (mantiene `fake_llm.calls == 0`).
4. **Todo inmutable** (`frozen`) → sin estado compartido, sin efectos de orden.

### 2.4 Contratos V1 **prohibidos de tocar**
```
memory_resolvers.MEMORY_TOOL_NAMES      build_memory_converse_resolver
memory_resolvers.build_memory_resolver  memory_service.MemoryRecord (firmas)
memory_service.VectorMemoryService      tools.AGENTIC_TOOL_CATALOG
memory_bridge.MemoryBridge              main.mount_memory_api_routes (/api/converse)
```

---

## 3. Clases nuevas (catálogo completo)

| Clase | Módulo | Kind | Propósito |
|---|---|---|---|
| `RelationKind` | `recall_plan.py` | Enum | Tipo de relación a aplicar en `relate` |
| `RetrieveKind` | `recall_plan.py` | Enum | Tipo de operación de recuperación |
| `Aggregation` | `recall_plan.py` | Enum | Agregación solicitada (count/list/summary) |
| `Anchor` | `recall_plan.py` | Enum | Ancla temporal (now/session_start/explicit) |
| `TimeWindow` | `recall_plan.py` | dataclass | Ventana temporal del plan |
| `EntitySlot` | `recall_plan.py` | dataclass | Una entidad detectada (`kind`+`value`) |
| `RetrieveOp` | `recall_plan.py` | dataclass | Una operación ejecutable |
| `RecallPlan` | `recall_plan.py` | dataclass | **Plan declarativo** (sustituye al intent único) |
| `Evidence` | `evidence.py` | dataclass | Una prueba procedente de un recuerdo |
| `RecallTrace` | `evidence.py` | dataclass | Trazabilidad plan→ops→evidence |
| `RecallResult` | `evidence.py` | dataclass | Salida: utterance + evidence + trace |
| `RecallPlanner` (no-clase) | `recall_planner.py` | `def understand(...)` | Construye el plan desde texto |

> **Decisión:** A1 usa **funciones puras de módulo** en lugar de una clase `RecallPlanner`, porque no hay estado (la clase se introduciría en A2 si el engine necesita caché). Evita clases vacías/artificiales.

---

## 4. RecallPlan

### 4.1 Definición

```python
@dataclass(frozen=True, slots=True)
class TimeWindow:
    since: float | None = None
    until: float | None = None
    hours: float | None = None
    anchor: Anchor = Anchor.NOW

@dataclass(frozen=True, slots=True)
class EntitySlot:
    kind: str            # "label" | "zone" | "camera" | "text"
    value: str

@dataclass(frozen=True, slots=True)
class RetrieveOp:
    kind: RetrieveKind
    entity: str | None = None      # label o zona canónica (ej. "PET")
    query: str | None = None       # para SEARCH
    limit: int = 5
    min_score: float = 0.0
    risk: str | None = None
    location: str | None = None

@dataclass(frozen=True, slots=True)
class RecallPlan:
    lang: str
    window: TimeWindow
    entities: tuple[EntitySlot, ...] = ()
    ops: tuple[RetrieveOp, ...] = ()
    relations: tuple[RelationKind, ...] = ()
    aggregation: Aggregation | None = None
    wants_evidence: bool = True
```

### 4.2 `plan_to_dict(plan) -> dict`
Serializa a estructura JSON-safe (`anchor.value`, `kind.value`, `entities` como lista de dicts). Es el **objeto que viaja en `RecallTrace`** para hacer la respuesta auditable.

### 4.3 Regla anti-árbol IF/THEN (obligatoria)
`understand` **no compara preguntas**, compone desde *slots*. La construcción de `ops` sigue una **tabla declarativa**, no ramas por pregunta:

| Condición de slot | Ops añadidas |
|---|---|
| hay `label` | `LAST_SEEN(label)` + `RANGE(window, label)` (historial) |
| no hay `label`, hay texto | `SEARCH(query)` + `RANGE(window)` |
| `aggregation == COUNT` | `AGGREGATE(COUNT, window)` |
| `aggregation == SUMMARY` | `AGGREGATE(SUMMARY, window)` + `RANGE(window)` |
| `anchor == SESSION_START` o `before_after` | `RANGE(window)` obligatorio |
| **siempre (fallback)** | se emite al menos `SEARCH` — **nunca `ops` vacío** |

> Añadir un caso de uso = **añadir una fila/fila de tabla**, jamás `if "¿dónde vi mi mascota?": …`.

### 4.4 Pasadas independientes de `understand`
Cada dimensión se resuelve con **una pasada sobre su tabla propia** y **acumula** (no compite):

1. **lang** → `lang` explícito o detección (sin adivinar si ya viene `es`/`en`).
2. **tiempo** → horas/ventana (reutiliza la lógica de `_HOURS_RE` vía `MemoryIntentClassifier.classify`, que ya es **API pública** y devuelve `MemoryIntent.hours`).
3. **entidades** → label/zona/cámara (vía `MemoryIntent.label`/`.location`, API pública de `classify`).
4. **relaciones** → tabla `phrase → RelationKind` (ej. `"antes de"` → `BEFORE_AFTER`, `"mientras"` → `TIMELINE`, `"cámaras"` → `CORRELATION`, `"dónde"` → `SPATIAL`).
5. **agregación** → tabla `phrase → Aggregation` (`"cuántos"` → `COUNT`, `"qué pasó"/"resumen"` → `SUMMARY`).
6. **ancla** → tabla `phrase → Anchor` (`"mientras estaba fuera"` → `SESSION_START`).

> **Reutilización sin duplicar tablas:** los slots de *label/location/hours* se obtienen delegando a la **API pública** `MemoryIntentClassifier().classify(text, lang)` (`memory_intent.py:195`). Solo se crean tablas **nuevas** para las 4 dimensiones que V1 no cubre (relación, agregación, ancla, zona).

---

## 5. Evidence

### 5.1 Definición

```python
@dataclass(frozen=True, slots=True)
class Evidence:
    record_id: str
    ts: float
    location: str
    labels: tuple[str, ...]
    risk: str
    confidence: float
    snippet: str
    camera_id: str | None = None
    zone: str | None = None

    @classmethod
    def from_record(cls, record: object, *, confidence: float | None = None) -> Evidence: ...

@dataclass(frozen=True, slots=True)
class RecallTrace:
    lang: str
    plan: dict[str, object]                 # plan_to_dict(plan)
    ops_executed: tuple[dict[str, object], ...]
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class RecallResult:
    utterance: str
    evidence: tuple[Evidence, ...]
    trace: RecallTrace
    lang: str
    is_error: bool = False
```

### 5.2 `Evidence.from_record(record: object)` — **duck-typing deliberado**
Lee atributos con `getattr(record, ...)`, **sin importar** `MemoryRecord`. Es la técnica ya usada en el repo (`memory_resolvers._labels_of`, línea 125-131). **Motivo:** `domain` no puede importar `infrastructure` (`src/domain/__init__.py` lo prohíbe explícitamente). Un objeto simulado en tests basta para validarla.

### 5.3 Narrativa determinista
```python
def render_utterance(evidence, *, lang: str, now: float) -> str
```
- **0 evidencia** → `render_abstention(lang)` (**abstención**, jamás inventa).
- **≥1** → una línea por evidencia (máx. 3) con `location`/`labels`/`format_relative_time(ts, now, lang)`.
- Misma `evidence` + mismo `now` + mismo `lang` ⇒ **salida byte a byte idéntica**.
- La redacción depende del **contenido recuperado**, no del tipo de pregunta → es lo que unifica los 4 casos.

### 5.4 `format_relative_time` (además de V1)
V1 ya tiene `_relative_time` **privado** en `memory_resolvers.py:93` (infraestructura → inaccesible desde dominio). A1 crea su propia versión **en dominio**. **Riesgo de duplicidad consciente**: documentado aquí; en A3 se unifican ambas en un helper de dominio (`memory_resolvers._relative_time` pasará a delegar), tarea **fuera de A1**.

---

## 6. RecallPlanner

### 6.1 Contrato

```python
def understand(text: str, lang: str | None = None, *, now: float | None = None) -> RecallPlan
```

### 6.2 Algoritmo (determinista)

1. `now = now or 0.0` → **si no se inyecta, se usa un valor fijo de referencia** para que el plan sea reproducible en tests. (En producción A2 inyectará `time.time()`; A1 no lo llama nunca.)
2. `query = " ".join(text.lower().split())`; si vacío → **plan de fallback**.
3. `_detect_lang(text, lang)`: si `lang ∈ {es,en}` se respeta; si no, detección por acentos/palabras clave.
4. **Pasadas 2-6 (§4.4)**: cada una acumula slots/relations/aggregation/anchor en locales, **sin `elif` encadenados entre dimensiones**.
5. **Construcción de `ops`** por la **tabla** de §4.3.
6. Devuelve `RecallPlan` con `wants_evidence=True`.

### 6.3 Garantías
- `plan.ops` **nunca vacío** (invariante testeable).
- Misma entrada + mismo `now` ⇒ mismo plan (idempotente).
- Sin mutación de estado de módulo (sin cachés ni globals mutables).
- `relations` deduplicadas y con orden estable.

---

## 7. Tests necesarios

> **Solo se añaden tests nuevos. No se edita, mueve ni marca `@skip` ningún test existente.**

### 7.1 `tests/unit/test_recall_plan.py` (~7 tests)
- `test_time_window_defaults` → `since/until/hours is None`, `anchor == Anchor.NOW`.
- `test_entities_and_ops_default_to_empty_tuple` (evita `None` y `mutable default`).
- `test_plan_is_frozen_and_slot_sealed` → `frozen` + sin `__dict__` (usa `slots=True`).
- `test_plan_to_dict_is_json_safe` → valores de enum serializados por `.value`; sin tipos no-JSON.
- `test_plan_to_dict_is_deterministic` → dos llamadas idénticas.
- `test_retrieve_kind_values_are_stable` → claves de texto congeladas (compat. de trace).
- `test_relation_kind_values_are_stable`.

### 7.2 `tests/unit/test_evidence.py` (~11 tests)
- `test_evidence_frozen_with_optional_defaults` → `camera_id/zone is None`.
- `test_from_record_reads_detections_duck_typed` (objeto stand-in con `detections`).
- `test_from_record_missing_fields_degrade` → sin `detections` → `labels=()`; sin `location` → `""`.
- `test_from_record_confidence_is_max` → máx. de `detections[].confidence`.
- `test_from_record_does_not_import_memory_record` → no usa tipos de infraestructura.
- `test_render_abstention_bilingual` → ES≠EN y ambos no vacíos.
- `test_render_utterance_deterministic` → dos invocaciones con el mismo `now` ⇒ igual.
- `test_render_utterance_never_invents` → evidencia vacía ⇒ sólo abstención.
- `test_render_utterance_bilingual` → ES y EN distintos, ambos contienen `location`.
- `test_format_relative_time_matches_v1_semantics` → mismos umbrales de V1 (60 s / 3600 s / 86400 s).
- `test_truncate_snippet_limit` → corte en 120 con `...`.
- `test_recall_result_serializable` → `trace.plan` dict + `evidence_ids` coherente con `evidence`.

### 7.3 `tests/unit/test_recall_planner.py` (~11 tests, **parametrizado**)
- `test_understand_four_target_cases` → **parametrizado** sobre los 4 casos, verificando `entities/ops/relations` esperados (p.ej. mascota ⇒ `SPATIAL`+`LAST_SEEN`; "antes de la caída" ⇒ `BEFORE_AFTER`+`RANGE`; "cámaras" ⇒ `CORRELATION`).
- `test_understand_ops_never_empty` (invariante, sobre varias queries).
- `test_understand_fallback_when_nothing_recognized` ⇒ `SEARCH` presente.
- `test_understand_respects_explicit_lang` → `lang="en"` ⇒ `plan.lang == "en"`.
- `test_understand_detects_lang_when_absent` → ES acentuado ⇒ `es`.
- `test_understand_is_deterministic` → misma query+`now` ⇒ plan idéntico (2 ejecuciones).
- `test_understand_uses_injected_now` → dos `now` distintos ⇒ windows distintas (prueba de inyección, sin `time.time()`).
- `test_understand_relations_deduplicated` → orden estable, sin duplicados.
- `test_understand_empty_query_returns_fallback_plan`.
- `test_understand_reuses_public_classifier_api` → `label` extraído vía `classify` coherente con V1 (p.ej. "mascota"→`PET`).
- `test_understand_never_returns_none` → nunca `None`.

### 7.4 `tests/unit/test_domain_purity.py` (~3 tests, **guard**)
- `test_new_modules_import_only_stdlib_and_domain` → lee los 3 ficheros y falla si aparecen `fastapi`, `boto3`, `mcp`, `src.infrastructure`, `httpx`, `PIL`.
- `test_no_time_or_network_calls_in_domain` → falla si aparece `time.time(`, `requests`, `urlopen` en los 3 módulos.
- `test_required_future_import_present` → `from __future__ import annotations` en los 3.

**Esperado:** `208 + ≈32 nuevos ≈ 240 passed` (mínimo aceptable **≥ 232**).

---

## 8. Estrategia para mantener 208 PASSED

### 8.1 Lista cerrada de "NO TOCAR" (A1)
```
src/infrastructure/**            src/domain/models/**      src/domain/ports/**
src/main.py                      src/static/**             alexa_skill/**
tests/**  (existentes)           pytest.ini  setup.cfg  conftest.py  requirements.txt
src/domain/services/memory_intent.py   src/domain/services/__init__.py   src/domain/__init__.py
```

### 8.2 Mecanismos de protección
1. **A1 = solo creación.** Ningún archivo preexistente recibe un byte nuevo.
2. **Sin tocar `MEMORY_TOOL_NAMES` ni `AGENTIC_TOOL_CATALOG`** → `test_memory_resolvers.py:154` (`MEMORY_TOOL_NAMES <= set(names)`) y `test_agent_tools.py` siguen válidos sin ajustes.
3. **Sin tocar `memory_resolvers`** → las aserciones de **texto literal** (`test_memory_converse.py:54`, `test_memory_resolvers.py:161`) permanecen byte a byte.
4. **Sin imports en dirección inversa** → nada en V1 importa los módulos nuevos ⇒ **imposible por construcción** que A1 altere comportamiento previo.
5. **Sin LLM** → se conserva `assert fake_llm.calls == 0`.
6. **Tiempo inyectado** (`now`) → sin dependencia de reloj de pared ⇒ tests deterministas y paralelizables.
7. **Gate tras cada archivo nuevo**, en este orden:
```powershell
.\.venv\Scripts\python.exe -m pytest -q                     # debe seguir 208 + N nuevos, 0 fallos
.\.venv\Scripts\python.exe -m flake8 src tests              # 0 violaciones (88, E203/W503 ignorados)
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```
8. **Prohibido**: editar `pytest.ini` (p.ej. marcar tests `skip`/`xfail`), cambiar `testpaths`, o subir umbrales de `max-line-length`.
9. **Si un test existente falla → A1 está mal diseñado** (no se "ajusta" el test). Se revierte el módulo nuevo responsable.

### 8.3 Verificación de "solo creación"
Antes de empezar A1, capturar huella del área protegida y volver a compararla al cerrar:
```powershell
Get-FileHash -Path <lista 8.1> | Out-File baseline_a1.sha256
# ... al cerrar A1: recomparar y exigir cero diferencias
```

---

## 9. Estrategia de coexistencia con `MemoryConverse`

### 9.1 Principio: **paralelo, nunca sustitutivo (en A1)**
`memory_converse` sigue siendo el **único** camino vivo para `/api/converse`, dashboard y Alexa+. A1 añade el núcleo del nuevo camino **sin conectarlo todavía**.

### 9.2 Mapa de coexistencia

| Superficie | Camino hoy | Tras A1 | Tras A3 (futuro, no ahora) |
|---|---|---|---|
| `/api/converse` (dashboard, Voice Dock) | `build_memory_converse_resolver` → V1 | **sin cambios** | sin cambios |
| MCP `memory_converse` | V1 | **sin cambios** | sin cambios |
| MCP `memory_recall` | — | **no existe** (A1 no añade tools) | **nuevo tool → engine** |
| `/api/recall` | — | **no existe** | **nuevo endpoint → engine** |
| `memory_last_seen/search/summary` | V1 | **sin cambios** | sin cambios |

### 9.3 Reglas de acoplamiento
- **A1 no importa** `memory_resolvers`, `memory_bridge`, `memory_service`, `main`.
- **Nadie importa a A1 en A1** (los módulos nuevos son hojas del árbol de dependencias). → Coexistencia = **cero interferencia por construcción**.
- **Sin estado compartido**: `understand` no mantiene cachés ni registros de sesión → no puede afectar a `MemoryBridge._episodes`.
- **Sin reescritura de narrativa**: A1 no reemplaza frases V1; la redacción nueva existe *junto* a la vieja.
- **Decisión aprobada:** migración de `memory_converse` al engine → **fase G**, sólo con garantía de salida idéntica para los casos ya cubiertos por los 208 tests (exigirá un test de equivalencia V1↔V2 antes de conmutar).

### 9.4 Cabecera de migración (preparada, no activada)
Se deja documentada la futura conmutación `memory_converse → engine`, pero **no se escribe código para ella en A1** (evita riesgo de regresión y de código muerto).

---

## 10. Criterios de aceptación de A1

### A. Gates duros (obligatorios)
| # | Criterio | Verificación |
|---|---|---|
| 1 | `208` tests previos **todos verdes**, sin edición de tests existentes | `pytest -q` ⇒ `0 failed`, `208` originales incluidos |
| 2 | Tests nuevos añadidos | total **≥ 232** (objetivo ≈240) |
| 3 | `flake8` limpio | `flake8 src tests` ⇒ **0** |
| 4 | `black` limpio | `black --check src tests --line-length 88` ⇒ sin cambios |
| 5 | **Cero archivos modificados** | huella §8.3 idéntica (solo `??` nuevos) |
| 6 | **Cero dependencias nuevas** | `requirements.txt` byte-idéntico |
| 7 | Pureza del dominio | `test_domain_purity.py` verde; sin `src.infrastructure` en los 3 módulos |

### B. Funcionales
| # | Criterio | Verificación |
|---|---|---|
| 8 | Los 4 casos objetivo producen `RecallPlan` correcto | `test_understand_four_target_cases` |
| 9 | `plan.ops` nunca vacío | invariante en planner |
| 10 | Determinismo | 2 ejecuciones idénticas (planner y `render_utterance`) |
| 11 | Abstención (no inventar) con evidencia vacía | `test_render_utterance_never_invents` |
| 12 | Tiempo inyectado, sin `time.time()` | purity + `uses_injected_now` |
| 13 | Sin LLM | purity guard + sin llamadas a puertos LLM |

### C. Coexistencia
| # | Criterio | Verificación |
|---|---|---|
| 14 | Salida V1 byte idéntica | no se tocó `memory_resolvers` ⇒ tests de texto literal pasan |
| 15 | Catálogo/tools V1 intactos | `MEMORY_TOOL_NAMES` y `AGENTIC_TOOL_CATALOG` sin cambios |
| 16 | Ningún import inverso V1→A1 | huella + revisión de imports |

### D. Definición de "terminado" (DoD)
A1 está **terminado y apto para revisión** cuando los 7 criterios de A son verdes **y** los 3 grupos (B, C) lo son, dejando constancia de los tres comandos ejecutados. **A2 no comienza hasta que A1 cumpla DoD.**

---

## 11. Orden de ejecución propuesto de A1

| Paso | Acción | Gate inmediato |
|---|---|---|
| 0 | Capturar huella §8.3 | — |
| 1 | `recall_plan.py` + `test_recall_plan.py` | `pytest -q` |
| 2 | `evidence.py` + `test_evidence.py` | `pytest -q` |
| 3 | `recall_planner.py` + `test_recall_planner.py` | `pytest -q` |
| 4 | `test_domain_purity.py` (guard) | `pytest -q` |
| 5 | Gates completos + huella final | `pytest -q` + `flake8` + `black` + hash |

**Fuera de A1 (NO ahora):** `records_between()`, `recall_engine.py`, `memory_timeline.py`, tool `memory_recall`, `/api/recall`, campos `camera_id`/`zone`, cualquier cambio en V1.
