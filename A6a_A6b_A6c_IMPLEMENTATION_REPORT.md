# A6a_A6b_A6c_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A6 (Contextual Memory Reasoning)**
**Sub-fases entregadas:** A6a → A6b → A6c (en ese orden)
**Fecha:** 2026-10-18
**Regla absoluta respetada:** `memory_converse` **no se ha tocado**.

---

## 1. Resumen ejecutivo

| | Antes | Después |
|---|---|---|
| Tests | 376 | **433** (+57) |
| `flake8` | 0 | **0** |
| `black` | limpio | **87 files unchanged** |
| Ficheros `.py` modificados | — | **4** (todos autorizados) |
| `memory_converse` | — | **intacto, byte a byte** |

A6a, A6b y A6c construyen los **cimientos** del Relation Layer sin cambiar un solo comportamiento observable hoy: la respuesta a cualquier pregunta existente es idéntica a la de antes. Lo que sí han cambiado son las **capacidades que el sistema ahora tiene disponibles** para A6d y A6e.

---

## 2. A6a — Cimiento relacional

### Archivos
| Archivo | Tipo |
|---|---|
| `src/domain/services/relation.py` | **nuevo** |
| `tests/unit/test_relation.py` | **nuevo** (18 tests) |

### Contenido

**`Relation`** — frozen + slots, el unidad de razonamiento:

```python
kind: str                       # vocabulario cerrado
subject: str                    # obligatorio
object: str                     # obligatorio
rule: str                       # obligatorio (procedencia)
facts: Mapping[str, object]     # los números crudos
degraded: bool = False
fallback: str | None = None
```

**`KNOWN_RELATION_KINDS`** — vocabulario **cerrado** de 12 tipos en 3 familias:

| Familia | Tipos |
|---|---|
| `TEMPORAL_KINDS` | `temporal_precedes`, `temporal_follows`, `temporal_within`, `temporal_gap`, `temporal_transition` |
| `SPATIAL_KINDS` | `spatial_same_zone`, `spatial_same_camera`, `spatial_degraded` |
| `CORRELATIONAL_KINDS` | `correlation_same_label`, `correlation_same_risk`, `correlation_overlapping`, `correlation_co_occurring` |

**`relation_to_dict()`** — proyección JSON para la traza.

### Invariantes que A6a fija con tests

1. **Vocabulario cerrado** — un kind desconocido lanza `ValueError`. `test_causal_language_is_not_a_valid_kind` comprueba que `"causal"`, `"causes"`, `"caused_by"` y `"because_of"` **no son kinds válidos**: la causalidad está prohibida en la raíz del modelo, no sólo en la redacción.
2. **Procedencia obligatoria** — `subject`, `object` y `rule` no pueden ser vacíos ni blancos.
3. **Inmutabilidad** — frozen + slots.
4. **`confidence` deliberadamente ausente** — `test_relation_has_no_confidence_field`. En su lugar, `degraded` + `fallback`.

---

## 3. A6b — Simetría temporal

### Archivos
| Archivo | Tipo |
|---|---|
| `src/infrastructure/services/memory_timeline.py` | **modificado** (+12 líneas) |
| `tests/unit/test_memory_timeline.py` | **modificado** (+5 tests) |

### Contenido

```python
def episodes_after(episodes, *, target_ts: float) -> tuple[Episode, ...]:
    """Keep the episodes that started at or after ``target_ts``."""
    return tuple(episode for episode in episodes if episode.start >= target_ts)
```

Espejo exacto de `episodes_before` (A2), cortando por `start` con frontera **inclusiva**, igual que el original lo hace por `end`. Ambas direcciones usan la misma regla de borde, así que un episodio que empieza exactamente en el objetivo es alcanzable desde ambos lados.

**Esto desbloquea el Caso 2** ("¿qué pasó *después* de la apertura de la reja?"), que antes era literalmente imposible: sólo existía la mirada hacia atrás.

### Tests nuevos (5)
| Test | Qué fija |
|---|---|
| `test_episodes_after_filters_by_target` | espejo directo del test de `episodes_before` |
| `test_episodes_after_all_before_target_is_empty` | vacío cuando nada queda por delante |
| `test_episodes_after_includes_the_episode_starting_on_target` | frontera inclusiva |
| `test_episodes_before_and_after_partition_the_timeline` | **para 5 targets distintos, `before ∪ after` cubre exactamente todos los episodios** — ninguna fisura ni solape |
| `test_episodes_after_preserves_order` | orden cronológico preservado |

---

## 4. A6c — Anclaje a evento

### Archivos
| Archivo | Tipo |
|---|---|
| `src/domain/services/memory_anchor.py` | **nuevo** |
| `src/domain/services/recall_plan.py` | **modificado** (+1 campo, +1 clave) |
| `src/infrastructure/services/recall_engine.py` | **modificado** (anclaje + abstención) |
| `tests/unit/test_memory_anchor.py` | **nuevo** (17 tests) |
| `tests/unit/test_recall_engine_anchor.py` | **nuevo** (17 tests) |

### Contenido

**`AnchorRef`** (dominio puro, duck-typed) — el momento resuelto sobre el que se reconstruye la ventana:

```python
record_id, ts, label, location, camera_id, zone, candidates = 1
```

**La regla de anclaje, cerrada y determinista:**
- el ancla es el registro **más reciente** con esa etiqueta
- los empates se resuelven por `id` **descendente** → nunca depende del orden de inserción
- `candidates` cuenta los registros que coincidieron, para que un ancla ambigua sea **visible en la traza** en vez de silenciosa
- **sin coincidencia no hay ancla**, y sin ancla no hay respuesta contextual

**Dos campos aditivos en `RecallPlan`** (default `None`, así que todos los planes existentes son idénticos):

```python
anchor: str | None = None        # etiqueta del evento sobre el que reconstruir
# plan_to_dict() gana "anchor": plan.anchor
```

**Mecanismo de dos pasadas en `RecallEngine.execute()`:**

```python
if plan.anchor is not None:
    anchor = self._resolve_anchor(...)
    if anchor is None:
        return _abstain(plan, ops_executed)     # sin ancla => silencio
    span = _anchor_span(plan.window)            # hours*3600 o 300s
    since, until = anchor.ts - span, anchor.ts + span
...
self._relate(..., until=anchor.ts if anchor else until)
```

Dos detalles que importan:

1. **La ventana se rebasea** alrededor del ancla (`[ts−span, ts+span]`), no se recorta.
2. **Las relaciones se cortan en `anchor.ts`**, no en el borde de la ventana. Es lo que hace que "antes de la caída" signifique antes de la caída y no antes del final de la ventana — lo prueba `test_relations_are_cut_at_the_anchor_not_at_the_window_edge`.

**Nueva traza:** `{"op": "anchor", "label", "found", "record_id"?, "ts"?, "candidates"?}`.

### Tests nuevos (34)

| Bloque | Tests |
|---|---|
| Ancla (17) | estructura, selección del más reciente, desempate por `id`, independencia del orden de entrada, recuento de candidatos, metadatos espaciales, duck-typing |
| Motor (17) | inercia por defecto, resolución, rebase de ventana, span por `hours`, span por defecto, corte direccional, **abstención total** |

**Las tres que más importan:**

- `test_plan_without_anchor_keeps_the_original_window` — sin ancla, la recuperación devuelve **los 4 registros**, incluido el lejano: prueba que el anclaje es **estrictamente inerte** por defecto.
- `test_relations_are_cut_at_the_anchor_not_at_the_window_edge` — con `hours=0.5` la ventana llega hasta 2880, pero el corte se queda en **1080** (el ancla). Prueba el mecanismo central.
- `test_abstention_runs_no_retrieval_operation` — ancla ausente ⇒ `ops == ["anchor"]`: **no se ejecuta ninguna operación de recuperación**. El sistema prefiere callarse antes que responder la pregunta no anclada.

---

## 5. Gates

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `.venv\Scripts\python.exe -m pytest -q` | **433 passed** |
| Lint | `.venv\Scripts\python.exe -m flake8 src tests` | **0 violaciones** |
| Formato | `.venv\Scripts\python.exe -m black --check src tests --line-length 88` | **87 files unchanged** |
| Dependencias nuevas | `requirements.txt` | **ninguna** |

### Resultado pytest
```
433 passed in 9.84s
```

| Fase | Tests |
|---|---|
| Baseline (V1+A1…A5) | 376 |
| A6a — `test_relation.py` | +18 |
| A6b — `test_memory_timeline.py` | +5 |
| A6c — `test_memory_anchor.py` | +17 |
| A6c — `test_recall_engine_anchor.py` | +17 |
| **Total** | **433** |

**Los 376 tests preexistentes siguen verdes. Ninguno fue editado**, salvo `test_memory_timeline.py` al que se le **añadieron** 5 tests (y se actualizó su docstring de cabecera para reflejar "after").

---

## 6. Evidencia de impacto cero

Huella SHA-256 de los **82 ficheros `.py`** de `src/` + `tests/` capturada antes de la primera edición (`A6_BASELINE.sha256`) y recomparada al cerrar:

```
changed/missing: 4
CHANGED: .\src\domain\services\recall_plan.py
CHANGED: .\src\infrastructure\services\memory_timeline.py
CHANGED: .\src\infrastructure\services\recall_engine.py
CHANGED: .\tests\unit\test_memory_timeline.py
```

Exactamente la lista autorizada para A6b (2) y A6c (2). **0 `MISSING`.**

### Ficheros nuevos (5)
`src/domain/services/relation.py` · `src/domain/services/memory_anchor.py` · `tests/unit/test_relation.py` · `tests/unit/test_memory_anchor.py` · `tests/unit/test_recall_engine_anchor.py`

### Protección de V1 — verificación explícita

Comprobación programática de que los ficheros de `memory_converse` no aparecen en la lista de cambios:

```
memory_converse / bridge / intent: INTACTOS
```

| Fichero protegido | Estado |
|---|---|
| `src/infrastructure/adapters/mcp/memory_resolvers.py` (`memory_converse`) | **intacto** |
| `src/domain/services/memory_intent.py` | **intacto** |
| `src/infrastructure/services/memory_bridge.py` | **intacto** |

El artefacto `A6_BASELINE.sha256` se **eliminó tras la verificación**. HEAD intacto en `b963c5f`. Sin commits, sin push.

---

## 7. Decisiones y desviaciones

### 7.1 Desviación declarada: `RelationRule` pospuesto a A6d
El plan de A6a preveía `RelationRule` + una tabla `RELATION_RULES`. **No se ha creado**: una tabla de reglas cuyo motor llega en A6d sería código muerto, y `PHASE_A_IMPLEMENTATION_PLAN.md §9.4` lo prohíbe explícitamente. A6a entrega la **unidad** (`Relation`) y el **vocabulario cerrado**, que es lo que A6d va a poblar. Misma disciplina aplicada en A4 con `memory_spatial.py`.

### 7.2 El motor resuelve el ancla con el almacén, no escaneando
`RecallEngine._resolve_anchor` usa `last_seen()` + `count_occurrences()` (ambos existentes, eficientes) y delega el mapeo de campos en `anchor_from_record()`, del dominio. La regla pura `resolve_anchor(records, label)` sigue disponible para cualquier secuencia y está **probada por tests**. El mapeo vive en **un solo sitio**; no hay duplicación de lógica.

### 7.3 El episodio ancla aparece todavía en "antes"
`episodes_before` es inclusivo por diseño de A2 (un episodio que termina exactamente en el objetivo cuenta). Consecuencia: al preguntar "antes de la caída", la propia caída sigue en la lista de episodios. **No se ha tocado `episodes_before`** (comportamiento A2 protegido). Excluir el ancla de la *respuesta* es una concern de **selección de evidencia / narrador**, y por tanto de **A6e**.

### 7.4 Span por defecto = 300 s
`DEFAULT_ANCHOR_SPAN_SECONDS = 300.0`, coherente con `DEFAULT_TIMELINE_GAP_SECONDS` de A2. Si el plan lleva `hours`, se usa eso en su lugar.

---

## 8. Qué queda disponible para A6d/A6e

| Capacidad | Estado tras A6c |
|---|---|
| Unidad `Relation` inmutable y serializable | ✅ lista |
| Vocabulario cerrado de 12 tipos, con la causalidad prohibida en la raíz | ✅ listo |
| Corte temporal en ambas direcciones | ✅ listo (`episodes_before` + `episodes_after`) |
| Resolución del momento de un evento, determinista y trazable | ✅ listo |
| Ventana reconstruida alrededor de un evento del pasado | ✅ listo |
| Abstención total sin ancla | ✅ listo |
| Motor de reglas que emita `Relation` | ⬜ A6d |
| Narrador que traduzca relaciones a lenguaje | ⬜ A6e |

**Los Casos 1, 2 y 5 del documento de arquitectura son técnicamente posibles hoy.** Lo que falta es componer la respuesta (A6d: reglas → relaciones; A6e: relaciones → frases).

---

## 9. Siguiente paso

**A6d — Motor de relaciones sobre episodios**: tabla de reglas temporal/espacial/correlacional emitiendo `Relation` sobre `Episode`, con orden determinista y tope duro, integrado en `_relate` **sin tocar aún el utterance**. Criterio de aceptación: relaciones visibles en la traza y respuesta **idéntica** a la de hoy.

Pendiente de tu aprobación.
