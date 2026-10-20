# A7C — Implementación: Query Router + Estado vivo (Current-State Reasoning)

**Fase:** A7C (implementación, no análisis) · **Módulo:** enrutador de preguntas + respuestas de estado
**Regla dura respetada:** `memory_converse`/`MemoryBridge`/Dashboard/Android/Vivotek intactos · 570 tests previos siguen PASS · sin commits · sin push · HEAD = `b963c5f`
**Orden de trabajo:** QW1 → QW2 → QW3 → QW4 → QW5 → QW6 (exacto)

---

## 1. Objetivo cumplido

El **bug observado** en el Voice Dock:

```
¿La reja está cerrada?  →  "No he encontrado recuerdos para: ¿La reja está cerrada?"
```

ya **no existe**. Una pregunta sobre el estado *actual* de la casa se enruta a la
**capa de estado vivo** (`watch.last_state`) y **nunca** toca `search_memory`,
`last_seen` ni los timelines. Las preguntas de memoria siguen su camino V1 sin cambios.

---

## 2. Archivos modificados y nuevos

### Modificados (7)

| Archivo | Cambio |
|---|---|
| `src/domain/services/query_router.py` *(de QW1)* | `RouteDecision.polarity: str \| None` — propiedad abierto/cerrado que **afirma la propia pregunta** (`"open"`/`"closed"`/`None`), detectada por `_OPEN_WORDS`/`_CLOSED_WORDS`. |
| `src/domain/services/recall_plan.py` | Campos nuevos `RecallPlan.state_topic` y `RecallPlan.state_polarity` + ambas claves en `plan_to_dict` (traza auditable). `None` en todo plan de memoria → comportamiento idéntico. |
| `src/domain/services/recall_planner.py` | `understand()` consulta `route_query`; si la pregunta es `CURRENT_STATE` devuelve `_state_plan(decision)`: **una sola** op `CURRENT_STATE`, sin ops de almacén. |
| `src/domain/services/recall_synthesis.py` | **Política 0 (primera coincidencia):** `state_topic` → `render_state_answer` desde el snapshot del op ejecutado, jamás `render_utterance`. |
| `src/infrastructure/adapters/mcp/memory_resolvers.py` | Rama temprana en `build_memory_converse_resolver.resolve` (tras validar query, antes del clasificador) que responde estado desde `current_state`; helper `_read_live_state`. Líneas protegidas 476/532 intactas. |
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | `recall()` y `build_memory_recall_resolver` aceptan `state_provider` y lo inyectan en el motor. |
| `src/main.py` | `/api/recall` pasa `state_provider=(lambda: watch.last_state) if watch else None` (`watch` ya estaba en scope). |
| `src/infrastructure/services/recall_engine.py` | `state_provider` en el constructor; `_execute_op` `CURRENT_STATE` → `_read_state()`: `{"status":"ok","state":<snapshot>}` o `{"status":"unavailable"}` si no hay provider o falla. |

### Nuevos (8)

| Archivo | Contenido |
|---|---|
| `src/domain/services/current_state_reasoning.py` | Renderizador honesto: `render_state_answer(topic, state, lang, *, polarity)` + tablas de frases es/en, degradación "no dispongo". |
| `tests/unit/test_query_router.py` | 41 tests del enrutador. |
| `tests/unit/test_current_state_reasoning.py` | 23 tests del renderizador. |
| `tests/unit/test_converse_state_routing.py` | 11 tests V1 (`memory_converse`) con/sin estado vivo. |
| `tests/unit/test_recall_state_provider.py` | 7 tests motor: snapshot, `unavailable`, provider que falla, no toca almacén. |
| `tests/unit/test_recall_state_plan.py` | 9 tests planificador + política 0 + threading. |
| `tests/integration/test_state_routing_end_to_end.py` | 7 goldens HTTP en `/api/converse` y `/api/recall`. |

---

## 3. Enrutador (`query_router`) — precedencia

```
1. conteo            ("cuántos…")                                  → RECALL
2. anchor de memoria ("hoy", "ayer", "antes", "mientras estaba…")  → RECALL
3. pasado            ("ha estado", "estuvo", "ocurrió", "dejaste"…) → RECALL
4. sujeto + presente ("está", "ahora", "hay"…)                     → CURRENT_STATE(topic)
5. panorama          ("¿qué ocurre ahora?", "what is happening…")   → CURRENT_STATE(OVERVIEW)
6. por defecto                                                     → RECALL
```

`StateTopic ∈ {GATE, DOOR, MOTION, TEMPERATURE, RISK, SMOKE, OVERVIEW}` ·
`MemoryIntentClassifier` se reutiliza **solo** para detectar el idioma.

---

## 4. Renderizado honesto (A7C)

`render_state_answer` lee **solo** campos reales del snapshot:

| Tema | Campo real | Respuesta (es) |
|---|---|---|
| `gate` | `gate_open` | `Sí. La reja se encuentra cerrada actualmente.` (polaridad `closed` + hecho cerrado) |
| `door` | `door_open` | `Sí. La puerta se encuentra cerrada actualmente.` |
| `motion` | `detections` (label `MOTION`) | `Sí, detecto movimiento activo.` / `No detecto movimiento activo.` |
| `temperature` | `temperature_c` | `La temperatura actual es 22.4°C.` |
| `risk` | `risk` | `El nivel de riesgo actual es LOW.` |
| `smoke` | `detections` (label `SMOKE`/`FIRE`) | `Sí, detecto humo activo.` / `No detecto humo activo.` |
| `overview` | composición (riesgo + incidencias + temperatura) | `El nivel de riesgo actual es LOW. No detecto incidencias activas. La temperatura actual es 22.4°C.` |

Garantías por construcción:

- **Nunca inventa:** campo ausente → `"No dispongo del estado actual de la reja."`
  (o temperatura/riesgo/vivienda según el tema).
- **La polaridad no cambia el hecho:** `¿La reja está cerrada?` con reja abierta →
  `"No. La reja está abierta ahora mismo."` (prefijo Sí/No + hecho real).
- **Sin almacén, sin LLM, sin reloj:** dominio puro (stdlib) — no hay ninguna
  llamada a `search_memory`/`last_seen`.
- **Movimiento por etiqueta:** activo ⟺ `"MOTION"` en `detections` (sin duplicar el
  umbral de infraestructura `MOTION_THRESHOLD`).
- **Overview en V1 sin cambios:** la rama temprana de `memory_converse` **excluye**
  `OVERVIEW`; los goldens fijados (`"Actualmente…"`) permanecen byte-idénticos.

---

## 5. Canal recall — política 0 (QW5)

Antes de la política 1 (COUNT), `render_synthesis` evalúa:

```
0. state_topic → render_state_answer(topic, snapshot, lang, polarity)
                 snapshot = op "retrieve:current_state" con status "ok"
                 status "unavailable" → frase honesta "no dispongo"
```

`plan.state_topic is None` ⇒ la política 0 no actúa ⇒ planes de memoria intactos.

---

## 6. Tests nuevos (98 → total suite **668**)

| Archivo | Nº |
|---|---|
| `tests/unit/test_query_router.py` | 41 |
| `tests/unit/test_current_state_reasoning.py` | 23 |
| `tests/unit/test_converse_state_routing.py` | 11 |
| `tests/unit/test_recall_state_provider.py` | 7 |
| `tests/unit/test_recall_state_plan.py` | 9 |
| `tests/integration/test_state_routing_end_to_end.py` | 7 |
| **Total** | **98** |

570 (base A7B) + 98 = **668 passed**.

### Goldens obligatorios (end-to-end, `/api/converse` con estado vivo)

```
¿La reja está cerrada?    → Sí. La reja se encuentra cerrada actualmente.
¿Hay movimiento ahora?    → No detecto movimiento activo.
¿Qué temperatura hay?     → La temperatura actual es 22.4°C.
¿Cuál es el riesgo actual? → El nivel de riesgo actual es LOW.
¿Qué ocurre ahora?        → Actualmente no tengo detecciones activas.   (golden V1 intacto)
Is the gate closed?       → Yes. The gate is currently closed.
```

### Canal recall (`/api/recall`, misma app)

```
¿La reja está cerrada? → "Sí. La reja se encuentra cerrada actualmente."
                         evidence: []  · plan.state_topic: "gate" · plan.state_polarity: "closed"
                         ops[0]: retrieve:current_state, status ok, state.gate_open == false
```

Con el watchdog **idle** (sin `gate_open`/`temperature_c`), ambos canales degradan
honestamente: `"No dispongo del estado actual de la reja."` — jamás el bug original.

---

## 7. Verificación de impacto (hash vs `A7C_BASELINE.sha256`)

`CHANGED=7 · NEW=8 · MISSING=0` (95 → 103 archivos `.py`).

| Cambiados (7) | Nuevos (8) |
|---|---|
| `recall_plan.py`, `recall_planner.py`, `recall_synthesis.py` | `current_state_reasoning.py`, `query_router.py` |
| `memory_resolvers.py`, `recall_resolvers.py`, `recall_engine.py` | 6 archivos de test |

**No modificados** (fuera de alcance, byte-idénticos): `tools.py` (`memory_converse`),
`memory_bridge.py`, `memory_intent.py`, Dashboard (`dashboard.html` no aparece en el
manifiesto `.py`), Android, Vivotek, `pytest.ini`.

---

## 8. Observaciones y límites declarados

1. **Secuencia renderizador/política:** el renderizador se crea en **QW2** (lo exige
   el bug fix en `memory_converse`); la **política 0** lo reutiliza en **QW5**. Ambas
   comparten una única fuente de verdad de frases.
2. **`OVERVIEW` en recall sí se enruta a estado** (el canal recall es la superficie
   A7C); en **V1 `memory_converse` se conserva** el golden `"Actualmente…"`. Las dos
   superficies son coherentes y honestas, con textos distintos por diseño.
3. **Estado idle real:** `watch.last_state` inicial
   `{"risk":"LOW","source":"idle","detections":[],"announcement":""}` no trae
   `gate_open`/`temperature_c`; por eso, sin tick de sensores, esas respuestas son
   "no dispongo" (honesto). Con `read_sensors` (temperatura base `22.4`, reja/puerta
   cerradas) aparecen los goldens exactos.
4. **Estimador de confianza de movimiento:** activo por etiqueta `"MOTION"`, no por
   `motion_score` (el umbral `0.20` es de infraestructura y no se duplica en dominio).
5. **Baseline consumido:** `A7C_BASELINE.sha256` (en `%TEMP%\opencode\`) se elimina
   tras esta verificación, como en fases anteriores.

---

## 9. Comandos de verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q                                  # 668 passed
.\.venv\Scripts\python.exe -m flake8 src tests                           # 0
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88   # 103 unchanged
git log --oneline -1                                                     # b963c5f, sin commits
```
