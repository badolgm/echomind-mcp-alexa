# ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md

**Sprint:** ECHOMIND V2 — MEMORY FIRST AI
**Tipo:** Diseño de arquitectura (sin implementación, sin cambios de código, sin commits, sin push, sin dependencias nuevas)
**Fecha:** 2026-10-17
**Base:** EchoMind V1 validado (208 tests PASSED) — se **evoluciona**, no se reemplaza.

---

## 0. Pregunta central

> **¿Cómo convertir EchoMind en una memoria espacial conversacional basada en evidencia que razona sobre recuerdos reales sin perder determinismo, trazabilidad, compatibilidad MCP ni alineación con Alexa+?**

**Respuesta corta.**
Se introduce un **Recall Engine determinista** *delante* de los resolvers actuales, que transforma la pregunta en un **Recall Plan** (operaciones), **recupera** de `VectorMemoryService` mediante primitivas ya existentes, **relaciona** resultados en *episodios/timeline/espacio*, **sintetiza** una narrativa **evidence-first** y **responde** por MCP. Todo se apoya en `MemoryBridge` + `VectorMemoryService` + `MemoryRecord` **sin reemplazarlos**: V1 sigue siendo la capa de almacenamiento y la ruta de compatibilidad. El determinismo se preserva porque **el retrieval y la relación son puros y sin LLM**; el LLM (Bedrock) solo puede actuar, *opcionalmente y tras el QFP*, como **capa de síntesis de lenguaje sobre evidencia ya recuperada** — nunca como fuente de verdad ni de recuperación.

---

## 1. Arquitectura actual (AS-IS, validada)

### 1.1 Pipeline vigente

```
CameraFrameSource (Vivotek live / Android phone / simulation)
   └─ AmbientWatchService.tick()            [ambient_watch_service.py:263]
        ├─ sensores: SimulatedSensorBus.read()   [sensor_bus.py:31]
        ├─ movimiento: frame_delta_ratio()       [ambient_watch_service.py:93]
        └─ predict_ambient_state() -> risk + detections   [ambient_watch_service.py:137]
              └─ EventHub.publish({"kind":"camera_alert",...})  [ambient_watch_service.py:314]
                        │
   MemoryBridge.run() ──┴─> camera_alert_to_memory_record()  [memory_bridge.py:53]
        └─ coalescing por (location, labels) + episode_gap 30s  [memory_bridge.py:109]
              └─ VectorMemoryService.store_memory(record)     [memory_service.py:99]
                        │
   /api/converse  o  tool memory_converse     [main.py:204 · memory_resolvers.py:470]
        └─ MemoryIntentClassifier.classify()  [memory_intent.py:195]  → 1 Intent
              └─ resolver (last_seen/search/summary/history)   [memory_resolvers.py:151-308]
                    └─ plantilla de frase (ES/EN)  → MCPResponse
```

### 1.2 Componentes (ruta y responsabilidad)

| Componente | Archivo | Rol |
|---|---|---|
| `AmbientWatchService` | `ambient_watch_service.py` | Watchdog 0.5 s: sensores + motion → `AmbientPrediction` (risk + detections) → publica `camera_alert` |
| `SimulatedSensorBus` | `sensor_bus.py` | Baseline determinista (temp 22.4, smoke 0.02, gate/door cerrados, pet 0.12) |
| `EventHub` | `event_hub.py` | pub/sub in-process (`asyncio.Queue`) |
| `MemoryBridge` | `memory_bridge.py` | Suscriptor pasivo: mapea alertas HIGH/CRITICAL → `MemoryRecord`, **coalesce** en episodios |
| `MemoryRecord` | `memory_service.py:26` | `id, timestamp, location, source, detections[(label,confidence)], risk, model_analysis` |
| `VectorMemoryService` | `memory_service.py:87` | Store en memoria + `embed_text()` sha256 256-D + coseno; búsqueda, last_seen, counts, top_events, forget |
| `MemoryVectorStorePort` | `memory_service.py:63` | Contrato **Qdrant Edge futuro** (no implementado): upsert/query/delete, Cosine, filtros payload |
| `MemoryIntentClassifier` | `memory_intent.py:192` | Clasificador string/regex → 8 `MemoryIntentType` (puro domain) |
| `memory_resolvers` | `memory_resolvers.py` | 4 tools + router `converse`; narrativas plantilla ES/EN |
| `demo_seed_service` | `demo_seed_service.py` | 5 memorias deterministas (pet/smoke/gate/fall/elderly) |
| API | `main.py:188-217` | `/api/demo/seed`, `/api/converse` |
| MCP tools | `tools.py:188-283` | `memory_last_seen`, `memory_search`, `memory_summary`, `memory_converse` |
| Skill | `alexa_skill/skill.json` | Manifest Alexa+ MCP `2025-11-25` |

### 1.3 Capacidades disponibles hoy (inventario)

**Almacenamiento (`VectorMemoryService`):** `store_memory`, `search_memory(query,limit,min_score,location,risk)`, `last_seen(label,location,source)`, `count_occurrences(label,since,location)`, `label_counts(since,location)`, `count_events(risk,since,location)`, `top_events(since,location,limit)`, `recent_high_risk_events`, `recent_critical_events`, `forget_memory`, `size`.

**Embedding:** `embed_text()` — hashed TF, L2-normalizado, determinista, sin red.

**Evento observado (`camera_alert`):** `kind, tool, status/risk, location, source, detections, motion_score, announcement, model_analysis, safety_gate_signals, safety_gate_recommendation, ts`.

**Clasificación:** 8 intents (`LAST_SEEN, SEARCH, SUMMARY, TOP_EVENTS, HIGH_RISK, CRITICAL_RISK, EVENT_COUNT, CURRENT_STATE`).

---

## 2. Diagnóstico (preguntas 1–3)

### 2.1 Qué YA soporta recall-centric (activos reutilizables)

1. **Separación almacenamiento/razonamiento**: `VectorMemoryService` ya es una API de *retrieval* rica; los resolvers solo la *consumen*. → El Recall Engine puede vivir encima sin tocar el store.
2. **Determinismo puro**: `embed_text` + coseno + filtros + `time.time()` acotado = razonamiento reproducible y auditable. Alineado con QFP.
3. **Episodios, parcialmente**: `MemoryBridge` ya *coalesce* ticks en un episodio con `_episode_key=(location, labels)` y `_merge_detections`. → Existe la semilla del modelo episódico.
4. **Datos ricos por observación**: `detections[]` (label+confidence), `risk`, `model_analysis`, `source`, `ts`. → Suficiente para evidencia.
5. **MCP-ready**: la capa de tools/resolvers ya devuelve `MCPResponse` con `MCPContentItem` → extensible a *evidence blocks*.
6. **Seed determinista**: `demo_seed_service` permite razonar sobre memoria poblada en demo sin depender de eventos vivos.

### 2.2 Qué LIMITA el razonamiento (brechas)

| # | Brecha | Evidencia | Efecto |
|---|---|---|---|
| G1 | **Intento único (intent-centric)** | `classify()` devuelve **un** `MemoryIntent` | “¿qué cámaras vieron el mismo evento?” y “¿qué pasó antes?” no caben en 1 intent |
| G2 | **Respuesta por plantilla** | `memory_resolvers.py` construye frases fijas por intent | No hay síntesis multi-registro ni razonamiento temporal/espacial |
| G3 | **`location` pobre / hardcodeada** | `AmbientWatchService` publica `"location":"camera"` (`:322`); seed mezcla `patio/kitchen/living/cam-01` | Memoria **espacial** casi nula; todo cae en “camera” |
| G4 | **Sin identidad de cámara** | `source` = `live`/`simulation`; no hay `camera_id` | No se puede correlacionar multi-cámara |
| G5 | **Sin coordenadas/región** | `detections` solo `{label, confidence}` | No hay “cerca de la piscina” |
| G6 | **Episodio no persistido** | `MemoryBridge._episodes` es un dict en RAM, efímero | El timeline no puede reconstruir episodios tras reinicio; sin `episode_id` en el record |
| G7 | **Sin timeline primitive** | No hay slice ordenado por ventana arbitraria + gaps | “¿qué ocurrió antes de X?” se resuelve parcial/indirecto |
| G8 | **Sin correlación** | Ninguna op agrupa por proximidad temporal/espacial entre fuentes | Caso 4 irresoluble hoy |
| G9 | **Evidencia no expuesta** | Se responde en prosa; no se adjuntan record-id/ts/camera | Baja **trazabilidad** y confianza del jurado/Alexa+ |
| G10 | **Sin plan de recall** | El intent es la única estructura intermedia | No se pueden **componer** operaciones (retrieve → relate → synthesize) |
| G11 | **Converse sin estado** | Cada query es stateless | “mientras estaba fuera” no tiene ancla temporal de sesión |

### 2.3 Capacidades subutilizadas (poder latente)

- `search_memory(min_score, location, risk)` — **filtros** casi no usados (converse solo pasa `location`).
- `count_occurrences`, `label_counts`, `count_events`, `top_events`, `recent_high_risk/critical` — agregación ya lista para *summaries* ricos.
- `MemoryVectorStorePort` — contrato listo para el **swap a Qdrant Edge** sin cambiar resolvers.
- `embed_text` — similitud semántica determinista ya disponible para *ranking* multi-señal.
- `_merge_detections` — base para **fusión de evidencia**.
- `safety_gate_signals` / `recommendation` en el evento — **explicabilidad** ya calculada y descartada al persistir.

---

## 3. Principios de diseño (reglas no negociables)

1. **Evolucionar, no reemplazar.** `MemoryBridge`, `VectorMemoryService`, `MemoryRecord`, `MemoryConverse` permanecen; V2 es aditivo.
2. **Determinismo primero.** Retrieval y relación son **puros y sin LLM**. Sin regex nuevos, sin IF/THEN gigantes, sin placeholders, sin hardcodeos.
3. **Evidencia antes que prosa.** Toda afirmación cita `(record_id, ts, source, label, confidence)`.
4. **Una sola fuente de verdad.** El store local manda; el LLM (Bedrock) no introduce hechos.
5. **Compatibilidad total.** Los 4 tools y sus esquemas siguen funcionando; V2 añade rutas nuevas.
6. **Trazabilidad.** Cada respuesta puede reconstruirse a partir de la memoria persistida (reproducible/testeable).
7. **MCP-nativo.** La salida sigue siendo `MCPResponse`/`MCPContentItem`; se extiende con bloques estructurados.
8. **Alineación Alexa+.** La salida se piensa como *utterance + card* de Alexa+, no como log de CCTV.

---

## 4. Arquitectura objetivo (TO-BE) — el pipeline recall-centric

```
                         ┌───────────────────────────────────────────────┐
  query (ES/EN) ─────▶   │  1. UNDERSTAND  (determinista, puro)          │
                         │     tokens + entidades + tiempo + relación     │
                         └───────────────────────┬───────────────────────┘
                                                 ▼
                         ┌───────────────────────────────────────────────┐
                         │  2. RECALL PLAN  (declarativo, NO un intent)   │
                         │     ops[] + relations[] + window + evidence?   │
                         └───────────────────────┬───────────────────────┘
                                                 ▼
   VectorMemoryService ◀── 3. RETRIEVE (primitivas existentes + slices)   │
                                                 ▼
                         ┌───────────────────────────────────────────────┐
                         │  4. RELATE   episodes · timeline · espacio ·   │
                         │              correlación multi-fuente          │
                         └───────────────────────┬───────────────────────┘
                                                 ▼
                         ┌───────────────────────────────────────────────┐
                         │  5. SYNTHESIZE  narrativa evidence-first       │
                         │     (determinista; LLM opcional tras QFP)      │
                         └───────────────────────┬───────────────────────┘
                                                 ▼
                         ┌───────────────────────────────────────────────┐
                         │  6. RESPOND   MCPResponse = texto + evidence   │
                         │               (utterance + card Alexa+)        │
                         └───────────────────────────────────────────────┘
```

**Diferencia clave vs V1:** donde hoy hay `classify → resolver`, V2 inserta `understand → recall_plan → retrieve → relate → synthesize → respond`, de modo que **una pregunta puede componer varias operaciones** y **varias memorias** en una respuesta razonada.

**Compatibilidad:** `memory_converse` conserva su contrato externo; internamente delega al Recall Engine y, si este no cubre el caso, cae al routing V1 (`MemoryIntentClassifier`). Los tools `memory_search/last_seen/summary` siguen siendo públicos y se convierten en *ops* del engine.

---

## 5. Recall Engine (preguntas 4 y 9)

### 5.1 Estructura intermedia: `RecallPlan`

> Diseño (no código). Sustituye al `MemoryIntent` único por un plan **componible**.

```
RecallPlan {
  lang: "es" | "en"
  window: { since: ts?, until: ts?, hours: float?, anchor: "now"|"session_start"|ts? }
  entities: [ { kind: "label"|"zone"|"camera"|"free_text", value, confidence } ]
  ops: [ RetrieveOp ]            # 0..n, se ejecutan y se unen
  relations: [ "episode", "timeline", "spatial", "correlation", "before_after" ]
  intent_hints: { aggregation?: "count"|"list"|"summary", evidence: bool }
}

RetrieveOp ∈ {
  LastSeen(entity, filters)          # → last_seen()
  Occurrences(entity, window)        # → count_occurrences()/search_memory()
  Range(window, filters)             # → slice temporal (nuevo, sobre records)
  Top(window, risk?)                 # → top_events()/recent_*()
  Aggregate(group_by=label|zone|camera, window)  # → label_counts()
  CurrentState()                     # → watch.last_state
}
```

`RecallPlan` es **declarativo y serializable** → testeable, trazable y registrable (ideal para el jurado y para depurar).

### 5.2 `understand()` — cómo sin reglas rígidas

- **Normalización + tokenización** reutilizando el enfoque ya existente (`memory_intent.py`), pero produciendo **slots múltiples** en lugar de un enum.
- **Entidades**: reutiliza `_LABEL_TERMS` (mascota→PET, reja→GATE_OPEN…), extendido a **zonas** (`piscina`, `corredor norte`, `cocina`, `patio`) y a **cámaras** (`cam-03`).
- **Tiempo**: un único parser de expresiones (`hace 4 minutos`, `últimas 2 horas`, `ayer`, `mientras estaba fuera`→`anchor: session_start`).
- **Composición**: si la frase contiene *más de una* señal (p.ej. mascota + “dónde” + “antes”), se emiten **varias ops + relations**, no se elige una.
- **Fallback sin reglas nuevas**: si no hay match, la op por defecto es `Range(now-24h) + search_memory(free_text)` (comportamiento SEARCH actual, garantizado).

> **Regla anti-“árbol IF/THEN”: el parser produce *slots*, no *ramas*. El motor compone ops a partir de slots; añadir un caso ≠ añadir un `if`.**

### 5.3 `retrieve()` — reutilización máxima

Todas las ops mapean a primitivas **ya existentes** (§1.3). Lo único nuevo con estado es un **`Range(window, filters)`** que rebanada `_records` por `timestamp` (trivial, O(n), determinista). Sin dependencias nuevas.

### 5.4 `relate()` y `synthesize()` — ver §7–§10.

### 5.5 Caso 9 — “¿Dónde vi mi mascota?” sin reglas rígidas

- `understand` → `entities=[{label:PET}]`, `relations=[spatial, episode, history]`.
- `ops` → `LastSeen(PET)` + `Occurrences(PET, window=7d)` + `Range(window=7d, filters=label PET)`.
- `retrieve` → registros reales con `timestamp`, `source`, `location`.
- `relate` → agrupar en episodios por proximidad temporal; ordenar; tomar ubicación actual + anterior + cámara por episodio.
- `synthesize` → *“La última observación fue {relative_time} cerca de {zona} por {camera_id}. Antes apareció en {zona_previa}.”*
- **No hay** una regla “si pregunta mascota → responde Y”; hay un **plan** que cualquier pregunta sobre PET ejecuta igual.

---

## 6. Evolución de `MemoryRecord` y compatibilidad (preguntas 5 y 6)

### 6.1 Campos aditivos (con defaults → V1 sigue válido)

```
MemoryRecord (V2, todos los nuevos OPCIONALES con default):
  id, timestamp, location, source, detections, risk, model_analysis   # V1 intacto
  + camera_id: str | None          # "cam-01" (Vivotek), "cam-phone", "cam-03"
  + zone: str | None               # "pool", "north_corridor", "kitchen"…
  + region: tuple | None           # (x,y,w,h) o zonas espaciales si hay bbox
  + episode_id: str | None         # enlace al episodio persistido
  + event_id: str | None           # correlación del MISMO evento entre fuentes
  + sensor_snapshot: dict | None   # temp/smoke/gate/door/pet del instante
  + embedding_version: int = 1     # versiona embed_text para migraciones futuras
```

> El store construye con **keywords** (`memory_bridge.py:67`), así que añadir campos con default **no rompe** V1. Los records viejos conviven con `camera_id/zone/episode_id = None` y el motor degrada con gracia (usa `location` como zona por defecto).

### 6.2 Relacionar Android / Vivotek / sensores / eventos / episodios (Q6)

| Fuente | Cómo se marca | Cómo se relaciona |
|---|---|---|
| Vivotek | `camera_id="cam-01"`, `zone` de mapa | Por `zone` + `ts` |
| Android (phone) | `camera_id="cam-phone"`, `zone` móvil | Por `zone` + `ts` |
| Sensores | `sensor_snapshot` en el record | Por `ts` (contexto del mismo tick) |
| Eventos `camera_alert` | `event_id` (hash de kind+ts+zone) | Correlación multi-cámara por `event_id`+ventana |
| Episodios | `episode_id` persistido | Agrupa records contiguos (`MemoryBridge` ya lo calcula) |

**Compatibilidad**: todo es metadato añadido. `detections`, `risk`, `model_analysis` no cambian; los resolvers V1 siguen leyendo los mismos campos.

---

## 7. Timeline Engine (preguntas 7 y 5)

### 7.1 Objetivo
Reconstruir secuencias reales: *“¿qué ocurrió antes de la caída?”* y *“¿qué pasó mientras estaba fuera?”*.

### 7.2 Diseño
- **Slice temporal**: `Range(window, filters)` → lista ordenada por `ts` ascendente.
- **Segmentación episódica**: reutiliza la noción de `episode_gap` (30 s, ya en `memory_bridge.py:31`) para agrupar records en **episodios** (inicio–fin–zona–riesgo–labels).
- **Normalización temporal**: `since/until` absolutos o relativos; `anchor = session_start` cuando la pregunta dice “mientras estaba fuera” (se ancla al inicio de la sesión MCP).
- **Ventanas y gaps**: marca silencios (“sin actividad entre las 14:00 y las 15:30”).
- **Relación `before_after`**: dado un `event` (p.ej. FALL), devuelve los episodios previos dentro de la ventana.

### 7.3 Caso 5 — “¿Qué ocurrió antes de la caída?”
1. `retrieve` el evento FALL (último, o el identificado).
2. `Range(until=ts_fall, window=±2h)`.
3. `timeline` → episodios previos ordenados + gaps.
4. `synthesize` → *“Antes de la caída: a las 15:02 hubo movimiento en el corredor (cam-03); a las 15:10 la puerta se abrió (cam-01); a las 15:14 ocurrió la caída.”*

---

## 8. Memoria espacial (preguntas 5 y 6)

### 8.1 Jerarquía espacial (nueva, determinista)

```
Home
 ├─ zone: "living"        ← camera_id "cam-01", "cam-phone"
 ├─ zone: "kitchen"       ← camera_id "cam-02"
 ├─ zone: "north_corridor"← camera_id "cam-03"
 ├─ zone: "pool" | "patio"← camera_id "cam-04"
 └─ (móvil)               ← camera_id "cam-phone", zone dinámica
```

- **Mapa cámara→zona** (config estática, sin dependencias): `camera_id → zone`.
- **Zona en el record**: `zone` derivado en `MemoryBridge` (o en el watchdog) desde `camera_id`.
- **Región/objeto**: si una detección trae bbox, se mapea a una **descripción espacial** (“cerca de la piscina”).

### 8.2 Caso 1 — “¿Dónde vi mi mascota?”
`LastSeen(PET, zone?)` + `Occurrences(PET, 7d)` → ubicación actual + anteriores + cámara + tiempo, **todo desde evidencia**.

### 8.3 Corrección crítica (quick win)
Hoy `AmbientWatchService` publica `"location":"camera"` (`:322`). Debe publicar la **zona real** (`camera_id → zone`) para que la memoria espacial tenga sentido. Es un cambio de **dato**, no de arquitectura.

---

## 9. Correlación multi-fuente (pregunta 6 y caso 4)

### 9.1 Objetivo
*“¿Qué cámaras observaron el mismo evento?”* → **correlación temporal + espacial + evidencia**.

### 9.2 Diseño
- **Correlación temporal**: dos records “son el mismo evento” si `|ts_a − ts_b| ≤ Δ` (p.ej. 5 s) **y** comparten al menos un `label` de la firma.
- **Correlación espacial**: adyacencia de `zone` (mapa de vecindad: `patio↔pool`, `living↔north_corridor`).
- **Firma de evento**: `event_id = hash(kind, bucket(ts, Δ), signature(labels))` → agrupa observaciones del mismo suceso entre cámaras.
- **Salida**: cluster `{event_id, zonas[], cameras[], t_inicio, t_fin, labels[], evidence[]}`.

### 9.3 Caso 4
`Range(window) → relate(correlation Δ=5s + spatial adjacency) → synthesize` → *“El mismo evento fue observado por cam-01 (patio) y cam-04 (pool) entre 15:02:03 y 15:02:11; evidencia: [mem-a, mem-b].”*

> Coste: O(n) con índice por *time bucket*; no hay O(n²).

---

## 10. Evidence-First Reasoning (pregunta 8)

### 10.1 Objeto de evidencia

```
Evidence {
  record_id, ts, camera_id, zone, labels[], risk, snippet(model_analysis),
  confidence, source
}
```

### 10.2 Reglas
1. **Toda frase** narrativa se genera **desde** ≥1 `Evidence`; ninguna afirmación sin respaldo.
2. La salida MCP lleva **dos bloques**: (a) `text/plain` (utterance para Alexa+), (b) `text/json` (evidence cards: ids, ts, zona, cámara, confianza).
3. **Trust/abstain**: si no hay evidencia, se responde “no tengo recuerdos de eso”, **nunca** se alucina (determinismo).
4. **Orden por relevancia**: severidad → recencia → score semántico (ya disponibles).

### 10.3 Caso 3 — “¿Dónde ocurrió la caída?”
`find(FALL) → Evidence{zone, ts, camera_id, labels, risk, snippet}` → *“La caída ocurrió {relative_time} en {zone}, observada por {camera_id}. Evidencia: registro {id} (confianza {c}).”* — ubicación, momento, cámara y evidencia explícitos.

---

## 11. Paradigma teach / remember / recall sin copiar `sc-on-device-ai-memory` (pregunta 10)

| Fase | En EchoMind V2 | Nota |
|---|---|---|
| **remember** | Ya existe: `MemoryBridge → VectorMemoryService` | Es el corazón actual; se mantiene |
| **recall** | Nuevo **Recall Engine** (§5) sobre las primitivas existentes | Aporta *plan + relate + evidence* |
| **teach** | **Diferido / no requerido** | V1 ya concluyó que *teach* no es necesario para el claro storytelling de Alexa+; evitamos copiar arquitecturas ajenas |

**Qué NO copiamos de `sc-on-device-ai-memory`:** su modelo on-device de grafo/entidades, su API de “teach facts” explícita y su almacenamiento específico. EchoMind se distingue por: **recall determinista sobre memoria episódica espacial observada por sensores**, con **evidencia** y **QFP**, y con **MCP/Alexa+** como superficie.

---

## 12. Mapeo de los 5 casos objetivo

| Caso | Plan (ops) | Relations | Salida |
|---|---|---|---|
| 1 ¿Dónde vi mi mascota? | `LastSeen(PET)` + `Occurrences(PET,7d)` | spatial, episode, history | zona+tiempo+cámara actual y anterior |
| 2 ¿Qué pasó mientras estaba fuera? | `Range(anchor=session_start)` + `Aggregate(label)` | timeline | resumen temporal desde recuerdos reales |
| 3 ¿Dónde ocurrió la caída? | `Range(FALL)` | evidence | ubicación+momento+cámara+evidencia |
| 4 ¿Qué cámaras vieron el mismo evento? | `Range(window)` | correlation(Δ,spatial) | cluster multi-cámara + evidencia |
| 5 ¿Qué ocurrió antes de la caída? | `Range(until=ts_fall,±2h)` | timeline, before_after | timeline reconstruido |

Ninguno requiere regex nuevos ni árboles IF/THEN: todos son **planes** sobre operaciones genéricas.

---

## 13. Roadmap por fases

> Cada fase es **aditiva** y deja V1 funcionando; se puede parar en cualquier punto.

| Fase | Alcance | Rompe algo | Entrega |
|---|---|---|---|
| **A. Recall Plan + Understand** | `RecallPlan`, `understand()` multi-slot, `retrieve()` sobre ops existentes; `memory_converse` delega al engine con *fallback* a V1 | No | Casos 1,2,3,5 (básico) |
| **B. Evidence-First** | `Evidence`, bloques MCP `text/json`, trust/abstain | No | Trazabilidad (caso 3 pleno) |
| **C. Episodios persistidos + Timeline** | `episode_id` en record; Timeline Engine | No (defaults) | Casos 2,5 plenos |
| **D. Memoria espacial** | `camera_id`/`zone` en record; mapa cámara→zona; `location` real en watchdog | No (datos) | Casos 1,4 (espacial) |
| **E. Correlación multi-fuente** | `event_id`, vecindad espacial, clusters | No | Caso 4 pleno |
| **F. MCP surfacing + Alexa+ cards** | tools `memory_recall`/`memory_timeline`/`memory_evidence`; utterances+cards | No (nuevos tools) | Producto |
| **G. Qdrant Edge** | Implementar `MemoryVectorStorePort` y hacer *swap* | No | Escala |

---

## 14. Riesgos y mitigaciones

| Riesgo | Sev. | Mitigación |
|---|---|---|
| **“Regex creep” / árboles IF/THEN** | Alta | Parser produce **slots**, no ramas; revisión estricta; test de composición |
| **Pérdida de determinismo** | Alta | Retrieval/relación puros; LLM solo síntesis opcional tras QFP; semillas fijas en tests |
| **Romper V1 / MCP** | Alta | Campos `MemoryRecord` con default; `memory_converse` con *fallback* a routing V1; contratos MCP intactos |
| **Rendimiento O(n) / correlación** | Media | Índice por *time bucket*; límites top-k; cache por ventana |
| **Ambigüedad multi-intent** | Media | El plan es una **unión** de ops; la incertidumbre se resuelve en `synthesize`, no eligiendo |
| **Sobrealcance** | Media | Roadmap por fases con *stop* válido; nada de reescribir el store |
| **Metadatos espaciales inventados** | Media | `zone` derivado de config **estática** verificable; degradar con gracia si falta |
| **Coste/privacidad** | Baja | Todo local; sin red en retrieval |

---

## 15. Quick wins (sin cambiar arquitectura)

1. **`location` real en `camera_alert`** (de “camera” → zona): arregla de raíz la memoria espacial (cambio de dato).
2. **Exponer evidencia** (ids+ts+cámara) en las respuestas actuales: trazabilidad inmediata ante el jurado.
3. **“Observación anterior” en `last_seen`**: segunda ocurrencia → caso 1 casi completo.
4. **Usar `min_score`/`risk` de `search_memory`** en `converse`: mejor precisión de recuperación.
5. **`camera_id` en el record** desde `source`/config: habilita correlación futura con coste mínimo.

---

## 16. vNext (después del hackathon)

- **Recall Engine completo** con `RecallPlan` serializable + registro de planes (auditoría).
- **Memoria semántica** vía embeddings Bedrock (Titan) tras el `MemoryVectorStorePort`, manteniendo el fallback hashed.
- **Grafo de memoria** (entidades↔zonas↔episodios) en Qdrant Edge con payload filters.
- **MCP Apps / cards** en Alexa+ (carousels de evidencia).
- **Teach** *opcional* (si un caso de negocio lo exige), sin copiar arquitecturas de terceros.

---

## 17. Impacto en Alexa+ Track (pregunta 11)

| Criterio del jurado | Cómo V2 lo refuerza |
|---|---|
| **Context awareness** | Plan de recall con entidades/ventanas/relaciones en vez de 1 intent |
| **State across sessions** (*citado como “creative”*) | Episodios + timeline persistidos; ancla `session_start` |
| **Agentic workflows** (*“orchestrates across services autonomously”*) | Retrieval → relate → synthesize como workflow determinista y componible |
| **Memory / Orchestration** | Es literalmente el núcleo: memoria episódica espacial razonada |
| **Distinción “obvious” vs “creative”** | Deja de parecer “basic MCP wrapper” / “single-turn Q&A” |
| **Trust** | Evidence-first: cada respuesta demuestra de dónde sale |

## 18. Impacto en AWS Builder (pregunta 12)

| Criterio | Cómo V2 lo refuerza |
|---|---|
| **Bedrock no-“obvious”** | Bedrock pasa de “una llamada de texto” a **capa de síntesis de un pipeline de retrieval** (RAG sobre memoria del hogar) — ejemplo “creative” |
| **Multi-servicio/orquestación** | Bedrock + (opcional) AgentCore sobre un motor de memoria; narración sobre evidencia recuperada |
| **QFP** | El engine funciona **sin** Bedrock → resiliencia demostrable y diferenciadora |
| **Documentable** | El propio diseño (plan→retrieve→relate→synthesize) es un *patrón de integración* citable en Product Feedback |

> **Conclusión (pregunta central).** EchoMind V2 = **memoria espacial conversacional basada en evidencia** construida *encima* de V1: se preserva el determinismo (retrieval/relación puros, LLM solo opcional y sin verdad), la trazabilidad (evidence), la compatibilidad MCP (contratos intactos + tools nuevos) y la alineación Alexa+ (utterance + cards + state across sessions). El riesgo se controla con un **roadmap por fases** y la regla **“slots, no ramas”**.

---

## 19. Decisiones abiertas (requieren tu criterio)

1. **Alcance de fases A–E** antes del 23 OCT vs. solo diseño (fase A + quick wins).
2. **`location` real** en el watchdog: ¿zona fija por cámara o zona dinámica del móvil?
3. **Ventana de correlación Δ** (p.ej. 5 s) y **mapa de vecindad** de zonas: ¿definir cuáles?
4. **Salida de evidencia** en MCP: ¿bloque `text/json` (lo más simple) o `MCPContentItem` tipado nuevo?
5. **Bedrock en síntesis**: ¿habilitar narración LLM opcional tras QFP o mantener 100% determinista para la demo?
