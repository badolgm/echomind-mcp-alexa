# A6_CONTEXTUAL_REASONING_ARCHITECTURE.md

**Sprint:** ECHOMIND V2 PHASE A — **A6 (Contextual Memory Reasoning)**
**Fecha:** 2026-10-18
**Estado:** **Diseño. Ninguna línea de código implementada.**

---

## 0. Respuesta a la pregunta central

> *¿Cómo puede EchoMind razonar sobre recuerdos y evidencias reales sin convertirse en un chatbot ni depender de un LLM?*

**Convirtiendo "razonar" en "computar sobre hechos almacenados".**

EchoMind no necesita entender el mundo: necesita **ordenar, agrupar, comparar y medir** lo que ya guardó. Todo lo que un humano pregunta tras ver un vídeo ("¿qué pasó antes?", "¿quién más lo vio?", "¿dónde?", "¿cuántas veces?") es una operación sobre **orden temporal, identidad espacial y frecuencia** — tres cosas que ya están en `MemoryRecord` y se pueden calcular con aritmética.

La regla que lo sostiene:

> **Una respuesta es válida sólo si cada una de sus frases puede señalarse contra una regla determinista y un conjunto de `record_id` citados. Si una frase no tiene regla, no se emite.**

No es un chatbot con cámaras. Es un **motor de recuperación con capacidad de comparación**, que narra lo que comparó. La inteligencia está en la **restricción**, no en la generación.

---

## 1. Diagnóstico: por qué A6 es el siguiente paso natural y no una discontinuidad

Todo el cimiento ya existe:

| Capa | Existe desde | Qué aporta a A6 |
|---|---|---|
| `MemoryBridge` | V1 | evento → record |
| `VectorMemoryService` | V1 | almacén + filtros |
| `MemoryRecord` (+ `camera_id`/`zone`) | A4 | identidad espacial |
| `RecallPlan` / `RecallPlanner` | A1 | pregunta → plan declarativo |
| `Evidence` / `render_utterance` | A1 | narración sin invención |
| `memory_timeline.py` | A2 | `Episode`, `TimelineGap`, `episodes_before` |
| `recall_engine.py` | A2 | retrieve → relate → synthesize |
| `memory_spatial.py` | A5 | `resolve_zone`, `resolve_camera` con degradación |
| `memory_recall` + `/api/recall` | A3 | canal paralelo trazable |

### El hueco real

En `recall_engine.py:86-87`:

```python
self._relate(plan, ordered, ops_executed, until=until)      # ← calcula grupos/episodios/gaps
utterance = render_utterance(evidence, lang=plan.lang, now=now)   # ← no los lee
```

`_relate` produce relaciones y las vuelca **sólo al trace**. El utterance se construye únicamente desde `evidence`. Es decir:

> **Hoy las relaciones existen, son correctas y son auditables… pero nadie las usa para responder.**

A6 no inventa una capa nueva desde cero: **cierra el circuito** entre lo que `_relate` ya calcula y lo que la narración ya dice. De ahí que sea la "primera fase de razonamiento" y no una reescritura.

### Dos ausencias concretas detectadas en el código

| # | Ausencia | Consecuencia |
|---|---|---|
| 1 | Existe `episodes_before()` pero **no existe `episodes_after()`** | El Caso 2 ("¿qué pasó *después* de…?") es **imposible hoy**. Sólo se puede mirar hacia atrás. |
| 2 | Las ventanas se anclan a `NOW` o `SESSION_START`. **No hay anclaje a un evento del pasado** | Los Casos 1, 2 y 5 son imposibles: necesitan la ventana *alrededor de "la caída"*, y hoy no hay forma de decirle al engine cuándo fue esa caída. |

Ambas ausencias definen el mecanismo central de A6 (§5.2).

---

## 2. Definición de Relation Layer

### 2.1 Qué es una relación

> **Una relación es un enlace derivado, con procedencia completa, entre dos o más evidencias o episodios, computado exclusivamente desde hechos almacenados (etiquetas, marcas de tiempo, ubicaciones, cámaras, riesgo).**

Cinco propiedades que la definen y que son **invariantes de diseño**, no aspiraciones:

| Propiedad | Significado | Por qué importa |
|---|---|---|
| **Derivada** | Nunca se persiste. Se recalcula en cada consulta. | No puede quedar obsoleta ni corromperse. Coste 0 de escritura. |
| **Con procedencia** | Cada relación cita las `record_id`/`episode` de origen y la `rule` que la produjo. | Permite replay total de cualquier respuesta. |
| **Determinista** | Mismos registros + mismos parámetros → mismo conjunto de relaciones, en el mismo orden. | Reproducibilidad, testing y confianza. |
| **Monótona** | Añadir registros puede añadir relaciones, pero nunca crear tipos nuevos. | El vocabulario de relaciones es cerrado y auditado. |
| **Local** | Se calcula sólo sobre la evidencia recuperada, nunca sobre el almacén completo. | Coste acotado y respeta el marco de la consulta. |

### 2.2 Qué NO es una relación

- **No es una inferencia sobre el mundo.** No dice "hubo un robo"; dice "A precede a B por 40 s en la misma zona".
- **No es una causa.** Nunca emite "X causó Y" (§4).
- **No es una confianza de modelo.** Ver la trampa semántica en §7.1.
- **No es un resumen.** Un resumen agrega; una relación **compara**.

### 2.3 Posición en el pipeline

```
RecallPlan                       (A1 — qué recuperar y cómo comparar)
   ↓ retrieve
MemoryRecord[]                   (V1 — hechos crudos)
   ↓ build_episodes              (A2 — ocurrencias coalescidas)
Episode[]
   ↓ resolve_anchor              (NUEVO — ¿alrededor de qué momento?)
AnchorRef
   ↓ REASON                      (NUEVO — §3 y §5)
Relation[]
   ↓ synthesize                  (MODIFICADO — narración guiada por relaciones)
RecallResult.utterance + trace   (A1/A3 — trazabilidad total)
```

**El nivel de razonamiento opera sobre `Episode`, no sobre `MemoryRecord` crudo.** Es una decisión de coste y de semántica: un episodio ya es "una ocurrencia", y sus cardinalidades son manejables donde las de registros no lo son (§7.4).

---

## 3. Tipos de relación

Cuatro familias, alineadas con las que pediste y con los `RelationKind` que ya existen.

### 3.1 Temporal — *cuándo, en qué orden*

| Relación | Regla | Ya existe |
|---|---|---|
| `temporal_precedes` | `A.end <= B.start` | parcial (`episodes_before`) |
| `temporal_follows` | `A.start >= B.end` | **NO** (`episodes_after` falta) |
| `temporal_within` | ambos dentro de un mismo episodio | sí (`build_episodes`) |
| `temporal_gap` | silencio > umbral entre A y B | sí (`timeline_gaps`) |
| `temporal_transition` | adyacentes + cambia el conjunto de etiquetas | **NO** (§3.4) |

**Distancia siempre explícita.** Toda relación temporal lleva `seconds: float` en sus `facts`. Nunca se narra "antes" sin poder decir "cuánto antes" si se pregunta.

### 3.2 Espacial — *dónde y con qué identidad*

| Relación | Regla | Identidad usada |
|---|---|---|
| `spatial_same_zone` | `resolve_zone(A) == resolve_zone(B)` | `zone` → `location` |
| `spatial_same_camera` | `resolve_camera(A) == resolve_camera(B)` | `camera_id` → `source` |
| `spatial_degraded` | la identidad usada fue el fallback | marca explícita |

**Regla dura:** toda relación espacial declara en `facts` si la identidad fue **exacta** o **degradada**. Hereda directamente el diseño de A5 (`resolve_zone`/`resolve_camera` ya devuelven `(valor, degradado)`), así que la información ya está disponible y no hay que inventar semántica nueva.

Nunca se emite `spatial_same_zone` sin dejar constancia de si fue `zone` o `location`. La diferencia entre "misma zona" y "misma casa" es enorme y el sistema no debe confundirlas.

### 3.3 Correlacional — *qué co-ocurre*

| Relación | Regla |
|---|---|
| `correlation_same_label` | comparten al menos una etiqueta detectada |
| `correlation_same_risk` | comparten nivel de riesgo |
| `correlation_overlapping` | ventanas temporales solapadas |
| `correlation_co_occurring` | dentro de una ventana compartida ≤ umbral |

Es la familia que alimenta el Caso 4 ("¿qué cámaras observaron la misma situación?"): `correlation_overlapping` **+** `spatial_same_*`.

### 3.4 Causal aparente — *la más peligrosa, y por eso acotada*

**Definición operativa y cerrada:**

> `temporal_transition` se emite cuando dos episodios son **adyacentes** (gap ≤ umbral), comparten (o degradan a) **identidad espacial**, y **cambia** el conjunto de etiquetas entre el primero y el segundo.

**Qué se puede decir:** *"La reja se abrió 40 segundos antes de la caída."*
**Qué está prohibido decir:** *"La apertura de la reja provocó la caída."*

La diferencia es absoluta: la primera es una **medición**; la segunda es una **atribución de intención o física** que ningún sensor midió.

Esta relación es un **hecho temporal con nombre sugestivo**. El nombre del tipo existe para que los desarrolladores sepan qué están mirando; **nunca llega al lenguaje emitido**. El traductor a lenguaje sólo conoce la forma temporal (§4.2).

---

## 4. Qué puede inferirse y qué está prohibido

Esta sección es el **contrato anti-alucinación**. Es la parte del documento que debe convertirse en tests.

### 4.1 Inferible sin LLM (lista cerrada)

| # | Inferencia | Base |
|---|---|---|
| 1 | Orden entre ocurrencias | marcas de tiempo |
| 2 | Distancia temporal entre ocurrencias | marcas de tiempo |
| 3 | Agrupación por identidad | `zone`, `camera_id`, `location`, `source` |
| 4 | Co-ocurrencia dentro de una ventana | marcas de tiempo |
| 5 | Frecuencia y recurrencia | conteo de registros/episodios |
| 6 | Silencios y huecos | `timeline_gaps` |
| 7 | Transiciones de etiquetas en el tiempo | etiquetas + orden |
| 8 | Severidad máxima de una ventana | orden de riesgo |
| 9 | Duración de una ocurrencia | `episode.duration` |
| 10 | Qué cámaras/zonas cubrieron lo mismo | identidad espacial |

**Diez. Nada más.** Si una pregunta exige el punto 11, la respuesta es abstención.

### 4.2 Prohibido — lista cerrada

| # | Prohibición | Ejemplo prohibido | Por qué |
|---|---|---|---|
| 1 | Atribuir intención | "el ladrón entró para robar" | Ningún sensor mide intención |
| 2 | Afirmar causalidad | "X provocó Y" | Correlación ≠ causa |
| 3 | Identificar personas/animales por nombre | "Firulais estaba en el patio" | El modelo devuelve `PET`, no una identidad |
| 4 | Inventar contenido no almacenado | "se llevó un ordenador" | No está en `model_analysis` |
| 5 | Inventar tiempos o lugares | "hace 3 horas en el garaje" | Debe salir de los registros |
| 6 | Responder con evidencia vacía | cualquier cosa | Debe abstenerse |
| 7 | Mezclar registros fuera del conjunto recuperado | — | Rompería la trazabilidad |
| 8 | Especular sobre lo que habría pasado | "si no se hubiera abierto…" | Conttrafactual puro |
| 9 | Emitir dígitos de confianza como certeza | "92% seguro de que…" | Ver §7.1 |
| 10 | Completar huecos de forma plausible | "probablemente alguien…" | **La palabra "probablemente" está prohibida** |

### 4.3 Guardas en el narrador (diseño, no implementado aún)

El narrator debe fallar hacia la abstención en tres frentes:

| Guarda | Mecanismo |
|---|---|
| **Vocabulario prohibido** | Tabla de palabras vetadas por idioma (`causa`, `porque`, `debido a`, `provocó`, `ladrón`, `probablemente`, `creo`, `parece`…) validada contra cada cláusula emitida. Si aparece una → **la cláusula se descarta y se emite abstención parcial**. |
| **Cita obligatoria** | Ninguna cláusula se emite sin al menos una `record_id` trazable. El validador rechaza cláusulas sin ancla. |
| **Vacío = silencio** | Si el conjunto de relaciones es vacío, el narrador no rellena: narra las evidencias sueltas o se abstiene. |

---

## 5. Estructuras necesarias

> **Todo lo siguiente es diseño propuesto. Nada está implementado.**

### 5.1 `Relation` — la unidad de razonamiento

```python
@dataclass(frozen=True, slots=True)
class Relation:
    kind: str                      # "temporal_precedes" | "spatial_same_zone" | ...
    subject: str                   # record_id o episode_id
    object: str                    # record_id o episode_id
    rule: str                      # id estable de la regla que la produjo
    facts: dict[str, object]       # los números crudos detrás de la afirmación
    degraded: bool = False         # ¿se usó una identidad degradada?
    fallback: str | None = None    # cuál fue el fallback, si lo hubo
```

Decisiones de diseño y su justificación:

| Decisión | Razón |
|---|---|
| `facts: dict` en vez de campos tipados | Mantiene el dataclass cerrado mientras cada regla aporta sus propios números. El narrador lee sólo lo que conoce. |
| **`degraded` en vez de `confidence`** | Ver §7.1 — es la decisión de semántica más importante del documento. |
| `rule: str` estable | Permite auditar qué código produjo qué afirmación, años después. |
| `frozen` + `slots` | Coherente con `MemoryRecord`, `Episode`, `Evidence`. Inmutable = replayable. |

### 5.2 `AnchorRef` — el mecanismo que habilita los Casos 1, 2 y 5

Este es el concepto **nuevo** más importante de A6.

Las ventanas actuales se anclan a `NOW` o `SESSION_START`. Los Casos 1/2/5 necesitan anclarse a **un momento del pasado**: el instante de la caída, el de la apertura de la reja.

```python
@dataclass(frozen=True, slots=True)
class AnchorRef:
    record_id: str
    ts: float
    label: str
    location: str
    camera_id: str | None
    zone: str | None
```

**Mecanismo de dos pasadas** (la idea central de A6):

```
PASO 1  —  "¿cuándo fue la caída?"
          retrieve LAST_SEEN / SEARCH con el ancla
          → 0 resultados  ⇒  abstención total  (sin ancla no hay ventana)
          → 1 resultado   ⇒  AnchorRef
          → >1 resultados ⇒  el más reciente, y el trace lo declara

PASO 2  —  "¿qué había antes/después/alrededor?"
          ventana = [anchor.ts - N, anchor.ts]   o   [anchor.ts, anchor.ts + N]
          retrieve RANGE sobre esa ventana
          relations sobre esa ventana
```

**Desempate determinista y declarado:** si el ancla es ambigua se usa la más reciente (`ts` descendente, `id` como desempate) **y el trace registra `anchor_candidates: n`**. La respuesta nunca finge que no hubo ambigüedad.

**Si no hay ancla, no hay respuesta contextual.** No se intenta "aproximar": se abstiene. Esta es la regla que impide el 100 % de las respuestas plausibles-but-wrong de este tipo.

### 5.3 `episodes_after()` — la pieza que falta en A2

Existe `episodes_before(episodes, target_ts)`. Falta su espejo:

```python
def episodes_after(episodes, *, target_ts: float) -> tuple[Episode, ...]:
    """Keep the episodes that started at or after ``target_ts``."""
```

Simétrico, misma firma, misma semántica de borde (`>=` frente al `<=` actual). Sin esto el Caso 2 no existe.

### 5.4 Reglas como tabla, no como código ramificado

Siguiendo el patrón que el propio `recall_planner.py` ya establece ("adding a use case means adding a table row"):

```python
RELATION_RULES: tuple[RelationRule, ...] = (
    RelationRule(id="temporal.precedes", kinds=..., applies=..., build=...),
    ...
)
```

Añadir un tipo de relación = añadir una fila. **Ningún `if` nuevo en el motor.**

### 5.5 Traza ampliada

`RecallTrace.ops_executed` ya recibe entradas `{"op": "relate", ...}`. A6 añade, sin tocar las existentes:

```json
{
  "op": "relate",
  "relation": "spatial",
  "groups": {...},
  "degraded": true,
  "anchor": {"record_id": "...", "ts": ..., "candidates": 3},
  "relations": [
    {"kind": "temporal_precedes", "subject": "...", "object": "...",
     "rule": "temporal.precedes", "facts": {"seconds": 40.0}, "degraded": false}
  ]
}
```

**Aditivo.** Las claves existentes de `relate` no cambian → los 376 tests siguen en pie.

### 5.6 Narrador guiado por relaciones

`render_utterance` (A1) narra evidencias **sueltas**. A6 añade un narrador hermano, no un reemplazo:

| Función | Cuándo se usa | Estado |
|---|---|---|
| `render_utterance` | plan sin relaciones relevantes | **se mantiene intacto** |
| `render_relational_utterance` | plan con relaciones/anchor | nuevo |
| `render_abstention` | sin evidencia o sin ancla | **se mantiene intacto** |

El engine elige: si el plan no produjo relaciones significativas → narrador clásico (comportamiento idéntico al de hoy). Esto es lo que garantiza que A6 sea **estrictamente aditivo**.

---

## 6. Cómo responder preguntas contextuales

### 6.1 La regla de composición

> **Cada cláusula del utterance nace de exactamente una relación o de exactamente una evidencia. Nunca de una mezcla.**

Esto hace que la respuesta sea auditable cláusula a cláusula: puedes señalar cada frase con el dedo y decir "esta viene de aquí".

### 6.2 Los 5 casos objetivo, resueltos sobre esta arquitectura

#### Caso 1 — *¿Qué ocurrió antes de la caída?*

| Fase | Operación |
|---|---|
| Ancla | `LAST_SEEN` con etiqueta del evento caída → `AnchorRef` |
| Ventana | `[anchor.ts - ventana, anchor.ts]` |
| Relación | `temporal_precedes` (todos los episodios que terminan antes del ancla) |
| Narración | lista temporal con distancia al ancla |
| Vacío | "No ocurrió nada antes registrado." |

#### Caso 2 — *¿Qué pasó después de la apertura de la reja?*

Idéntico, con `episodes_after()` (§5.3). **Requiere la pieza que hoy no existe.**

#### Caso 3 — *¿Qué eventos están relacionados?*

Sin ancla. Se recuperan los episodios de la ventana y se enumeran relaciones por **número de factores compartidos** (etiqueta + zona + riesgo + solape), con ordenación determinista y tope máximo. La respuesta cita los pares y **el factor concreto** que los une — nunca dice "están relacionados" sin decir *por qué*.

#### Caso 4 — *¿Qué cámaras observaron la misma situación?*

`correlation_overlapping` + `spatial_same_*`, resolviendo identidad con `resolve_camera` (A5). Es el caso donde A5 rinde fruto directo: **la correlación por dispositivo ya está calculada en el engine, falta narrarla.**

#### Caso 5 — *¿Qué estaba ocurriendo alrededor de X?*

Ancla + ventana **simétrica** `[anchor.ts − N, anchor.ts + N]`, excluyendo el propio ancla del resultado para que la respuesta sea contexto, no eco. Relación dominante: `temporal_within` / `correlation_co_occurring`.

### 6.3 Política de vacío

| Situación | Respuesta |
|---|---|
| Sin ancla resoluble | Abstención total |
| Ancla resoluble, ventana vacía | "Antes/después de X no hay registros." |
| Relaciones vacías, evidencias presentes | Narrador clásico de A1 (sin fingir relación) |
| Todo vacío | `render_abstention` |

**Nunca se rellena un hueco con una formulación plausible.**

---

## 7. Riesgos

### 7.1 La trampa de `confidence` — el riesgo nº 1

`Evidence.confidence` (A1) es la **confianza de la detección del modelo de visión**. Si `Relation` expusiera `confidence`, un lector humano y cualquier consumidor JSON interpretarían que es "la probabilidad de que la relación sea cierta". **No lo es**, y mezclarlos sería un error semántico grave con consecuencias reales en un sistema de seguridad.

**Decisión:** `Relation` **no lleva `confidence`**. Lleva `degraded: bool` + `fallback: str | None`, heredando el patrón ya validado en A5. "¿Fue exacta o aproximada?" es una pregunta con respuesta binaria y verificable; "¿qué tan segura está?" no lo es en un sistema determinista.

### 7.2 Fuga de lenguaje causal

El riesgo de que "relación temporal" se convierta en "causa" **en la frase emitida**. Mitigación en tres capas:

1. El tipo de relación se llama `temporal_transition`, no `causal`.
2. El traductor a lenguaje sólo conoce la forma temporal.
3. Tests con tabla de palabras vetadas (§4.3) que **fallan el build** si aparecen.

### 7.3 Ancla ambigua → ventana correcta pero equivocada

Si "la caída" se resuelve contra la caída equivocada, **toda** la respuesta es internamente coherente y externamente falsa. Es el fallo más insidioso porque nada la marca como errónea.

Mitigación: desempate determinista + `anchor_candidates` en el trace + respuesta que, si hubo ambigüedad, puede mencionarlo.

### 7.4 Explosión combinatoria

Relaciones por pares = O(n²). Sobre registros crudos con cientos de eventos es inviable.

Mitigación: el nivel de razonamiento opera sobre **`Episode`** (ya coalescido, órdenes de magnitud menos), con **tope duro** de relaciones emitidas y poda por ventana. El tope es un parámetro con default, no un número mágico disperso.

### 7.5 Indeterminismo accidental

`set` y `dict` no garantizan orden. Una respuesta que cambia entre ejecuciones destruye la confianza y hace imposible el testing.

Mitigación: **todas** las listas de relaciones y grupos se ordenan con clave total determinista (`(timestamp, id)` o `(kind, subject, object)`). Regla verificable por test.

### 7.6 Latencia en Alexa+

Todo es aritmética sobre memoria local — sin llamadas de red ni de modelo — pero el ancla requiere **dos** pasadas de recuperación.

Mitigación: medir y fijar presupuesto en A6b antes de añadir más reglas. Si no se cumple, se recorta el tope de relaciones, no la trazabilidad.

### 7.7 Deriva de V1

El mayor riesgo operativo: que A6 toque el camino de `memory_converse`.

Mitigación estructural: **`memory_converse` no recibe ninguna llamada nueva.** A6 vive íntegramente en `recall_engine` + nuevos módulos puros de dominio. El plan de verificación incluye el hash de `memory_resolvers.py` como fichero que **no debe cambiar**.

---

## 8. Casos reales

Dataset hipotético sobre el que los tests de A6 deberían construirse:

| id | ts | location | zone | camera_id | labels | risk |
|---|---|---|---|---|---|---|
| `m-1` | 1000 | patio | outdoor | cam-01 | GATE_OPEN | MEDIUM |
| `m-2` | 1040 | patio | outdoor | cam-01 | GATE_OPEN | MEDIUM |
| `m-3` | 1080 | patio | outdoor | cam-02 | PERSON, FALL | CRITICAL |
| `m-4` | 1095 | patio | outdoor | cam-01 | PET | LOW |
| `m-5` | 1400 | kitchen | indoor | cam-03 | SMOKE | HIGH |

| Pregunta | Ancla | Ventana | Relación dominante | Respuesta esperada |
|---|---|---|---|---|
| ¿Qué ocurrió antes de la caída? | `m-3` (FALL) | (−∞, 1080] | `temporal_precedes` | "La reja se abrió hace 40 segundos." |
| ¿Qué pasó después? | `m-3` | [1080, +∞) | `temporal_follows` | "Una mascota apareció 15 segundos después." |
| ¿Qué cámaras observaron lo mismo? | — | ventana | `correlation_overlapping` + `spatial_same_zone` | "cam-01 y cam-02, ambos en outdoor." |
| ¿Qué ocurría alrededor? | `m-3` | [1000, 1160] | `correlation_co_occurring` | reja + caída + mascota |
| ¿Qué ocurrió antes de la caída **de la semana pasada**? | **0 resultados** | — | — | **Abstención** |

La última fila es tan importante como las cuatro anteriores: **demuestra que el sistema prefiere no responder antes que responder mal.**

---

## 9. Compatibilidad Alexa+

| Requisito | Respuesta de diseño |
|---|---|
| **Habla, no muestra** | Utterance = frases cortas, sin markdown, sin JSON, sin IDs en la voz. Los `record_id` van en el trace, no en el habla. |
| **Latencia** | Cero llamadas de modelo o red. Aritmética local + 2 pasadas de recuperación. Presupuesto a fijar y medir en A6b. |
| **Longitud** | Tope de cláusulas en el narrador (el `_MAX_LINES = 3` de A1 ya es el precedente). Alexa corta respuestas largas. |
| **Abstención hablable** | `render_abstention` (A1) ya existe y se mantiene. Frase corta, sin disculpas冗ndas. |
| **Ambigüedad** | Si el ancla fue ambigua, puede mencionarse en una cláusula corta sin sonar a error del sistema. |
| **Idioma** | ES/EN desde A1. Toda plantilla nueva nace bilingüe, no se traduce después. |

**Restricción añadida y deliberada:** la voz **nunca** dice "causa", "probablemente" ni porcentajes. La tabla de palabras vetadas se aplica al habla con la misma dureza que al texto.

---

## 10. Compatibilidad MCP

| Superficie | Impacto de A6 | ¿Rompe algo? |
|---|---|---|
| `MEMORY_TOOL_NAMES` / catálogo V1 | **sin cambios** — no se añade tool | No |
| `memory_converse` | **sin cambios** — cero llamadas nuevas | No |
| `memory_recall` | hereda el narrador relacional cuando el plan lo produce | No — aditivo |
| `/api/recall` | clave `anchor` y `relations` dentro de `trace` | No — claves nuevas |
| `RecallResult` / `RecallTrace` | campos **opcionales** con default | No — compatible |
| `PLAN` en el trace | ya serializa `relations`; se mantiene igual | No |

**MCP y Alexa+ comparten el mismo motor.** El narrador se parametriza por `lang` y el consumidor decide qué hacer con `trace`: el MCP lo expone completo para auditoría; Alexa lo descarta y sólo habla el `utterance`.

---

## 11. Partes que siguen siendo deterministas

**Todas.** No hay ninguna zona del sistema donde A6 introduzca aleatoriedad, aprendizaje o llamada a modelo:

| Componente | Determinismo |
|---|---|
| Resolución de ancla | Tabla + desempate total por `(ts, id)` |
| Ventanas | Aritmética pura sobre floats |
| Cálculo de relaciones | Tabla de reglas, sin ramificación |
| Orden de relaciones | Clave total explícita |
| Selección de cláusulas | Orden fijo, tope fijo |
| Redacción | Plantillas bilingües cerradas |
| Abstención | Frase literal |

**El LLM sigue estando donde estaba: fuera.** A6 es la demostración de que un sistema puede contestar "¿qué pasó antes?" sin haber entendido nunca qué es una caída.

---

## 12. Roadmap A6

Cada sub-fase es independiente, verificable y reversible. Ninguna toca `memory_converse`.

### A6a — Cimiento relacional *(dominio puro, sin behavior)*
- `Relation` + `RelationRule` en `src/domain/services/relation.py`
- Tabla de reglas vacía o con 2 reglas triviales
- Tests de estructura, inmutabilidad, serialización
- **Criterio:** 0 cambios en comportamiento observable. Huella: sólo ficheros nuevos.

### A6b — Simetría temporal *(la pieza que falta)*
- `episodes_after()` en `memory_timeline.py`
- Tests espejo de los de `episodes_before`
- Presupuesto de latencia medido y fijado
- **Criterio:** Caso 2 técnicamente posible.

### A6c — Anclaje a evento *(habilita Casos 1, 2, 5)*
- `AnchorRef` + resolución de ancla en `RecallEngine`
- Desempate determinista + `anchor_candidates` en el trace
- Abstención total sin ancla
- **Criterio:** Caso 1 responde de verdad; sin ancla se abstiene.

### A6d — Motor de relaciones sobre episodios
- Reglas temporal/espacial/correlacional sobre `Episode`
- Orden determinista + tope duro de relaciones
- Integración en `_relate` **sin tocar** el utterance aún
- **Criterio:** relaciones en el trace, respuesta idéntica a hoy.

### A6e — Narrador relacional *(el cierre del circuito)*
- `render_relational_utterance` con regla "una cláusula = una relación"
- Tabla de palabras vetadas ES/EN + tests que fallan el build
- Selección entre narrador clásico y relacional
- **Criterio:** Casos 1–5 responden; ningún test V1/A1–A5 cambia.

### A6f — Integración y trazabilidad
- `/api/recall` expone `anchor` + `relations`
- Prueba de impacto cero (hash de `memory_resolvers.py` intacto)
- Informe `A6_IMPLEMENTATION_REPORT.md`
- **Criterio:** DoD cerrado, sin commits.

---

## 13. Fuera de alcance (declarado, no implícito)

| Excluido | Motivo |
|---|---|
| Cualquier LLM (Ollama, Bedrock, cualquier modelo) | El objetivo es razonar **sin** él |
| Razonamiento libre o generación abierta | Contradice §4 |
| Migración de `memory_converse` a `memory_recall` | Fase G, decisión aparte |
| Digital Twin / Facility Maps | Sigue fuera; sin mapas no hay "adyacencia" real entre zonas |
| Identificación de personas o animales | Ningún sensor la da |
| Persistencia de relaciones | Son derivadas; persistirlas las haría obsoletas |
| Aprendizaje de umbrales | Los umbrales son parámetros fijos, no aprendidos |

---

## 14. Verificación prevista

Antes de escribir la primera línea de A6a, este documento define cómo se probará:

| Tipo de prueba | Qué fija |
|---|---|
| Tests de estructura | `Relation` inmutable, serializable, con default `degraded=False` |
| Tests de determinismo | misma entrada → salida **idéntica** byte a byte, N veces |
| Tests de orden | ninguna salida depende de `set`/`dict` iteration |
| Tests de prohibición | tabla de palabras vetadas; una fuga rompe el build |
| Tests de cita | ninguna cláusula sin `record_id` ancla |
| Tests de abstención | sin ancla ⇒ abstención; ventana vacía ⇒ frase literal |
| Prueba de impacto cero | SHA-256 antes/después; `memory_resolvers.py` **intacto** |
| Gates | `pytest`, `flake8`, `black` — igual que A1–A5 |

---

## 15. Conclusión

EchoMind ya sabe **observar, recordar, recuperar y relacionar**. A6 añade **razonar** — y lo añade no como una capa de generación sino como una capa de **comparación computada sobre hechos**, con procedencia completa y vocabulario cerrado.

La restricción no es una limitación del diseño: **es el diseño**. Un sistema de seguridad que no sabe qué no sabe es más peligroso que uno que se calla.

EchoMind se calla cuando no tiene pruebas. Y cuando las tiene, puede decir exactamente por qué las tiene.
