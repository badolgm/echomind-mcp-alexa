# ECHOMIND_V2_PHASE_A_RECALL_ENGINE.md

**Sprint:** ECHOMIND V2 PHASE A — Recall Engine Core
**Tipo:** Diseño + plan de primer paso de implementación (**sin implementar, sin commits, sin push, sin dependencias nuevas**)
**Fecha:** 2026-10-17
**Base:** EchoMind V1 validado — **208 tests PASSED** (gates: `pytest -q`, `flake8 src tests`, `black --check src tests --line-length 88`)

---

## 0. Alcance de Phase A

**Fuera de foco (ya validado, no se toca):** cámaras, Android, Vivotek, Dashboard, Voice Dock, TTS, STT.
**Dentro de foco:** transición **Intent-Centric → Recall-First** en la capa de memoria.

| En Phase A | Fuera de Phase A |
|---|---|
| `understand → recall_plan → retrieve → relate → synthesize → respond` | Bedrock/LLM en síntesis (queda para vNext) |
| Evidence Layer (trazabilidad) | Grafos/entidades semánticas |
| Timeline Layer (base) | Correlación multi-cámara completa (Phase D/E) |
| Spatial Memory Layer (base) | Bbox/región detallada |
| Un **tool MCP nuevo** + endpoint nuevo | Reescribir `memory_converse` (prohibido romperlo) |
| **Una** API aditiva de lectura por ventana | Reemplazar store / Qdrant |

**No romper:** `MemoryBridge`, `VectorMemoryService`, `MemoryRecord`, `MemoryConverse`, MCP, Alexa+, Dashboard, Voice Dock, **los 208 tests**.

---

## 1. Arquitectura actual (AS-IS)

### 1.1 REMEMBER — qué lo representa ya (Q1)

| Componente | Archivo | Por qué es "remember" |
|---|---|---|
| **`MemoryBridge`** | `memory_bridge.py:80` | Captura observaciones reales del `EventHub` y las persiste; coalesce ticks en **episodios** por `(location, labels)` con `episode_gap=30` (`memory_bridge.py:34,109,114`) |
| **`VectorMemoryService`** | `memory_service.py:87` | Store persistente en memoria con embeddings deterministas |
| **`MemoryRecord`** | `memory_service.py:26` | La unidad de recuerdo: `id, timestamp, location, source, detections, risk, model_analysis` |
| **`demo_seed_service`** | `demo_seed_service.py` | Recuerdos deterministas para demo sin eventos vivos |
| **`AmbientWatchService`** | `ambient_watch_service.py:263` | Genera las observaciones que se recuerdan |

> **Veredicto: REMEMBER está completo.** No se modifica.

### 1.2 RECALL — qué lo representa ya (Q2)

| Componente | Qué aporta | Qué no aporta |
|---|---|---|
| `VectorMemoryService.search_memory(query, limit, min_score, location, risk)` | recuperación semántica determinista (sha256 256-D + coseno) | no hay slice temporal arbitrario |
| `.last_seen(label, location, source)` | "última vez" | no devuelve la *anterior* |
| `.count_occurrences / label_counts / count_events` | agregación | — |
| `.top_events / recent_high_risk_events / recent_critical_events` | ranking por severidad/recencia | ventana fija, no por entidad |
| `memory_resolvers` (`last_seen/search/summary/converse`) | convierte recuperación en frase | **plantilla por intent, 1 plan, sin relación** |
| `MemoryIntentClassifier` | slotiza la pregunta | **un único `MemoryIntent`** (`memory_intent.py:26`) |

> **Veredicto: RECALL existe como *retrieval* y como *planteeo simple*. Le falta *plan componible* y *síntesis sobre evidencia*.**

### 1.3 Restricciones de no-regresión descubiertas (críticas)

Verificadas sobre los tests reales:

1. **Texto exacto de respuesta**: `tests/unit/test_memory_converse.py:54` y `test_memory_resolvers.py:161` afirman **cadenas literales** (p.ej. `"La última detección de una persona ocurrió hace 14 minutos en cam-01."`).
   → **Prohibido** alterar la salida de `build_memory_converse_resolver`, `memory_last_seen/search/summary`.
2. **Unión, no conteo**: `test_memory_resolvers.py:154` → `assert MEMORY_TOOL_NAMES <= set(names)`.
   → Si se añade un nombre a `MEMORY_TOOL_NAMES`, **debe añadirse también** al `AGENTIC_TOOL_CATALOG` o el test falla.
3. **Sin conteos fijos de tools**: `test_agent_tools.py:30-40` usa pertenencia/unicidad → **añadir un tool al catálogo es seguro**.
4. **Ningún test fija la lista exacta de tools**: comparaciones dinámicas (`test_agent_tools.py:75`, `test_memory_converse.py:159`).
5. **La memoria NUNCA llama al LLM**: `test_memory_resolvers.py:178` → `assert fake_llm.calls == 0`.
   → El engine de Phase A debe ser **LLM-free**.
6. **`MemoryRecord(...)` se construye siempre con keywords** (`memory_bridge.py:67,119`, `demo_seed_service.py:105`, tests) → añadir campos **opcionales con default es seguro**.

---

## 2. Análisis: qué falta (Q3–Q5)

### 2.1 RELATE (Q3) — falta
- Agrupar records en **episodios** que sobrevivan a un reinicio (hoy `MemoryBridge._episodes` es RAM efímera y `MemoryRecord` no guarda `episode_id`).
- Correlación **temporal + espacial** entre fuentes (mismo evento, Δ segundos, zonas vecinas).
- Unión de evidencia (fusión de detecciones entre observaciones).

### 2.2 TIMELINE (Q4) — falta
- **Slice por ventana arbitraria**: no existe método público `records_between(since, until)`.
- **Orden + gaps**: listar episodios cronológicos y marcar silencios.
- **`before(target)`**: "¿qué pasó antes de X?" — no hay primitiva.
- **Ancla de sesión**: "mientras estaba fuera" necesita `anchor = session_start` (hoy cada query es stateless).

### 2.3 MEMORIA ESPACIAL (Q5) — falta
- `AmbientWatchService` publica **`"location": "camera"`** (`ambient_watch_service.py:322`) → toda la memoria en vivo cae en una ubicación genérica.
- No existe `camera_id` ni `zone` en `MemoryRecord`.
- No hay **mapa cámara→zona** (`cam-01 → living`, `cam-04 → patio/pool`).
- `detections` no llevan región/bbox → no hay "cerca de la piscina".

---

## 3. Arquitectura objetivo (TO-BE) — Phase A

```
                       ┌──────────────────────────────────────────────┐
   query (ES/EN) ────▶ │ 1. UNDERSTAND   recall_planner (puro, domain) │
                       │    slots: entity · time · relations · anchor  │
                       └──────────────────────┬───────────────────────┘
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │ 2. RECALL PLAN   RecallPlan (declarativo)     │
                       │    ops[] + relations[] + window + lang        │
                       └──────────────────────┬───────────────────────┘
                                              ▼
   VectorMemoryService ◀─ 3. RETRIEVE   (primitivas existentes + records_between)
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │ 4. RELATE   episodes · spatial · correlation  │
                       └──────────────────────┬───────────────────────┘
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │ 5. SYNTHESIZE  narrativa desde Evidence[]     │
                       │    (determinista, sin LLM en Phase A)         │
                       └──────────────────────┬───────────────────────┘
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │ 6. RESPOND   MCPResponse =                   │
                       │    [text/plain utterance] + [text/json        │
                       │     {plan, evidence[], trace}]               │
                       └──────────────────────────────────────────────┘
```

**Principio de transición sin romper:** V1 sigue siendo el camino por defecto; el engine entra por un **canal nuevo paralelo**. Sólo en una fase posterior se migra `memory_converse`, y únicamente con garantía de salida idéntica para los casos ya cubiertos.

### 3.1 Estructura de módulos propuesta

```
src/domain/services/                      # puro, sin frameworks (dependencia solo ↓)
  recall_plan.py        RecallPlan, RetrieveOp, RelationOp, TimeWindow   (nuevo)
  evidence.py           Evidence, RecallTrace                            (nuevo)
  recall_planner.py     understand(query, lang, now) -> RecallPlan       (nuevo)

src/infrastructure/services/              # donde ya viven los records/store
  recall_engine.py      RecallEngine.execute(plan) -> RecallResult       (nuevo)
  memory_timeline.py    episodes()/timeline()/before()                   (nuevo)
  memory_spatial.py     camera_zone_map, resolve_zone(location,camera)   (nuevo)

src/infrastructure/adapters/mcp/
  recall_resolvers.py   build_memory_recall_resolver(engine)             (nuevo)
  memory_resolvers.py   +1 rama en build_memory_resolver + MEMORY_TOOL_NAMES (+2 líneas)
  tool_resolvers.py     sin cambios (despacha por MEMORY_TOOL_NAMES:539)

src/domain/models/tools.py                + MEMORY_RECALL al catálogo     (+1 tool)
src/infrastructure/services/memory_service.py   + records_between()      (+1 método, aditivo)
src/infrastructure/services/memory_bridge.py    sin cambios en comportamiento
src/main.py                                + /api/recall                  (+endpoint)
```

> **Regla de dependencia respetada:** `domain` no importa `infrastructure` (los operadores sobre `MemoryRecord` viven en infraestructura; el *plan* y la *evidencia* son puros).

---

## 4. Recall Engine (Q6, Q7)

### 4.1 `RecallPlan` (la estructura que sustituye al intent único)

```
RecallPlan {
  lang: "es"|"en"
  window: { since?, until?, hours?, anchor: "now"|"session_start"|ts }
  entities: [ { kind: "label"|"zone"|"camera"|"text", value } ]
  ops: [ RetrieveOp ]           # 0..n → se ejecutan y combinan
  relations: [ "episode" | "spatial" | "correlation" | "timeline" | "before_after" ]
  hints: { aggregation?: "count"|"list"|"summary", evidence: bool }
}

RetrieveOp ∈ {
  LastSeen(entity, filters)                    # → memory.last_seen()
  Search(query, filters, limit, min_score)     # → memory.search_memory()
  Range(window, filters)                       # → memory.records_between()  [NUEVO]
  Top(window, risk)                            # → memory.top_events()/recent_*()
  Aggregate(group_by, window)                  # → memory.label_counts()/count_*
  CurrentState()                               # → watch.last_state
}
```

### 4.2 `understand()` — sin árboles IF/THEN

- **Reutiliza** las tablas de entidades de `memory_intent.py:41` (`_LABEL_TERMS`) y el parser de horas `_HOURS_RE`.
- Produce **slots múltiples** en vez de una sola rama: p.ej. `{"mascota", "dónde", "antes"}` → `ops=[LastSeen(PET), Range(until=ts)]` + `relations=["timeline","spatial"]`.
- **Regla anti-ramas:** `understand` *acumula* slots; nunca hace `if X → Y`. Añadir un caso = añadir **una entrada de tabla**, no una rama.
- **Fallback garantizado:** si no hay slots, emite `Range(last 24h) + Search(query)` → equivalente al `SEARCH` actual (nunca devuelve vacío por diseño).

### 4.3 `retrieve()` — reutilización del núcleo (Q7)

Todas las ops se ejecutan **contra `VectorMemoryService` sin modificarlo**, salvo **una** adición:

| Op | Método existente |
|---|---|
| `LastSeen` | `last_seen(label, location, source)` (`memory_service.py:133`) |
| `Search` | `search_memory(query, limit, min_score, location, risk)` (`:109`) |
| `Top` | `top_events` / `recent_high_risk_events` / `recent_critical_events` (`:225,248,258`) |
| `Aggregate` | `label_counts` / `count_occurrences` / `count_events` (`:178,157,205`) |
| `CurrentState` | `watch.last_state` |
| **`Range`** | **NUEVO `records_between(since, until, *, location=None)` — lectura O(n), aditivo, sin alterar métodos existentes** |

`records_between` es **el único cambio necesario en `VectorMemoryService`** y es puramente aditivo: no toca ningún método, ni el store, ni los 208 tests.

### 4.4 `relate()` y `synthesize()`

- `relate`: agrupa los `Evidence` obtenidos en **episodios** (gap 30 s, misma noción que `_EPISODE_GAP_SECONDS`), los ordena y aplica la relación pedida (`spatial`, `before_after`, `correlation`).
- `synthesize`: genera la narrativa **leyendo evidencia**, no ramas `if`. La misma frase se arma con `Evidence` + plantilla de *redacción* parametrizada por **contenido de evidencia** (no por tipo de pregunta).

> **Diferencia decisiva vs V1:** la redacción V1 está condicionada al *intent*; la redacción V2 está condicionada a *qué evidencia se recuperó*. Por eso "¿dónde vi mi mascota?" y "¿dónde ocurrió la caída?" comparten el mismo mecanismo.

---

## 5. Evidence Layer (Q8, Q10)

### 5.1 Estructuras

```
Evidence {
  record_id: str
  ts: float
  location: str
  camera_id: str | None
  zone: str | None
  labels: [str]
  risk: str
  confidence: float        # máx. de detections[label].confidence
  snippet: str             # model_analysis (recortado)
}

RecallTrace {
  engine: str  version: int
  plan: RecallPlan
  ops_executed: [ {op, filters, returned_ids[]} ]
  evidence_ids: [str]
  timings: { understand_ms, retrieve_ms, relate_ms, synthesize_ms }
}
```

### 5.2 Reglas
1. **Ninguna frase sin evidencia.** Si `evidence[]` está vacío → *"No tengo recuerdos de eso"* (**abstención**, no alucinación).
2. **Salida dual en MCP**: `[text/plain]` (utterance de Alexa+) + `[text/json]` `{evidence, trace}`.
3. **Determinista**: misma memoria sembrada + misma query ⇒ misma respuesta byte a byte (testeable).
4. **LLM-free** en Phase A (cumple `fake_llm.calls == 0`).

### 5.3 Trazabilidad end-to-end (Q10)
`query → plan → ops → evidence_ids → narrativa`. Cada respuesta es **reproducible**: con el `trace` se puede re-ejecutar el plan contra el store y obtener lo mismo. `RecallTrace` es serializable → se puede registrar en telemetría o en el dashboard sin tocar V1.

---

## 6. Timeline Layer (Q4, base en Phase A)

**Objetivo:** responder "¿qué pasó mientras estaba fuera?" y "¿qué ocurrió antes de la caída?"

- `Range(window)` → records ordenados por `ts`.
- `build_episodes(records, gap=30.0)` → `Episode{start, end, location, labels, risk, evidence_ids}` (misma lógica de gap que `memory_bridge.py:31`, pero sobre la memoria persistida y **reconstituible tras reinicio**).
- `before(target_ts, window)` → episodios previos al objetivo.
- `anchor="session_start"` → ancla temporal de sesión para "mientras estaba fuera" (se registra al abrir la sesión MCP).

**En Phase A:** se implementan `Range` + `build_episodes` + orden/gaps. `before()` entra en Phase B/C con la segmentación completa.

---

## 7. Spatial Memory Layer (Q5, base en Phase A)

**Mapa cámara→zona (config estática, sin dependencias):**

```
cam-01 → living            cam-02 → kitchen
cam-03 → north_corridor    cam-04 → patio
cam-phone → (zone móvil)   genérico → (degrada a `location`)
```

- `resolve_zone(location, camera_id)`: si `location` es real (`patio`, `kitchen`, `cam-01`, …) la usa; si es `"camera"` o vacía, **degrada** a `camera_id`→zona; si nada, devuelve `location` original (**nunca inventa**).
- `MemoryRecord` gana campos **opcionales** `camera_id`, `zone` (con default `None`) → los records V1 siguen siendo válidos.
- `relate(spatial)` agrupa evidencia por zona; `resolve_zone` alimenta "cerca de la piscina" cuando exista región (vNext).

---

## 8. Evolución de `MemoryRecord` sin romper compatibilidad (Q9)

```
MemoryRecord (Phase A, todo lo nuevo con default → V1 intacto):
  id, timestamp, location, source, detections, risk, model_analysis   # SIN CAMBIOS
  + camera_id: str | None = None
  + zone: str | None = None
  + episode_id: str | None = None     # fase C
  + embedding_version: int = 1        # versiona embed_text
```

**Por qué es seguro (verificado):**
- `MemoryRecord` es `@dataclass(frozen=True, slots=True)`; añadir campos con default mantiene `frozen/slots` y la construcción por **keywords** sigue válida (`memory_bridge.py:67,119`, `demo_seed_service.py:105`, tests en `test_memory_converse.py:24`, `test_memory_service.py`).
- Ningún método de `VectorMemoryService` depende del orden posicional.
- Los records sin `camera_id/zone` (`None`) hacen que el engine **degrada** a `location`, igual que V1.

> **Prohibido:** renombrar/quitar campos existentes, cambiar `detections` de forma, alterar `embed_text` (mantener `embedding_version` para cambios futuros).

---

## 9. Los 4 casos objetivo con evidencia real (Q8)

| Pregunta | `understand` (slots) | `ops` | `relate` | Salida (evidence-first) |
|---|---|---|---|---|
| **¿Dónde vi mi mascota?** | entity=PET, relation=spatial+history | `LastSeen(PET)` + `Range(7d, label=PET)` | episode + spatial | *"La última observación hace {t} en {zona} por {camera_id}. Antes apareció en {zona_previa}."* + `evidence[mem-a, mem-b]` |
| **¿Qué pasó mientras estaba fuera?** | window=anchor `session_start`, aggregation=summary | `Range(session_start→now)` + `Aggregate(label)` | timeline (orden + gaps) | *"Desde tu salida: {n} episodios — {t1} {zona} {labels}; {t2}…; silencio {gap}."* + evidence |
| **¿Qué ocurrió antes de la caída?** | entity=FALL, relation=before_after, window=−2h | `Range(until=ts_fall, ±2h)` | timeline + before_after | *"Antes de la caída ({t}): {t−2h} {zona}…; {t−1h}…; a las {t} ocurrió la caída."* + evidence |
| **¿Qué cámaras observaron el mismo evento?** | window + relation=correlation | `Range(ventana Δ=5s)` | correlation (Δ + vecindad) | *"Mismo evento observado por cam-01 (living) y cam-04 (patio) entre {t0} y {t1}."* + `evidence[mem-1, mem-2]` |

**Nota honesta de alcance:** el *caso 4 completo* necesita `camera_id`/zona (Phase D) y correlación con vecindad (Phase E). En Phase A el plan y la estructura ya existen; con datos V1 (`location` genérica) el caso devuelve **degradación honesta** (abstención sobre lo que no puede probar) en vez de una respuesta inventada.

---

## 10. Roadmap incremental

| Fase | Contenido | Rompe 208 | Incremento visible |
|---|---|---|---|
| **A1** | `recall_plan.py` + `evidence.py` + `recall_planner.py` + tests puros | No | Entiende y planifica (sin red) |
| **A2** | `records_between()` + `recall_engine.py` + `memory_timeline.py` + tests | No | Recupera y relaciona |
| **A3** | `memory_recall` (catálogo + `MEMORY_TOOL_NAMES` + resolver) + `/api/recall` + tests | No | **Visible en MCP y API** |
| **A4** | `memory_spatial.py` + campos `camera_id`/`zone` + degradación | No | Espacial base |
| **B** | Redacción plena de evidencia + `text/json` completo + abstención | No | Respuestas "reales" |
| **C** | `episode_id` persistido + `before()` + ancla de sesión | No | Timeline completo |
| **D** | `location` real en watchdog + `camera_id` en records | No | Memoria espacial |
| **E** | Correlación Δ + vecindad + `event_id` | No | Caso 4 completo |
| **F** | `memory_timeline`/`memory_evidence` tools + cards Alexa+ | No | Producto |
| **G** | Migrar `memory_converse` al engine (con salida idéntica) / Qdrant Edge | Sólo con gates verificados | Recall-First pleno |

---

## 11. Riesgos

| Riesgo | Sev. | Mitigación |
|---|---|---|
| Alterar salida de `memory_converse`/tools V1 (rompe tests exactos) | **Crítica** | V1 **intacto**; engine solo por canal nuevo (`memory_recall`/`/api/recall`) |
| Añadir a `MEMORY_TOOL_NAMES` sin catálogo (falla `test_memory_resolvers.py:154`) | Alta | Añadir **ambos a la vez** (checklist obligatoria) |
| Reglas/ramas IF-THEN creciendo | Alta | `understand` **acumula slots**; añadir caso = añadir fila de tabla, no rama |
| Pérdida de determinismo | Alta | Retrieval/relate puros; sin LLM en Phase A; semillas fijas; test de idempotencia |
| Romper compatibilidad del store | Alta | `MemoryRecord` solo +campos con default; `records_between` aditivo |
| Inventar zonas/ubicaciones | Media | `resolve_zone` **degrada** a lo original; nunca fabrica |
| Correlación O(n²) | Media | Índice por *time bucket*; top-k |
| Engine se vuelve "otra capa muerta" | Media | Fase **A3** garantiza superficie visible (tool + endpoint) |
| Sobrecarga de alcance en Phase A | Media | Límite duro: 4 casos, sin Bedrock, sin cambio de V1 |
| `slots=True` + campos nuevos | Media | Verificar `frozen(slots=True)` admite defaults antes de tocar |

---

## 12. Quick Wins (bajo riesgo, alto impacto, sin arquitectura)

1. **`location` real en `camera_alert`** (de `"camera"` → zona) en `ambient_watch_service.py:322`: desbloquea de raíz la memoria espacial. Es un **cambio de dato**.
2. **Exponer evidencia** (ids + ts + cámara) junto a las respuestas V1 actuales → trazabilidad inmediata ante el jurado.
3. **Observación anterior** en `last_seen` (2ª ocurrencia) → caso 1 casi completo con datos existentes.
4. **Usar `min_score`/`risk`** de `search_memory` en `converse` → mejor recuperación.
5. **`camera_id`** derivado de `source` en `MemoryRecord` → habilita correlacción futura con coste mínimo.

---

## 13. Primer paso real de implementación (A1)

> **Slice mínimo, verificable y sin red**: el *plan* y la *evidencia* como objetos puros del dominio, con tests nuevos. **No toca ningún archivo existente de comportamiento.**

**1. `src/domain/services/recall_plan.py`** (nuevo)
- `TimeWindow`, `RetrieveOp`, `RelationOp`, `RecallPlan` como `@dataclass(frozen=True, slots=True)`.
- Helpers puros: `plan_is_supported(plan)`, `plan_to_dict(plan)` (para el `trace`).

**2. `src/domain/services/evidence.py`** (nuevo)
- `Evidence`, `RecallTrace`, `RecallResult` (value objects, sin IO).
- `render_utterance(result, lang)` → texto determinista desde `evidence[]` (**redacción parametrizada por evidencia**, no por pregunta).

**3. `src/domain/services/recall_planner.py`** (nuevo)
- `understand(query, lang=None, now=...) -> RecallPlan`.
- Reutiliza tablas de `memory_intent.py` (import **solo de dominio**).
- Emite slots múltiples; **fallback** = `Range(24h) + Search(query)`.

**4. Tests nuevos (no modifican los existentes)**
- `tests/unit/test_recall_planner.py`: slots para los 4 casos; fallback; determinismo (misma query+memoria ⇒ mismo plan); sin LLM.
- `tests/unit/test_evidence.py`: `Evidence` válida; **abstención** con evidencia vacía; `render_utterance` estable.

**Criterios de no-regresión (gate obligatorio tras A1):**
```
.\.venv\Scripts\python.exe -m pytest -q     # 208 + N nuevos; NINGUNO existente roto
.\.venv\Scripts\python.exe -m flake8 src tests
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```

**Siguientes pasos (ya diseñados, se ejecutan en orden):**
- **A2** → `records_between()` en `memory_service.py` + `recall_engine.py` + `memory_timeline.py` + tests.
- **A3** → `MEMORY_RECALL` en `tools.py` **y** `"memory_recall"` en `MEMORY_TOOL_NAMES` + rama en `build_memory_resolver` (`memory_resolvers.py:524-533`) + endpoint `/api/recall` en `main.py` + tests de integración.
- **A4** → `memory_spatial.py` + campos `camera_id`/`zone`.

---

## 14. Criterios de éxito de Phase A

1. **0 regresiones**: los 208 tests siguen verdes; V1 intacto byte a byte.
2. **Transición iniciada**: `understand → recall_plan → retrieve → relate → synthesize → respond` ejecutable de punta a punta en A3.
3. **4 casos** cubiertos con **evidencia real y no plantillas** (y abstención honesta cuando faltan datos).
4. **Trazabilidad**: cada respuesta expone `plan + evidence + trace`.
5. **Determinismo**: sin LLM, semillas fijas, respuestas reproducibles.
6. **Espacio/timeline en base**: `records_between` + `resolve_zone` + episodios reconstituibles.

> **Decisión abierta:** en **A3**, ¿el nuevo `memory_recall` es *además* de `memory_converse` (recomendado: sí, sin riesgo) o pretendes que `memory_converse` delegue ya en el engine en Phase A (exigiría igualar byte a byte la salida de los casos de los 208 tests)? Mi recomendación: **paralelo en A3, migración en G**.
