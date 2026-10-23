# DIAGRAM FINAL PACKAGE — EchoMind V2

> Reconstrucción de los 5 diagramas de arquitectura **desde el código real**.
> Este documento va **primero** (descripción por diagrama) y los SVG después.
>
> **Fuente de verdad**: el código de `src/` y, como apoyo, los documentos
> `ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md`, `MEMORY_EXPERIENCE_VALIDATION.md`,
> `A7C_QUERY_ROUTER_ARCHITECTURE.md` y `A7D_IMPLEMENTATION_REPORT.md`.
> Cuando un documento contradice al código, **manda el código**.
>
> **Nota de alcance**: los artefactos referenciados en la revisión previa
> (`DIAGRAM_MASTER_REVIEW.md`, `hero.svg`, `system-architecture.svg`,
> `memory-reasoning.svg`, `query-router.svg`, `domain-erd.svg`,
> `test-growth.svg`, `quota-fallback.svg`) **no existen** en el repositorio.
> Por tanto las inconsistencias citadas como C1/C5/C8/C9/C10/C14 **no pueden
> citarse ni resolverse**: se dejan constancia aquí, no se inventan. Los
> diagramas `test-growth.svg` y `quota-fallback.svg` quedan **fuera** del
> paquete principal (eran diagramas métricos, no de arquitectura).
>
> **Objetivo**: que un juez de Amazon entienda EchoMind V2 en menos de 60 s.
> **Sin inventar** entidades, relaciones ni arquitectura. Sin commits, sin push.

---

## 0. Hechos del sistema (verificados en código)

- **Entrada**: `src/main.py:compose()` (composition root hexagonal). Rutas MCP
  `GET/POST /mcp` (`fastapi_mcp_adapter.py`) más rutas HTTP auxiliares
  (`/api/converse`, `/api/recall`, `/dashboard`, `/api/cam/*`).
- **Superficie Alexa+/MCP**: `AGENTIC_TOOL_CATALOG` (`src/domain/models/tools.py`)
  con 9 herramientas; las 5 de memoria están en `MEMORY_TOOL_NAMES`.
- **Watchdog**: `AmbientWatchService` (cámara + sensores → predicción →
  `camera_alert` en `EventHub`).
- **Puente de memoria**: `MemoryBridge` (suscriptor pasivo de `EventHub`,
  persiste HIGH/CRITICAL coalescidos en `VectorMemoryService`).
- **Dos canales de memoria paralelos**: V1 `memory_converse` y V2
  `memory_recall` (plan → retrieve → relate → synthesize).
- **Router (A7C)**: `route_query` decide `CURRENT_STATE` vs `RECALL`.
- **Response intent (A7D)**: `resolve_intent` da forma a la respuesta.

---

## 1. `hero.svg` — Vista de portada

### Descripción
Diagrama de una sola mirada: el viaje completo de una pregunta de Alexa+ hasta
una respuesta honesta, pasando por las dos fuentes de verdad (estado en vivo y
memoria histórica). No es un diagrama de cajas exhaustivo: es el **titular**.

### Propósito
Que un juez entienda en <60 s **qué es** EchoMind V2: un ecosistema de hogar
con memoria primero, determinista, bilingüe y sin LLM en la ruta de memoria,
operativo 24/7 incluso con cuota agotada.

### Entidades incluidas (todas reales)
- **Alexa+** (cliente MCP externo).
- **MCP Streamable HTTP** (`FastAPIMCPServer`, endpoint `/mcp`).
- **Query Router** (`route_query`, `query_router.py`) — la bifurcación.
- **Current State** (`current_state_reasoning.render_state_answer` desde
  `watch.last_state`).
- **Memory Recall** (`recall()` → `RecallEngine`).
- **Memoria local vectorial** (`VectorMemoryService`).
- **AWS Bedrock** (adaptador de LLM, solo para herramientas multimodales/ambiente;
  **no** en la ruta de memoria).
- Etiqueta del **Quota Fallback** (`ResilientLLMAdapter` → `RuleBasedLLMAdapter`).

### Relaciones incluidas
- Alexa+ → MCP (`tools/call`).
- MCP → Router.
- Router → Current State (estado en vivo) / Router → Recall (historia).
- Recall → VectorMemoryService (lectura).
- Watchdog/Bridge → VectorMemoryService (escritura) — mostrado como la
  procedencia de los datos que Recall lee.
- Bedrock con flecha punteada = **opcional / fuera de la ruta de memoria**.

### Justificación arquitectónica
El corazón del producto es la **separación de fuentes de verdad**: una pregunta
de presente se responde del snapshot (`watch.last_state`) y una de pasado de la
memoria. El hero debe mostrar esa bifurcación porque es la decisión de diseño
que define EchoMind V2 y la que hace la respuesta auditable.

---

## 2. `system-architecture.svg` — Arquitectura por capas

### Descripción
Diagrama hexagonal por capas: entradas/salidas, adaptadores MCP, capa de
servicios de infraestructura, dominio puro y el bot del navegador. Muestra el
flujo de datos en producción de extremo a extremo.

### Propósito
Probar la **arquitectura hexagonal real**: dominio puro (stdlib) sin frameworks,
puertos de salida y adaptadores que implementan la IO.

### Entidades incluidas (rutas verificadas)
**Entradas (dispositivos / transporte)**
- Android (IP Webcam) → `HttpPhoneCameraAdapter` (`/api/cam/phone/*`).
- Vivotek FD8367 → `VivotekCameraAdapter` (`/api/cam/vivotek/*`).
- Alexa+ → `FastAPIMCPServer` (`/mcp`).

**Adaptadores**
- `adapters/aws/bedrock_adapter.py` (`BedrockLLMAdapter`).
- `adapters/aws/fallback_llm_adapter.py` (`ResilientLLMAdapter`,
  `RuleBasedLLMAdapter`).
- `adapters/camera/http_phone_camera_adapter.py`.
- `adapters/iot/vivotek_adapter.py`.
- `adapters/mcp/fastapi_mcp_adapter.py` (`InMemoryMCPServer`, `FastAPIMCPServer`).
- `adapters/mcp/memory_resolvers.py` (`memory_converse` + V1 tools).
- `adapters/mcp/recall_resolvers.py` (`memory_recall`).
- `adapters/mcp/tool_resolvers.py` (catálogo agéntico + ambiente + recordatorios).
- `adapters/mcp/web_dashboard.py` (Control Center `/dashboard`).
- `adapters/mcp/session_manager.py` (`SessionManager`).

**Servicios de infraestructura**
- `services/ambient_watch_service.py` (`AmbientWatchService`).
- `services/memory_bridge.py` (`MemoryBridge`).
- `services/memory_service.py` (`VectorMemoryService`, `MemoryRecord`).
- `services/memory_timeline.py` (`Episode`, `TimelineGap`, `build_episodes`).
- `services/recall_engine.py` (`RecallEngine`).
- `services/sensor_bus.py` (`SimulatedSensorBus`, `SensorData`).
- `services/demo_seed_service.py` (`seed_demo_memory`).
- `config/event_hub.py` (`EventHub`), `config/telemetry.py` (`Telemetry`).

**Dominio puro (servicios, sin IO)**
- `memory_intent.py` (`MemoryIntentClassifier`).
- `query_router.py` (`route_query`).
- `recall_planner.py` (`understand`), `recall_plan.py` (`RecallPlan`),
  `response_intent.py` (`resolve_intent`/`derive_intent`).
- `recall_synthesis.py` (`render_synthesis`).
- `evidence.py`, `context.py`, `context_narrative.py`, `relation.py`,
  `relation_rules.py`, `memory_anchor.py`, `memory_spatial.py`,
  `current_state_reasoning.py`.

**Puertos de salida**
- `domain/ports/output/mcp_port.py` (`MCPServerPort`).
- `domain/ports/output/llm_port.py` (`LLMServicePort`).

**Salidas**
- Respuestas MCP a Alexa+.
- Control Center (SSE de `EventHub` en `/dashboard/events`).

### Relaciones incluidas
- Android/Vivotek → sus adaptadores → `AmbientWatchService`.
- `AmbientWatchService` → `EventHub` (publica `camera_alert`) → `MemoryBridge`
  (suscriptor pasivo) → `VectorMemoryService`.
- Alexa+ → `FastAPIMCPServer` → `InMemoryMCPServer` (registro de tools) →
  resolvers → dominio/servicios.
- `ResilientLLMAdapter` envuelve a `BedrockLLMAdapter` con fallback a
  `RuleBasedLLMAdapter` (adaptador, no en la ruta de memoria).
- `main.py` cablea todo (composition root) y monta el dashboard y las rutas de
  cámara.

### Justificación arquitectónica
Es el diagrama que demuestra que la V2 **no rompió** el hexágono: la memoria es
un servicio de infraestructura más, y los demás adaptadores no cambiaron.
También muestra por qué el sistema vive sin AWS: el watchdog y el bridge son
lógica de borde.

---

## 3. `memory-reasoning.svg` — Canal de recall (data → relations → context → narration → synthesis)

### Descripción
El pipeline V2 completo de memoria, desde la pregunta hasta la respuesta
sintetizada, con las estructuras de dominio que se construyen en cada paso.

### Propósito
Mostrar que la respuesta de memoria es **determinista y basada en evidencia**:
cada paso tiene una estructura auditable y nada se inventa.

### Entidades incluidas
- **`understand()`** (`recall_planner.py`) → **`RecallPlan`** (`recall_plan.py`):
  `ops` (`RetrieveKind`: `LAST_SEEN`, `SEARCH`, `RANGE`, `TOP`, `AGGREGATE`,
  `CURRENT_STATE`), `relations` (`RelationKind`: `EPISODE`, `SPATIAL`,
  `CORRELATION`, `TIMELINE`, `BEFORE_AFTER`), `aggregation`, `anchor`,
  `direction`, `state_topic`, `state_polarity`, `response_intent`.
- **`MemoryIntentClassifier`** (`memory_intent.py`) → `MemoryIntent`
  (`MemoryIntentType`).
- **`RecallEngine`** (`recall_engine.py`): ejecuta ops →
  - `VectorMemoryService` (last_seen, search_memory, records_between, top_events,
    count_occurrences, count_events, label_counts).
  - `MemoryRecord` → `Evidence` (`evidence.py`).
  - **`Episode`** (`memory_timeline.build_episodes`) → **`Relation`**
    (`relation_rules.relate_episodes`, vocabulario cerrado en `relation.py`) →
    **`ContextItem`** (`context.build_context`, grados `SIGNAL_MIN`/`NARRATION_MIN`).
- **`resolve_intent`/`derive_intent`** (`response_intent.py`) → `ResponseIntent`.
- **`render_synthesis`** (`recall_synthesis.py`) → `_INTENT_RENDERERS`.
- **`render_context`** (`context_narrative.py`).
- **`render_utterance` / `render_abstention`** (`evidence.py`).
- **`RecallResult`** (`evidence.py`): `utterance`, `evidence`, `trace`, `context`.

### Relaciones incluidas
- Pregunta → `understand` → `RecallPlan`.
- `RecallPlan.ops` → almacén → registros → `Evidence` + `trace`.
- registros → `build_episodes` → `Episode`.
- `Episode` → `relate_episodes` → `Relation` (tipos temporales/espaciales/
  correlacionales) → `build_context` → `ContextItem` (gradado).
- `RecallPlan.response_intent` + traza → `render_synthesis` → respuesta.
- `traza` (`RecallTrace.ops_executed`) alimenta tanto la síntesis como la
  evidencia devuelta por `/api/recall`.

### Justificación arquitectónica
Este es el diagrama de "por qué la memoria razona y no alucina": el vocabulario
de relaciones es **cerrado**, las identidades espaciales **degradan** de forma
explícita (`memory_spatial`), el anclaje **abstiene** sin coincidencia
(`memory_anchor`), y la síntesis **lee la traza** que ya se ejecutó. La
narración (A6f) es la única capa que produce palabras, y solo sobre `ContextItem`
narrable.

---

## 4. `query-router.svg` — Decisión determinista estado vs memoria (A7C)

### Descripción
La tabla de precedencia de `route_query` y cómo se bifurca la respuesta entre
`current_state_reasoning` y el pipeline de memoria.

### Propósito
Explicar la corrección de A7C (bug `¿La reja está cerrada?` →
"No he encontrado recuerdos…") y demostrar que la clasificación es puramente
determinista y auditable.

### Entidades incluidas
- **`route_query`** (`query_router.py`) → **`RouteDecision`**
  (`kind: QueryKind`, `topic: StateTopic`, `lang`, `matched`, `polarity`).
- **Tablas**: `_STATE_SUBJECTS` (`GATE`, `DOOR`, `MOTION`, `TEMPERATURE`,
  `RISK`, `SMOKE`), `_PRESENT_MARKERS`, `_PAST_MARKERS`, `_MEMORY_ANCHORS`,
  `_PERSON_ANCHORS`, `_COUNT_MARKER`, `_OVERVIEW_PHRASES`.
- **`StateTopic`** (`GATE/DOOR/MOTION/TEMPERATURE/RISK/SMOKE/OVERVIEW`).
- **`render_state_answer`** (`current_state_reasoning.py`).
- **`understand`** (`recall_planner.py`) para la rama `RECALL`.
- **`MemoryIntentClassifier`** (detección de idioma + intención).

### Relaciones incluidas
- Orden de precedencia exacto (primer match gana):
  `count > memory-anchor > past > subject+present > overview > default recall`.
- `CURRENT_STATE` → `render_state_answer` (lee `watch.last_state`; **nunca**
  toca el almacén).
- `RECALL` (por defecto seguro) → pipeline de memoria V1/V2 tal cual.
- `polarity` ("open"/"closed") solo elige el prefijo `Sí/No`; el hecho reportado
  nunca cambia.
- Veto de persona: `_PERSON_ANCHORS` bloquea `GATE`/`DOOR` (estado de una cosa)
  pero **no** `MOTION`.

### Justificación arquitectónica
El router es la prueba de que EchoMind distingue "qué pasa ahora" de "qué
pasó": un default `RECALL` garantiza cero regresión V1, y el estado en vivo se
responde solo desde campos reales del snapshot, con degradación honesta ("No
dispongo…") en vez de inventar.

---

## 5. `domain-erd.svg` — Modelo de dominio

### Descripción
Diagrama entidad-relación de las estructuras de dominio puras del pipeline de
memoria, con sus campos reales y sus invariantes.

### Propósito
Documentar el modelo sobre el que se construye toda la razón contextual, sin
dependencias de infraestructura.

### Entidades incluidas (campos reales)
- **`MemoryRecord`** (`memory_service.py`, infra pero es el registro de origen):
  `id`, `timestamp`, `location`, `source`, `detections`, `risk`,
  `model_analysis`, `camera_id?`, `zone?`.
- **`Evidence`** (`evidence.py`): `record_id`, `ts`, `location`, `labels`, `risk`,
  `confidence`, `snippet`, `camera_id?`, `zone?`.
- **`Episode`** (`memory_timeline.py`): `start`, `end`, `location`, `labels`,
  `risk`, `record_ids` (+ `count`, `duration`).
- **`TimelineGap`**: `start`, `end`, `seconds`.
- **`Relation`** (`relation.py`): `kind`, `subject`, `object`, `rule`, `facts`,
  `degraded`, `fallback` — vocabulario cerrado `KNOWN_RELATION_KINDS`
  (`TEMPORAL_KINDS`, `SPATIAL_KINDS`, `CORRELATIONAL_KINDS`), **sin**
  `confidence`.
- **`RelationRule`** (`relation_rules.py`): `id`, `kind`, `description`,
  `salience` (tabla `RELATION_RULES`).
- **`ContextItem`** (`context.py`): `relation`, `salience` (+ `signal`,
  `narratable`, `degraded`).
- **`AnchorRef`** (`memory_anchor.py`): `record_id`, `ts`, `label`, `location`,
  `camera_id?`, `zone?`, `candidates`.
- **`RecallPlan`** (`recall_plan.py`): `lang`, `window` (`TimeWindow`), `entities`
  (`EntitySlot`), `ops` (`RetrieveOp`), `relations`, `aggregation`, `anchor`,
  `direction`, `state_topic`, `state_polarity`, `response_intent`.
- **`RecallResult` / `RecallTrace`** (`evidence.py`).

### Relaciones incluidas
- `MemoryRecord` **1..*** → `Episode` (agrupación por `location`+`labels` y
  `gap_seconds`).
- `Episode` **1..*** → `TimelineGap` (silencios > `max_gap`).
- `Episode` **pairwise** → `Relation` (vía `relate_episodes`; `RelationRule`
  define cada fila).
- `Relation` **1..1** → `ContextItem` (gradado por `salience`).
- `MemoryRecord` → `Evidence`.
- `AnchorRef` se resuelve desde `MemoryRecord` (más reciente con `label`);
  `RecallPlan.anchor` referencia ese `label`.
- `RecallPlan` **1..*** → `RetrieveOp`; **0..*** → `RelationKind`.

### Justificación arquitectónica
La ERD debe mostrar los invariantes que hacen auditable la V2: `Relation` sin
`confidence` (un motor determinista no responde "cuán seguro"), vocabulario de
tipos cerrado, `ContextItem` con dos umbrales (`SIGNAL_MIN`, `NARRATION_MIN`), y
la degradación de identidad espacial (`degraded`/`fallback`) como ciudadano de
primera clase.

---

## 6. Checklist de entrega

- [x] Descripción por diagrama (propósito, entidades, relaciones, justificación).
- [x] Solo entidades/relaciones verificadas en código.
- [x] Constancia de que la revisión previa y los SVG originales **no existen**;
      C1/C5/C8/C9/C10/C14 no se citan ni se inventan.
- [x] `test-growth.svg` y `quota-fallback.svg` excluidos del paquete principal.
- [x] Los 5 SVG (`hero`, `system-architecture`, `memory-reasoning`,
      `query-router`, `domain-erd`) escritos en la raíz del repositorio.
- [x] Validación SVG (XML bien formado, `viewBox`, texto legible).
- [x] Sin commits, sin push, sin tocar código/tests.

---

## 7. Aviso de estado del repositorio

El HEAD actual es `e5559d1` ("feat: A7C current state reasoning and A7D response
intent adapter"). El trabajo A7C/A7D **ya está commiteado** en el repositorio por
una operación previa (no por esta sesión de diagramas). Esta sesión de diagramas
**no** ha tocado código, tests ni hashes; solo añade este documento y, a
continuación, los SVG.
