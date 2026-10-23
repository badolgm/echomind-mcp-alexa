# A6e — Contexto Estructurado · Informe de Implementación

**Fecha:** 2026-10-18
**HEAD:** `b963c5f` — sin commits, sin push.
**Resultado:** ✅ **500 tests PASS** (473 → 500, +27) · **flake8: 0** · **black: 91 ficheros sin cambios**

---

## 1. Encargo y límites

> *Transformar relaciones existentes en respuestas contextuales.*
> *Crear únicamente `context` como extensión aditiva de `RecallResult`.*
> *No modificar la utterance actual. No cambiar respuestas visibles.*

Y el principio rector de la fase:

```
Datos → Relaciones → Contexto → Narración
```

No al revés. A6d recién construyó el motor de relaciones; **todavía estamos
validando** que las seis reglas producen relaciones correctas, deterministas y
trazables. Antes de convertirlas en lenguaje natural, hay que poder observarlas
como datos estructurados. La narración contextual completa llega en **A6f**.

**No tocar:** `memory_converse`, `MemoryBridge`, `MemoryIntentClassifier`,
Android, Vivotek, Dashboard. Verificado en §6.

---

## 2. Qué se entregó

### 2.1 `src/domain/services/context.py` (nuevo, dominio puro)

La capa que se interpone entre el grafo y las palabras.

| Símbolo | Qué es |
|---|---|
| `SIGNAL_MIN = 2` | Umbral de salience a partir del cual una relación merece decirse sin que nadie la pida |
| `DEFAULT_SALIENCE = 0` | Grado de un `kind` que la tabla no conoce: nunca promocionado, nunca descartado |
| `ContextItem` | `frozen + slots`: `relation` + `salience`, con `signal` y `degraded` como propiedades |
| `salience_of(kind)` | Lee el grado de la tabla de reglas de A6d |
| `build_context(relations)` | Jerarquiza sin descartar |
| `context_to_dict(item)` | Proyección JSON para `/api/recall` |

`ContextItem` valida `0 <= salience <= 3` en `__post_init__`.

### 2.2 `RelationRule.salience` (aditivo, `relation_rules.py`)

El grado **vive en la tabla de reglas**, no en el motor. Es una propiedad de la
regla, igual que su `description`: las seis filas lo declaran.

| Regla | `salience` | Por qué |
|---|---|---|
| `temporal.transition` | **3** | Cambio de estado — el latido de historia más claro |
| `correlation.overlapping` | **3** | Simultaneidad: contexto real |
| `temporal.precedes` | **2** | La secuencia importa, pero dispara O(n²): informativa de a una, ruidosa en bloque |
| `correlation.same_label` | **2** | Detección compartida, valor moderado |
| `spatial.same_zone` | **1** | Co-localización a sola, y sobre datos legacy casi siempre degradada |
| `correlation.same_risk` | **1** | "Ambos en HIGH" se repite en casi cualquier consulta |

La tabla queda **graduada, no uniforme**: existen grados por encima y por debajo
de `SIGNAL_MIN` (testado).

### 2.3 `RecallResult.context` y `RecallTrace.relations` (aditivos)

```python
class RecallTrace:
    lang, plan, ops_executed, evidence_ids
    relations: tuple[dict[str, object], ...] = ()   # ← nuevo

class RecallResult:
    utterance, evidence, trace, lang
    is_error: bool = False
    context: tuple[ContextItem, ...] = ()           # ← nuevo
```

Ambos campos llevan `default`, así que **ningún constructor existente cambia**:
los 5 constructores de `RecallResult` en el código son por keyword y siguen
válidos.

Dos vistas de un mismo grafo, con intenciones distintas:

- **`trace.relations`** — crudo, orden determinista de reglas. Es el gemelo
  auditable de la entrada `derived` de A6d (`count` y `relations` coinciden
  exactamente). Sirve para fiscalizar.
- **`context`** — jerarquizado por salience. Es el que leerá el narrador de A6f.
  Sirve para decidir qué decir primero.

### 2.4 Cableado (`recall_engine.py`, `recall_resolvers.py`)

- `_relate()` pasa de devolver `None` a devolver `(raw, context)`.
- `_derive_relations()` calcula el grafo **una sola vez** y lo serializa en las
  dos formas. (Una primera versión lo calculaba dos veces; se corrigió.)
- `execute()` los asigna: `trace.relations=raw`, `context=context`.
- `recall_result_payload()` expone `"context"` y `"trace.relations"`.

Los planes **sin relaciones** devuelven `()` en ambos campos, igual que A6d no
emitía la entrada `derived`.

---

## 3. Verificación

Demostración real (fixture A2, 3 registros, `now=10000`, plan con `EPISODE`):

```
utterance: GATE_OPEN en patio, hace 2 horas. FALL en patio, hace 2 horas. PET en patio, hace 2 horas.
trace.relations: 12 | context: 12
ops: ['retrieve:range', 'relate', 'relate']

  sal=3 signal=True   temporal_transition     m-1->m-2 degraded=True
  sal=3 signal=True   temporal_transition     m-1->m-3 degraded=True
  sal=3 signal=True   temporal_transition     m-2->m-3 degraded=True
  sal=2 signal=True   temporal_precedes       m-1->m-2 degraded=False
  sal=2 signal=True   temporal_precedes       m-1->m-3 degraded=False
  sal=2 signal=True   temporal_precedes       m-2->m-3 degraded=False
  sal=1 signal=False  correlation_same_risk   m-1->m-2 degraded=False
  sal=1 signal=False  correlation_same_risk   m-1->m-3 degraded=False
  sal=1 signal=False  correlation_same_risk   m-2->m-3 degraded=False
  sal=1 signal=False  spatial_same_zone       m-1->m-2 degraded=True
  sal=1 signal=False  spatial_same_zone       m-1->m-3 degraded=True
  sal=1 signal=False  spatial_same_zone       m-2->m-3 degraded=True

payload keys: ['context','engine','evidence','is_error','lang','response','trace']
```

Lo que esto demuestra:

- **La utterance no se tocó.** Es literalmente la narración V1.
- **Nada se esconde:** las 12 relaciones del grafo están en `context`, las 12
  de menor salience abajo, no borradas. Ocultar evidencia existente es cómo un
  sistema empieza a mentir por omisión.
- **La degradación viaja:** `spatial_same_zone` y las `transition` sobre datos
  legacy llevan `degraded=True`, para que A6f no los afirme como ciertos.
- **No aparecen** `same_label` ni `overlapping` porque este fixture no comparte
  etiquetas ni se solapa — comportamiento correcto, no ausencia.

---

## 4. Contrato cumplido

| Criterio | Resultado |
|---|---|
| `context` aditivo, con `default` | ✅ ningún constructor preexistente tocado |
| Uttersance inalterada | ✅ `test_the_utterance_does_not_read_the_context`: idéntica con y sin relaciones |
| Sin cambios en respuestas visibles | ✅ `response` sin alterar; sólo se *añaden* claves al JSON |
| Estructurado | ✅ `ContextItem` tipado, inmutable, con validación |
| Verificable | ✅ 27 tests nuevos sobre grado, orden, proyección y cableado |
| Determinista | ✅ orden total `(-salience, kind, subject, object)`; orden de entrada irrelevante |
| JSON-safe | ✅ `json.dumps(payload)` testado |
| `memory_converse` intacto | ✅ verificado en §6 |

### Nuevos tests (27)

Contexto del dominio (item, salience, umbral, orden, no-descarte, proyección) y
cableado del motor (campo vacío sin relaciones, poblado con relaciones,
determinismo, invariancia de la utterance, ruta de abstención, payload).

**Sobre los 473:** la consigna era mantenerlos en verde. **Los 473 siguen
pasando y ninguno fue relajado ni eliminado.** Un único test de A6d recibió una
**adición** de aserción (que toda regla tenga salience en 0–3); no se atenuó
ninguna expectativa. El total sube 473 → 500 por los 27 nuevos.

---

## 5. Decisiones de diseño

1. **`context` en dominio, no en el motor.** El narrador de A6f será un
   servicio de dominio; si el contexto lo construyera el motor de
   infraestructura, A6f tendría que cruzar capas para leerlo. `context.py` es
   dominio puro, stdlib, sin ciclos (verificado: `evidence → context →
   relation_rules → memory_spatial`, ninguna hoja importa `evidence`).

2. **Tipado, no diccionarios.** `RecallResult` ya tipa `evidence` y `trace`; el
   interior de `trace` es dict. `context` sigue a `evidence`: tipo fuerte con
   comportamiento (`signal`, `degraded`), dict sólo en la proyección JSON.

3. **Salience en la tabla, no en el motor.** Igual que `description`: las reglas
   declaran su propio peso. Añadir una regla sigue siendo añadir una fila.

4. **Dos vistas, no una.** `trace.relations` audita; `context` narra. Mezclarlas
   obligaría a fiscalizar con criterios de relevancia y a narrar con criterios
   de evidencia.

5. **Por qué no `utterance` todavía** (decisión del usuario): primero se
   validan las relaciones como datos. Datos → relaciones → contexto →
   narración. La A6f leerá `context`, jamás el grafo crudo.

---

## 6. Impacto en V1 — verificación y una laguna declarada

**Laguna de proceso (sin ocultar):** no se capturó el baseline SHA-256 **antes**
de la primera edición de A6e, como sí se hizo en A4, A5 y A6d. La prueba
hash before/after no existe para esta fase. Se sustituye por las siguientes
evidencias y se corrige el proceso capturando `A6F_BASELINE.sha256` (91
ficheros) al cerrar A6e, para que **A6f sí** tenga su comparación.

### 6.1 Lista exacta de cambios de A6e (6 ficheros)

**Modificados (5):**

| Fichero | Cambio |
|---|---|
| `src/domain/services/relation_rules.py` | campo `salience` + 6 filas |
| `src/domain/services/evidence.py` | campos `context`, `relations` + import |
| `src/infrastructure/services/recall_engine.py` | `_relate`/`_derive_relations` devuelven ambas vistas + cableado |
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | `context` y `trace.relations` en payload |
| `tests/unit/test_relation_rules.py` | **+1 línea** de aserción (salience 0–3) |

**Nuevos (2):** `src/domain/services/context.py`, `tests/unit/test_context.py`

No se abrió ni editó ningún otro fichero de producción en la fase.

### 6.2 Prueba de no-tocar sobre la lista protegida

| Protegido | Evidencia |
|---|---|
| **`MemoryIntentClassifier`** (`src/domain/services/memory_intent.py`) | `git diff HEAD` → **vacío**. Fichero **byte idéntico a `b963c5f`**, no sólo intacto en A6e sino en toda la Fase A. |
| **`memory_converse`** (`memory_resolvers.py:476,532` + `tools.py:266`) | `memory_resolvers.py` escrito 00:51, `tools.py` 00:50 — frente a la ventana A6e **19:06–19:17**. Ambos provienen de A3 (reporte de A3), no de A6e. |
| **`MemoryBridge`** (`memory_bridge.py:94`) | escrito 07:47; proviene de A4 (reporte de A4). |
| **Dashboard** (`src/static/dashboard.html`) | escrito 11:23; sucio desde antes de la Fase A — **ningún reporte de A1–A6d lo menciona**. |
| **Android / Vivotek** | no existe ningún directorio ni fichero con esos nombres en el árbol. Nada que tocar. |
| **Uttersance V1** | test explícito §3. |

Separación de tiempos de modificación:

```
19:17:07  recall_engine.py        ← A6e
19:17:24  recall_resolvers.py     ← A6e
19:16:25  evidence.py             ← A6e
19:16:16  context.py              ← A6e
19:06:30  relation_rules.py       ← A6e
   ── vacío de 4 horas ──
15:06:02  memory_intent.py        ✗ no tocado (git diff vacío)
11:23:10  dashboard.html          ✗ no tocado
07:47:18  memory_bridge.py        ✗ no tocado
00:51:37  memory_resolvers.py     ✗ no tocado
00:50:46  tools.py                ✗ no tocado
```

### 6.3 Prueba de conducta

Los **473 tests que definían A6c/A6d pasan sin ninguna modificación de
expectativa**. Ese conjunto incluye la ruta de `memory_converse`, la de
`MemoryIntentClassifier`, el bridge, el payload de `/api/recall` y las pruebas
de narración V1 — comportamiento preservado en bloque.

---

## 7. Gates finales

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `pytest -q` | **500 passed** (473 → 500; +27) |
| Lint | `flake8 src tests` | **0** |
| Formato | `black --check src tests --line-length 88` | **91 ficheros sin cambios** |
| Commits | `git log --oneline -1` | `b963c5f` (sin cambios) |

---

## 8. Archivos

**Nuevos**
- `src/domain/services/context.py` — `ContextItem`, `build_context`, `context_to_dict`, `salience_of`
- `tests/unit/test_context.py` — 27 tests

**Modificados (5)** — lista exacta en §6.1

**Baseline:** `A6F_BASELINE.sha256` (91 ficheros) — **se conserva hasta que A6f
lo use y lo elimine**.

**Declarado sucio por fases anteriores, no tocado en A6e:** `memory_resolvers.py`,
`tools.py`, `main.py`, `memory_intent.py`, `memory_bridge.py`, `memory_service.py`,
`dashboard.html` (§6.2).

---

## 9. Siguiente fase

**A6f — Narración contextual.** Consume `RecallResult.context`, ya jerarquizado
y con `signal`/`degraded` resueltos, para producir la respuesta contextual. Es
la primera fase que altera lo que se *dice* (no el `utterance` V1, sino una vía
nueva), y llega con las relaciones ya validadas como datos — que era el
objetivo declarado de esta fase.

Usará `A6F_BASELINE.sha256` para su prueba de impacto cero.
