# A7C — Query Router: arquitectura (análisis, sin implementación)

**Fase:** A7C · **Estado:** análisis aprobado → pendiente de implementación
**Regla dura:** NO se escribió código · sin commits · sin push · HEAD = `b963c5f`
**Protegido (no se rompe):** `memory_converse`, `memory_recall`, Voice Dock, Dashboard, Android, Vivotek

---

## 0. La pregunta central

> **¿Cómo evitar que una pregunta de estado actual sea respondida como una pregunta de memoria?**

Porque el enrutado ocurre **antes de cualquier recuperación** y el rama de estado
**no tiene camino de código hacia la búsqueda**:

1. **Router arriba de ambos canales.** Una sola función pura de dominio decide
   `CURRENT_STATE` vs `RECALL` **antes** de que `MemoryIntentClassifier` (V1) o
   `understand()` (V2) toquen la memoria. La decisión no vive en una tool:
   vive en una capa superior compartida.
2. **El bug actual es un default silencioso.** Hoy, `MemoryIntentClassifier`
   mapea a `CURRENT_STATE` solo frases amplias ("qué ocurre", "qué pasa");
   todo lo demás cae a `SEARCH` → `search_memory()` →
   `"No he encontrado recuerdos para: ¿La reja está cerrada?"`
   (`memory_resolvers.py:211`). El router reemplaza ese default: **sin señal de
   pasado y con sujeto+presente ⇒ estado**, sin señales ⇒ memoria (default seguro).
3. **Precedencia de pasado.** Cualquier marcador temporal pasado
   ("cuándo", "antes de", "mientras", "ha ocurrido", "yesterday"…) gana sobre
   cualquier marcador presente ⇒ una pregunta anclada en el tiempo **nunca**
   puede clasificarse como estado.
4. **Rama de estado sin escape a memoria.** El ramo `CURRENT_STATE` responde
   SOLO desde el snapshot `watch.last_state` y retorna. No existe `if` que lo
   redirija a `search_memory`, `last_seen` o `timeline`. En V2, el plan de estado
   tiene su propia política de síntesis (política 0) que **nunca cae al fallback
   narrativo de evidencia** — la síntesis de estado es irrefutable por
   construcción.
5. **Nada de LLM, nada de inventar.** Tablas de regex + campos reales del
   snapshot; campo ausente ⇒ frase honesta de no-disponibilidad, jamás una
   respuesta de memoria como sustituto.

---

## 1. Clasificación: memoria vs estado actual

### 1.1 Dos ejes

| Eje | Pregunta | Fuente de verdad | Canal |
|---|---|---|---|
| **Tiempo** | ¿habla del AHORA o del PASADO? | presente ⇢ snapshot vivo · pasado ⇢ registros | decide el ROUTER |
| **Fuente** | ¿de dónde se lee? | `watch.last_state` vs `VectorMemoryService` | decide el ejecutor |

El router decide **el dominio** (2 vías). **No** decide qué capacidad de memoria
— eso sigue siendo trabajo de `MemoryIntentClassifier` (8 intenciones) en V1 y
de `understand()`/planner en V2, exactamente como hoy.

### 1.2 Tabla de los 10 ejemplos canónicos

| # | Pregunta | Señales detectadas | Router | Tema (topic) | Capacidad V1/V2 si es RECALL |
|---|---|---|---|---|---|
| M1 | ¿Dónde vi mi mascota? | pasado `vi` + lugar | **RECALL** | — | LAST_SEEN / SPATIAL |
| M2 | ¿Qué ocurrió antes de la caída? | pasado `ocurrió` + `antes` | **RECALL** | — | BEFORE_AFTER + anchor |
| M3 | ¿Qué ocurrió después de la caída? | pasado `ocurrió` + `después` | **RECALL** | — | BEFORE_AFTER + anchor |
| M4 | ¿Qué pasó mientras estaba fuera? | pasado `pasó` + `mientras` | **RECALL** | — | TIMELINE + SESSION_START |
| M5 | ¿Qué cámaras observaron el mismo evento? | pasado `observaron` (o default) | **RECALL** | — | CORRELATION |
| E1 | ¿La reja está cerrada? | sujeto `reja` + presente `está` | **CURRENT_STATE** | `gate` | — |
| E2 | ¿Hay movimiento ahora? | sujeto `movimiento` + `hay`/`ahora` | **CURRENT_STATE** | `motion` | — |
| E3 | ¿Qué temperatura hay? | sujeto `temperatura` + `hay` | **CURRENT_STATE** | `temperature` | — |
| E4 | ¿Cuál es el riesgo actual? | sujeto `riesgo` + `actual` | **CURRENT_STATE** | `risk` | — |
| E5 | ¿Qué ocurre ahora? | frase overview `qué ocurre` + `ahora` | **CURRENT_STATE** | `overview` | — |

### 1.3 Las tres tablas (tabla-driven, como el planner de A1/A7B)

```
_STATE_SUBJECTS   (sujeto → topic)
  gate      ← reja, portón, porton, cancela, gate, front gate
  door      ← puerta, door, front door
  motion    ← movimiento, motion, movement
  temperature ← temperatura, temperature, grados, degrees
  risk      ← riesgo, risk, peligro, danger
  smoke     ← humo, smoke  (ampliación: el snapshot tiene smoke_density)

_PRESENT_MARKERS  (contexto de presente; regex con límite de palabra)
  es: \best[áa]\b, hay, ahora, en este momento, actual, actualmente, ahora mismo
  en: \bis\b, \bare\b, \bnow\b, "right now", currently, "at the moment"

_PAST_MARKERS     (ancla en el tiempo; PREVALECE sobre los presentes)
  es: cuándo, antes, después, despues, mientras, ocurri*, pasó, pasado,
      ha ocurrido, ha estado, estuvo, estaba, viste, vio, ayer, "la última vez"
  en: when, before, after, while, happened, occurred, was, were, has been,
      last time, yesterday

_OVERVIEW_PHRASES (sin sujeto concreto → panorama general)
  es: qué ocurre, qué pasa, qué está pasando, qué sucede, "en general"
  en: what is happening, what's happening, "what is going on", "current state"
```

Regla: **un tema de estado exige (sujeto ∨ overview) AND presente**, salvo que
un marcador pasado gane antes. Las tablas se agregan por fila — añadir un caso
de uso es añadir una fila, nunca tocar un `if`.

---

## 2. Casos ambiguos

| # | Pregunta ambigua | Discusión | Resolución propuesta |
|---|---|---|---|
| A1 | ¿La reja ha estado abierta **hoy**? | sujeto+estado, pero perfecto (historia de hoy) | **RECALL** — `ha estado` es marcador pasado (copula presente `está` ⇒ estado; perfecto `ha estado/was/has been` ⇒ memoria). Hoy lo clasifica `LAST_SEEN` y sigue clasificándolo así. |
| A2 | ¿Qué pasó **ahora**? | pasado + presente a la vez | **RECALL** — el pasado prevalece (regla única y simple; "qué pasó" ancla en tiempo). |
| A3 | ¿Cuántos eventos **hay ahora**? | conteo + presente | **RECALL** — los conteos son operación de memoria (siempre; precedencia del marcador de conteo). `EVENT_COUNT` ya existe. |
| A4 | ¿Cuánto tiempo lleva abierta la reja? | estado + duración | **CURRENT_STATE (parcial honesto)** v1: responde el estado (abierta/cerrada) + `ts` del snapshot; **no** afirma duración (el `ts` es del último tick, no del inicio de la apertura). Fuera de alcance v1: duración real ⇒ requeriría historial ⇒ respuesta honesta de límite. |
| A5 | ¿Todo bien? / ¿Cómo vamos? | sin sujeto, sin pasado | **Default RECALL** en v1 (comportamiento actual, cero regresión). Opción futura: fila `_OVERVIEW_CASUAL` → `overview`. |
| A6 | ¿Hay humo? | sujeto no canónico en la lista original | **CURRENT_STATE** `smoke` (el snapshot tiene `smoke_density` y `SMOKE` en detections). Fila nueva en la tabla — sin tocar el router. |
| A7 | ¿Cuál es el riesgo **ahora y qué pasó hoy**? | compuesta estado+memoria | **v1: RECALL** (pasado prevalece, consistente con A2). Futuro: respuesta compuesta (línea de estado + línea de memoria) — marcada como alcance futuro, no v1. |
| A8 | ¿Se movió alguien? vs ¿Se está moviendo alguien? | perfecto vs progresivo | pasado `se movió` ⇒ **RECALL**; progresivo `está moviendo`+sujeto ⇒ **CURRENT_STATE** `motion`. Cubierto por las tablas `está`/`movimiento`. |
| A9 | ¿Cómo está hoy la reja? | copula presente + "hoy" | **CURRENT_STATE** `gate` — "hoy" **no** es marcador pasado (es de la tabla de resumen V1); el copula `está` manda. |
| A10 | ¿Qué temperatura hubo **ayer**? | pasado + sujeto de estado | **RECALL** — pasado prevalece (aunque V1 no tenga serie de temperatura; cae al pipeline de memoria normal, comportamiento actual). |

Principio de diseño: **las ambiguas se resuelven con UNA regla de precedencia
(conteo > pasado > estado > default)**, no con excepciones. Cada fila ambigua
de la tabla anterior se vuelve un test golden.

---

## 3. Estrategia de routing

### 3.1 Dónde vive

Nuevo módulo **`src/domain/services/query_router.py`** — dominio puro
(stdlib + regex), sin IO, sin estado, sin LLM. Los dos adaptadores lo importan
(dirección de dependencia correcta: infraestructura → dominio).

```python
@dataclass(frozen=True, slots=True)
class RouteDecision:
    kind: Literal["current_state", "recall"]
    topic: str | None        # "gate" | "door" | "motion" | "temperature" |
                             # "risk" | "smoke" | "overview" | None
    lang: str
    matched: tuple[str, ...] # marcadores detectados (auditoría para la traza)

def route_query(text: str, lang: str | None = None) -> RouteDecision: ...
```

### 3.2 Política (primera coincidencia gana — misma filosofía que planner/síntesis)

```
1. query vacía            → RECALL            (hoy: SEARCH, sin cambio)
2. marcador de conteo     → RECALL            (cuántos/how many + eventos/alertas)
3. marcador PASADO        → RECALL            (precedencia absoluta)
4. sujeto de estado
   Y marcador PRESENTE    → CURRENT_STATE + topic
5. frase overview         → CURRENT_STATE + topic="overview"
6. default                → RECALL            (hoy: SEARCH — cero regresión)
```

La **detección de idioma** reutiliza la lógica ya probada de
`MemoryIntentClassifier` (`_SPANISH_HINTS` / `_ENGLISH_HINTS`), o recibe `lang`
del llamador — el router no duplica ni contradice la detección existente.

### 3.3 Por qué NO se toca `MemoryIntentClassifier`

- Es un archivo **protegido** por reglas duras de fases anteriores y sus tests
  (`test_memory_intent.py`) fijan clasificaciones byte a byte.
- El router es **más grueso** (2 vías) que el clasificador (8 intenciones):
  son capas complementarias, no competidoras. El router decide *dominio*; el
  clasificador, dentro de `RECALL`, decide *capacidad*.
- **Cero regresión por construcción:** si el router devuelve `RECALL`, el código
  V2/V1 existente se ejecuta **idéntico** a hoy (mismo clasificador, mismas
  narrativas, mismos tests verdes).

### 3.4 Dos puntos de enganche cubren las cuatro superficies

| Superficie | Punto de enganche del router |
|---|---|
| MCP `memory_converse` + `/api/converse` (Voice Dock, Dashboard) | rama temprana en `build_memory_converse_resolver.resolve` (V1) |
| MCP `memory_recall` + `/api/recall` | `understand()` / plan (V2) |

Ningún otro componente importa el router. Cámaras (Android, Vivotek), TTS/STT,
Dashboard HTML y `MemoryBridge` **no se enteran** de que A7C existe.

---

## 4. Integración con `memory_recall` (V2)

### 4.1 Plan auditable (mismo patrón que `direction` de A7B)

- `RecallPlan` gana el campo `state_topic: str | None` + `"state_topic"` en
  `plan_to_dict` → la traza de `/api/recall` demuestra **por qué** se respondió
  con estado.
- `understand()` llama a `route_query()` al inicio; si `CURRENT_STATE`, devuelve
  un plan degenerado y explícito:

```
ops = (RetrieveOp(kind=CURRENT_STATE, entity=topic),)
relations = ()   ·   aggregation = None   ·   state_topic = topic
```

### 4.2 Engine: ejecución real del op `CURRENT_STATE`

- `RecallEngine.__init__` gana `state_provider: Callable[[], Mapping] | None`.
- `_execute_op` (hoy `recall_engine.py:208` → `extra["status"] = "unavailable"`):
  - **sin provider** → sigue `status="unavailable"` ⇒
    `tests/unit/test_recall_engine.py:312` **sigue verde sin editarse**;
  - **con provider** → snapshot leído con `try/except` (best-effort, igual que
    V1 `_current_state_answer`) y proyectado en la traza:

```json
{"op": "retrieve:current_state", "status": "ok",
 "state": {"topic": "gate", "gate_open": false, "risk": "LOW",
           "temperature_c": 22.4, "motion_score": 0.0,
           "detections": [], "source": "live", "ts": 1760000000.0}}
```

- El engine **nunca** consulta `VectorMemoryService` en este op (0 llamadas de
  recuperación ⇒ `evidence = ()`, `evidence_ids = ()`).

### 4.3 Síntesis: política 0 (antes de todo lo de A7B)

```
0. plan.state_topic fijado    → _state_line(topic, traza, lang)
     · status "ok"            → respuesta derivada de state.*
     · status "unavailable"   → frase honesta de no-disponibilidad
     · NUNCA cae a render_utterance()  ← garantía central
1..7 (política A7B sin cambios)
8. fallback render_utterance() byte-idéntico a V1
```

### 4.4 Cableado (3 puntos, todos aditivos)

| Punto | Hoy | Cambio |
|---|---|---|
| `memory_resolvers.py:541` | `build_memory_recall_resolver(memory)` **tira** el provider | pasar `current_state=current_state` (el parámetro **ya existe** en la línea 527) |
| `recall_resolvers.recall()` / `build_memory_recall_resolver` | sin provider | aceptar `current_state` y pasarlo a `RecallEngine(state_provider=...)` |
| `main.py:239` (`/api/recall`) | `recall(memory, query, …)` | `current_state=(lambda: watch.last_state) if watch else None` (`watch` ya está en scope, igual que `/api/converse:223`) |

---

## 5. Integración con `current_state`

### 5.1 Fuente de verdad única

`AmbientWatchService.last_state` (snapshot dict,
`ambient_watch_service.py:252-310`), ya cableado hoy a V1 en `main.py:160`
(`current_state_provider=lambda: watch.last_state`):

| Campo | Contenido real | Ejemplo mandatory |
|---|---|---|
| `gate_open` / `door_open` | reed switches del sensor bus (baseline: `False`, `sensor_bus.py:38-39`) | E1 |
| `motion_score` + `detections[MOTION]` | delta de frames de cámara (Android/Vivotek/phone) | E2 |
| `temperature_c` | baseline **22.4** (`sensor_bus.py:15`) | E3 |
| `risk` | veredicto del watchdog (`LOW/MEDIUM/HIGH/CRITICAL`) | E4 |
| `detections[]` | `{label, confidence}` vivos (SMOKE, GATE_OPEN…) | E5 |
| `ts`, `source` | último tick + origen (`live`/`snapshot`/`idle`) | honestidad |

### 5.2 Contrato del renderizador (dominio puro)

`render_state_answer(topic: str, state: Mapping, lang: str) -> str`:

- Lee **solo** campos reales presentes en el snapshot.
- Campo **ausente** → frase honesta: `"No dispongo del estado actual de la
  reja."` (nunca memoria, nunca invención). Estado inicial `idle`
  (`ambient_watch_service.py:252-257`) **no** trae `gate_open`/`temperature_c`
  hasta el primer tick (≤ 0.5 s tras el lifespan) — el renderizador lo distingue
  de `gate_open = False`.
- Campo presente → respuesta obligatoria (tabla derivación):

| Tema | Condición (campo real) | Respuesta ES (ejemplo mandatory) | Respuesta EN |
|---|---|---|---|
| `gate` | `gate_open is False` | `Sí. La reja se encuentra cerrada actualmente.` | `Yes. The gate is currently closed.` |
| `gate` | `gate_open is True` | `No. La reja está abierta ahora mismo.` | `No. The gate is open right now.` |
| `motion` | sin `MOTION` en detections y `motion_score` bajo | `No detecto movimiento activo.` | `I detect no active motion.` |
| `motion` | `MOTION` en detections | `Sí, detecto movimiento activo.` | `Yes, I detect active motion.` |
| `temperature` | `temperature_c = 22.4` | `La temperatura actual es 22.4°C.` | `The current temperature is 22.4°C.` |
| `risk` | `risk = "LOW"` | `El nivel de riesgo actual es LOW.` | `The current risk level is LOW.` |
| `overview` | campos disponibles | `Resumen construido desde el estado actual.` (compuesto: riesgo + detecciones + temperatura) | idem EN |

### 5.3 Separación estricta de fuentes

- **Estado ⇢ snapshot nunca memoria:** una pregunta E1-E5 no genera UNA sola
  llamada a `search_memory`/`last_seen`/`records_between`.
- **Memoria ⇢ registros nunca snapshot:** M1-M5 no leen `watch.last_state`.
- Así se evita la mezcla peligrosa: "la reja estaba abierta hace 10 min"
  (memoria) no puede contaminar "¿está cerrada?" (estado), ni al revés.

---

## 6. Riesgos

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | **Falso positivo**: estado respondido como memoria (bug actual) | Alto — es exactamente el problema a resolver | Precedencia de pasado + exigir sujeto+presente + golden test de los 10 ejemplos |
| R2 | **Falso negativo**: memoria respondida como estado | Alto — rompe M1-M5 | Marcadores pasados con límite de palabra; los 5 ejemplos de memoria son tests golden; default = RECALL |
| R3 | Regresión V1 en overview (`¿Qué ocurre ahora?` → `"Actualmente…"` fijado en `test_memory_converse.py:121,129` y `test_phone_camera_end_to_end.py:92`) | Alto — tests literal | En V1, el router **no intercepta** `overview`: cae al clasificador y `_current_state_answer` tal cual hoy. Solo los temas nuevos (gate/door/motion/temperature/risk/smoke) se interceptan |
| R4 | Cambio de salida V1 en preguntas que hoy terminaban en `"No he encontrado recuerdos…"` | Bajo — era el bug | Revisar aserciones literales existentes: `test_memory_resolvers.py:120` usa `"zzz"` (no interceptado) y `test_memory_intent.py:28` es clasificador (intocado) |
| R5 | Doble verdad memoria↔estado | Medio | Separación estricta §5.3; la respuesta de estado jamás incluye evidencia y viceversa |
| R6 | Snapshot `idle` sin campos (`gate_open`, `temperature_c`) | Medio — riesgo de inventar | Frase honesta por campo ausente (§5.2); nunca derivar de `{}` vacío |
| R7 | Bilingüe (Alexa en-US / Voice Dock EN) | Medio | Tablas es+en desde el día 1; reutilizar hints de idioma existentes; tests golden en ambos idiomas |
| R8 | Auditoría: respuesta de estado sin rastro en la traza | Bajo | `plan.state_topic` + `state` proyectado en `ops_executed` (§4.1-4.2) |
| R9 | Voice Dock/Dashboard: frases nuevas en TTS | Bajo | Solo cambia la salida para temas que hoy responden `"No he encontrado recuerdos…"` (bug); overview V1 byte-idéntico; sin tocar `dashboard.html` |
| R10 | Regresión en `test_recall_engine.py:312` (`status == "unavailable"`) | Bajo | Sin `state_provider` el op sigue reportando `unavailable` — comportamiento preservado por diseño |
| R11 | Scope creep (LLM, placeholders, `if` gigantes) | Medio | Tablas + precedencia de 4 filas; sin LLM por definición; gate de gates: 570 tests + flake8 + black |
| R12 | Falsa coincidencia de marcadores (p.ej. `está` dentro de `estado`) | Bajo | Regex con límite de palabra (`\best[áa]\b` no matchea `estado`) + tests de pares mínimos (A1, A8, A9) |

---

## 7. Quick wins (orden de implementación sugerido)

| # | Quick win | Alcance | Esfuerzo | Riesgo |
|---|---|---|---|---|
| **QW1** | `query_router.py` puro + `tests/unit/test_query_router.py` (golden: 10 ejemplos + ambiguos A1-A10, es+en) | Solo archivos **nuevos** — imposible regresión | 1-2 h | Nulo |
| **QW2** | Rama temprana en `build_memory_converse_resolver.resolve` (temas ≠ overview) → arregla el bug observado en V1 | 5-10 líneas en `memory_resolvers.py` (sin tocar líneas protegidas 476/532) | 30 min | Mínimo (R3 controlado) |
| **QW3** | Cablear el provider al canal recall (3 puntos de §4.4) | 3 archivos, cambios de 1-3 líneas | 30 min | Nulo (aditivo) |
| **QW4** | Engine: op `CURRENT_STATE` real con `state_provider` + proyección en traza | `recall_engine.py` (sin provider ⇒ `unavailable` intacto) | 1 h | Mínimo (R10) |
| **QW5** | Síntesis política 0 `state_topic` + `render_state_answer` con las respuestas obligatorias de §5.2 | 2 archivos nuevos/en dominio | 1-2 h | Nulo para A7B (política 0 solo con `state_topic`) |
| **QW6** | Tests golden es+en de salida + honestidad de snapshot `idle` + payload `/api/recall` con `evidence: []` | Tests nuevos | 1 h | Nulo |

**Secuencia:** QW1 → QW2 (bug observado resuelto el mismo día) → QW3+QW4 →
QW5 → QW6. Gates tras cada paso:

```powershell
.\.venv\Scripts\python.exe -m pytest -q                 # 570 + N nuevos, 0 fallos
.\.venv\Scripts\python.exe -m flake8 src tests          # 0
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```

---

## 8. Alcance protegido y fuera de alcance

**Intocable:** `MemoryIntentClassifier` · `memory_converse` (líneas 476/532) ·
`MemoryBridge` · `dashboard.html` (Voice Dock) · Android/Vivotek/Phone camera
adapters · TTS/STT · `MEMORY_TOOL_NAMES` / catálogo MCP · `pytest.ini`.

**Fuera de alcance de A7C:** migrar `memory_converse` al engine (fase G) ·
respuestas compuestas memoria+estado (A7) · duración real de estado (A4) ·
cualquier LLM.

**Decisión de producto pendiente (marcada, no bloqueante):** ¿se unifica la
frase de overview V1 (`"Actualmente detecto…"`) con la nueva composición V2?
Hoy la regla es **no romper**: V1 conserva su frase byte-idéntica; V2 compone
la suya. Una única voz unificada exigiría el test de equivalencia V1↔V2 de la
fase G.
