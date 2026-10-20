# A6f — Narración Contextual · Informe de Implementación

**Fecha:** 2026-10-18
**HEAD:** `b963c5f` — sin commits, sin push.
**Resultado:** ✅ **535 tests PASS** (500 → 535, +35) · **flake8: 0** · **black: 93 ficheros sin cambios** · **impacto V1: cero**

---

## 1. Encargo y límites

> *Consumir `context`. No consumir relaciones crudas.*
> *La narración debe nacer desde `ContextItem`, `signal`, `degraded`, `salience`.*
> *Crear un camino nuevo. No reemplazar el antiguo.*

Y la decisión de alcance: **narrar únicamente `temporal.transition` y
`correlation.overlapping`** — las dos que un humano percibe como contexto útil.
`temporal.precedes`, `correlation.same_label`, `correlation.same_risk` y
`spatial.same_zone` **no llegan a la voz**, salvo que una fase futura demuestre
que aportan valor real.

**No tocar:** `memory_converse`, `MemoryIntentClassifier`, `MemoryBridge`,
`response`, `render_utterance`, Dashboard, Android, Vivotek. Verificado en §6.

Principio de la fase: *menos información, más comprensión*.

---

## 2. Archivos creados

| Archivo | Tipo | Contenido |
|---|---|---|
| `src/domain/services/context_narrative.py` | **nuevo**, dominio puro | `render_context()`, renderers, `MAX_NARRATION_ITEMS` |
| `tests/unit/test_context_narrative.py` | **nuevo** | 35 tests |

**Modificados (5):**

| Archivo | Cambio |
|---|---|
| `src/domain/services/context.py` | `NARRATION_MIN = 3` + propiedad `ContextItem.narratable` |
| `src/domain/services/relation_rules.py` | `facts` de `correlation.overlapping` gana `subject_labels`/`object_labels` (aditivo) |
| `src/domain/services/evidence.py` | `RecallResult.context_utterance: str = ""` (aditivo) |
| `src/infrastructure/services/recall_engine.py` | `execute()` llama a `render_context()` y rellena el campo |
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | payload gana `"context_response"` |

---

## 3. La escalera de grados

`context.py` queda con dos umbrales distintos y un motivo por existir cada uno:

| Umbral | Valor | Significado | Quién lo usa |
|---|---|---|---|
| `SIGNAL_MIN` | **2** | Merece atención sin que nadie lo pida | ordena la cola (A6e) |
| `NARRATION_MIN` | **3** | Merece decirse en voz alta | **selecciona frases (A6f)** |

```
salience 3 → temporal.transition, correlation.overlapping   → SE DICE
salience 2 → temporal.precedes, correlation.same_label      → señal, NO se dice
salience 1 → correlation.same_risk, spatial.same_zone       → ruido, NO se dice
```

`signal` (grado amplio) ordena la cola que llega ya ordenada; `narratable`
(estrecho) decide qué se habla. Ambos derivan de `salience`, que sigue viviendo
en la tabla de reglas: **subir o bajar la línea de voz es cambiar una
constante, no rediseñar nada**.

---

## 4. Narrativa contextual

### 4.1 Formatos

| Caso | Español | Inglés |
|---|---|---|
| Cambio (normal) | `Cambio de GATE_OPEN a FALL, 40 segundos después, en el mismo lugar.` | `Change from GATE_OPEN to FALL, 40 seconds later, in the same place.` |
| Cambio (degradado) | `…en el mismo lugar (identidad aproximada).` | `…in the same place (approximate identity).` |
| Solape | `PET y SMOKE simultáneos durante 100 segundos.` | `PET and SMOKE at the same time for 100 seconds.` |
| Sin etiquetas | `Cambio de actividad, 40 segundos después, en el mismo lugar.` | `Change of activity, 40 seconds later, in the same place.` |
| Futuro desconocido | `Relación entre m-9 y m-7.` | `Relation between m-9 and m-7.` |

Invariante: **toda afirmación sale de `relation.facts`**. Nada se deduce, nada
se inventa, `lang` distinto de `en` cae a español.

### 4.2 Salida real (fixture A2, 3 registros)

```
V1 utterance   : GATE_OPEN en patio, hace 2 horas. FALL en patio, hace 2 horas. PET en patio, hace 2 horas.
context_utter  : Cambio de GATE_OPEN a FALL, 80 segundos después, en el mismo lugar (identidad aproximada).
                 Cambio de GATE_OPEN a PET, 95 segundos después, en el mismo lugar (identidad aproximada).
                 Cambio de FALL a PET, 15 segundos después, en el mismo lugar (identidad aproximada).
context items  : 12 | narratable: 3
sin relations  : context_utterance = ''
```

**12 relaciones en contexto, 3 frases.** Las 9 de menor salience siguen en
`context` y en `trace.relations` para auditoría — no se borran, no se dicen.

`response` del payload es idéntico a la utterance V1 (testado).

### 4.3 Límites implementados

- **Cap:** `MAX_NARRATION_ITEMS = 3`, el mismo techo de tres líneas que
  `render_utterance` de V1 (`_MAX_LINES`).
- **Degradación hablada:** un `degraded=True` añade el marcador en lugar de
  afirmar una identidad aproximada como cierta.
- **Vacío ≠ abstención:** sin contexto narrable el campo es `""`, no la frase
  de abstención — "no hay contexto" no es "no hay nada que recordar".
- **Nada narrable se descarta en silencio:** un `kind` futuro con salience ≥3
  y sin renderer cae a una frase genérica (testado), en vez de desaparecer.

---

## 5. Hallazgo: `correlation.overlapping` y el solape cero

Verificado en código y empíricamente durante la fase:

`build_episodes()` parte de registros **ordenados por timestamp**, así que los
episodios que produce son disjuntos — `B.start ≥ A.end` siempre. Un solape
estrictamente positivo es **inalcanzable** desde el motor; lo único que puede
ocurrir es que dos episodios **se toquen** (`overlap_seconds == 0`), cuando dos
claves distintas caen en el mismo instante.

La primera versión de mi narrador produjo, con datos reales del motor:

> `PET y SMOKE simultáneos durante 0 segundos.`

— una frase sin sentido. **Ese error era mío y se corrigió en la capa de
narración sin tocar A6d**: solape 0 se narra como *instante*, no como duración.

> `PET y SMOKE en el mismo instante.`

Declarado por honestidad, sin parchear la regla: `correlation.overlapping` con
solape positivo hoy sólo es alcanzable con episodios construidos a mano (tests
unitarios). Si alguna fase quiere narrar simultaneidad real, tendrá que
revisar cómo se construyen los episodios — decisión de esa fase, no de A6f.

---

## 6. Impacto cero

Baseline: **`A6F_BASELINE.sha256`**, 91 ficheros, capturado al cerrar A6e
*antes* de la primera edición de A6f (lección de proceso aprendida en A6e).

```
changed/missing: 5
CHANGED: src\domain\services\context.py
CHANGED: src\domain\services\evidence.py
CHANGED: src\domain\services\relation_rules.py
CHANGED: src\infrastructure\adapters\mcp\recall_resolvers.py
CHANGED: src\infrastructure\services\recall_engine.py
missing: 0

memory_converse(resolvers+tools) / IntentClassifier / Bridge / Dashboard /
main / service: INTACTOS
```

**Cinco ficheros modificados — exactamente los cinco que A6f declara. Cero
ficheros perdidos. Ninguno de la lista protegida.**

| Protegido | Evidencia |
|---|---|
| `MemoryIntentClassifier` | `git diff HEAD` → **0 líneas**, byte idéntico a `b963c5f` |
| `memory_converse` (`memory_resolvers.py` + `tools.py`) | fuera de la lista cambiada; escritos en A3 |
| `MemoryBridge` | fuera de la lista cambiada; escrito en A4 |
| Dashboard / main / service | fuera de la lista cambiada |
| Android / Vivotek | no existen en el árbol |
| **utterance V1** | `test_the_v1_utterance_is_untouched_by_the_narration`: idéntica con y sin narración, y sin la palabra `Cambio` |
| **`render_utterance`** | no modificado (sólo `evidence.py` ganó un campo con `default`) |

**Nuevo campo, camino nuevo:** `context_utterance` lleva `default=""`, así que
los 5 constructores existentes de `RecallResult` siguen válidos y el abstain
(`_abstain`) devuelve `""` automáticamente. El campo no se añade a `_render`
(MCP): **la respuesta visible de V1 no cambia en ningún canal.**

---

## 7. Gates

| Gate | Comando | Resultado |
|---|---|---|
| **pytest** | `pytest -q` | **535 passed** (500 → 535; **+35**) |
| **flake8** | `flake8 src tests` | **0** |
| **black** | `black --check src tests --line-length 88` | **93 ficheros sin cambios** |
| Commits | `git log --oneline -1` | `b963c5f` (sin cambios) |

Los 500 tests previos siguen en verde **sin ninguna modificación de
expectativa**; los 35 nuevos son de A6f.

### Cobertura de los 35 tests

- **Escalera** (5): `NARRATION_MIN > SIGNAL_MIN`; exactamente los dos kinds
  hablados; los cuatro retenidos no narrables; `narratable ⇒ signal`;
  degradación no bloquea.
- **Selección** (6): contexto vacío → `""`; ruido → `""`; cap; `MAX == 3`;
  determinismo.
- **`temporal.transition`** (7): es/en; marcador de degradación es/en; sin
  etiquetas; singular `1 segundo`/`1 second`; listas de varias etiquetas.
- **`correlation.overlapping`** (5): es/en; deduplicación; **solape 0 →
  instante**; sin etiquetas.
- **Forma general** (4): renderer genérico no silencioso; todas las frases
  terminan en `.`; `lang` desconocida → español; orden contextual.
- **Cableado del motor** (8): default `""`; plan sin relaciones; el motor
  narra sólo lo narrable; **utterance V1 intacta**; idioma del plan; camino de
  abstención; payload `context_response` con `response` sin tocar; JSON-safe.

---

## 8. Archivos

**Nuevos (2):** `src/domain/services/context_narrative.py`,
`tests/unit/test_context_narrative.py`

**Modificados (5):** lista exacta en §2.

**Baseline:** `A6F_BASELINE.sha256` (91 ficheros) — **consumido y eliminado**
tras la verificación de §6. Al cerrar A6f se captura **`A6G_BASELINE.sha256`
(93 ficheros)** como punto de partida de impacto cero para la siguiente fase,
mismo procedimiento.

**Generados:** `A6f_IMPLEMENTATION_REPORT.md` (este documento).

---

## 9. Siguiente fase

El camino existe y es consumible: `RecallResult.context_utterance` +
`context_response` en `/api/recall`, con la utterance V1 intacta y el contexto
ya jerarquizado y narrado.

La decisión que queda abierta — y que ninguna fase debe tomar por su cuenta sin
aprobarla — es **cuándo y dónde se muestra** esa narración al usuario final:
hoy existe como campo estructurado, trazable y verificado, esperando una
decisión de producto (canales, UX de Voice Dock, si convive o sustituye).

También queda pendiente, declarado desde A6d: `spatial.same_camera` (los
`Episode` no llevan cámara) y la exclusión del episodio ancla en
`before`/`after`, heredada de A6c.
