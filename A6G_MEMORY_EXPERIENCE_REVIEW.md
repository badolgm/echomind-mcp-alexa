# A6g — Revisión de Experiencias de Memoria Reales

**Fecha:** 2026-10-18
**HEAD:** `b963c5f` — sin commits, sin push.
**Modo:** revisión y ejecución. **Cero líneas de código modificadas** (prueba en §8).

---

## Pregunta central

> ¿Qué experiencias de memoria conversacional ya son posibles con EchoMind hoy?

**Respuesta corta:**

1. **A nivel de datos/traza: las seis preguntas producen salida real.** El
   motor recupera evidencia, cuenta etiquetas, agrupa por zona y por cámara,
   calcula silencios temporales, resuelve anclas y genera un grafo de
   relaciones con narración — todo correcto, determinista y auditable.
2. **A nivel de experiencia conversacional hablada: ninguna de las seis
   responde a la pregunta que se le hace.** Los seis casos producen hoy
   *exactamente el mismo* `response`:

   > `GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas.`

   Son **las 3 líneas más antiguas de la ventana**, idénticas para las seis
   preguntas, porque `render_utterance` narrifica únicamente la evidencia
   (`recall_engine.py:113`) y **los resultados de `relate` y `aggregate` nunca
   llegan a la respuesta**.
3. **Una experiencia de las seis sí es funcional hoy**, con la reformulación
   que el clasificador entiende: *"¿Cuándo fue la última vez que viste la
   mascota?"* → `PET en jardin, hace 5 horas. PET en patio, hace 30 minutos.
   PET en patio, hace 10 minutos.`

---

## 1. Método

- **Qué se ejecutó:** los entry points reales — `understand()` (planificador),
  `recall()` (resolver MCP/HTTP, el mismo que usa `memory_recall`),
  `RecallEngine.execute()`, capa de contexto y narración, y `_render` de MCP.
- **Datos:** fixture doméstico de **12 registros / 12 episodios / 4 cámaras /
  7 zonas-ubicaciones**, con sesión de 7 h, una caída (`FALL DETECTED`) y humo
  simultáneo en dos cámaras. `NOW` fijo (`1760000000.0`), sin reloj vivo.
- **Dos modos de ejecución:** MCP real (`build_memory_recall_resolver(memory)`
  → `session_start=None`, `memory_resolvers.py:541`) y HTTP real
  (`/api/recall` con `session_start`, `main.py:243`).
- **Contrafactuales:** planes construidos directamente contra el *mismo* motor
  para medir qué es *capacidad del motor* hoy vs. *lo que el planificador no
  pide*. No hay código nuevo en el repo: los harness viven en el directorio
  temporal del sistema.
- **Clasificación usada:**
  - **FUNCIONAL** — la salida conversacional responde a la pregunta.
  - **PARCIAL** — el sistema calcula parte de la respuesta (traza/contexto) o
    la entrega por coincidencia de datos, pero la respuesta hablada no está
    dirigida a la pregunta.
  - **IMPOSIBLE (tal como se formula)** — ni el plan ni el motor llegan a
    tocar la capa de respuesta para esa pregunta.

---

## 2. Veredicto por caso

| # | Pregunta | Estado | Qué responde hoy | Qué falta |
|---|---|---|---|---|
| 1 | ¿Dónde vi mi mascota? | **PARCIAL** | Las 3 líneas antiguas (una por casualidad es `PET en jardin, hace 5 horas`) | No enruta a `last_seen`; sin `label`/`location` en el plan |
| 2 | ¿Qué ocurrió antes de la caída? | **PARCIAL** | Mismas 3 líneas; traza `before_after target_ts=AHORA, 12/12 episodios` | `plan.anchor` **nunca se fija** → no hay "la caída" como referencia |
| 3 | ¿Qué ocurrió después de la caída? | **PARCIAL** | Idéntico al caso 2, byte a byte | Ancla (B1) **y** dirección: `episodes_after` no se invoca jamás (B2) |
| 4 | ¿Qué pasó mientras estaba fuera? | **PARCIAL** | Mismas 3 líneas; la traza sí tiene 7 silencios temporales reales | MCP descarta `session_start` (B5); la respuesta no resume la ventana |
| 5 | ¿Qué eventos están relacionados? | **IMPOSIBLE (como se formula)** | Mismas 3 líneas; `relations=[]` → **la capa de relaciones ni se activa**; `context_response=''` | "relacionados" no existe en el vocabulario de relaciones (B4) |
| 6 | ¿Qué cámaras observaron la misma situación? | **PARCIAL** | Mismas 3 líneas; la traza **sí** responde: 4 grupos por cámara; el contexto narra `SMOKE en el mismo instante.` | La respuesta no lo dice; la narración nunca nombra cámaras (B8) |

**0/6 funcionales tal como se preguntan · 5 parciales · 1 imposible.**
Con reformulación natural: el **caso 1 se vuelve funcional** (§4-F1); el 5 se
activa diciendo *"al mismo tiempo"*; los 2/3 **no hay reformulación que los
salve** hasta que el planificador fije el ancla.

---

## 3. Caso a caso: real vs. esperado vs. diferencia exacta

### Caso 1 — ¿Dónde vi mi mascota?

**Plan real:** `intent=search`, `relations=[spatial]`, `anchor=None`,
`entities=[text: "¿dónde vi mi mascota?"]`, `ops=[search, range]`.

**Salida real (MCP):**

```
response         = "GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas."
evidence         = 12 (los 12 registros)
trace            = retrieve:search count=5 ids=[m-11, m-03, m-04, m-12, m-01]
                   retrieve:range count=12
                   relate:spatial groups={patio:6, jardin:1, salon:3, cocina:2} degraded=False
                   relate:derived count=64 (cap) narratable=1
context_response = "SMOKE en el mismo instante."
```

**Esperado:** *"La última vez que vi la mascota fue en el patio, hace 10
minutos."*

**Diferencia exacta:**
- `"dónde"` sólo fija la relación `SPATIAL` (`recall_planner.py:47`), que
  agrupa por zona **en la traza** — nunca en la respuesta.
- `_extract_label("mascota") → PET` **sólo se ejecuta en la rama
  LAST_SEEN** (`memory_intent.py:249-255`); "¿dónde vi…?" no matchea
  `_LAST_SEEN_RE` (`memory_intent.py:175-179`, exige *"cuándo viste /
  última vez / when did you see"*). El plan queda sin entidad.
- La mención `PET en jardin` aparece **por coincidencia**: es el 3.º registro
  más antiguo del almacén. Con 500 registros, desaparecería.

**Contrafactual (mismo motor):** plan `last_seen(PET)` →
`"PET en patio, hace 10 minutos."` con `evidence=1` — el motor puede, el
plan no lo pide.

### Caso 2 — ¿Qué ocurrió antes de la caída?

**Plan real:** `intent=summary (hours=24)`, `relations=[before_after]`,
**`anchor=None`**, `ops=[range, aggregate(summary)]`.

**Salida real:**

```
response   = "GATE_OPEN en patio, hace 6 horas. ..."   (idéntica al caso 1)
trace      = retrieve:range count=12
             retrieve:aggregate agg=summary
                 label_counts={'GATE_OPEN':1,'PERSON':3,'PET':3,'MOTION':2,
                               'FALL DETECTED':1,'PERSON_ELDERLY':1,'SMOKE':2}
             relate:before_after target_ts=1760000000.0  episodes=12 count=12
```

**Esperado:** *"Antes de la caída: reja abierta hace 6 h, persona hace 6 h,
movimiento 3 minutos antes… (5 episodios previos)."*

**Diferencia exacta:** `target_ts` es **`NOW`**, no el instante de la caída →
*"antes de la caída"* se calcula como *"antes de ahora"* → **12 de 12
episodios, es decir, todo**. La ventana tampoco se reconstruye alrededor del
evento.

**Contrafactual (mismo motor):** plan con `anchor="FALL DETECTED"` →

```
trace      = anchor label=FALL DETECTED found=True
             relate:before_after target_ts=1759985600.0  episodes=5 count=5
```

**El motor ya responde correctamente a "antes de la caída"**: encuentra la
ancla y corta en 5 episodios. El planificador no la fija nunca (B1).

### Caso 3 — ¿Qué ocurrió después de la caída?

**Plan real:** idéntico al caso 2 salvo el texto de `entities`/`query`.
**Salida real:** idéntica al caso 2 (el motor ignora `query` en
`range`/`aggregate`).

**Diferencia exacta (dos capas):**
- **B1:** misma ancla ausente.
- **B2:** *"antes de"* y *"después de"* mapean a **la misma**
  `RelationKind.BEFORE_AFTER` (`recall_planner.py:31,33`) y el motor sólo
  ejecuta `episodes_before` (`recall_engine.py:281-290`).
  `episodes_after` existe, está probado con 5 tests
  (`memory_timeline.py:111-121`) y **no tiene ningún llamador en `src/`**:
  hoy es código muerto desde el motor.
- Comprobado: `plan_to_dict` de "antes" vs "después" difiere **sólo** en
  `entities` y en el `query` de los ops → salidas finales idénticas.

### Caso 4 — ¿Qué pasó mientras estaba fuera?

**Plan real:** `intent=summary`, **`window.anchor=session_start` ✓**,
`relations=[timeline]`, `ops=[range, aggregate]`.

**Salida real:**

```
response   = "GATE_OPEN en patio, hace 6 horas. ..."   (idéntica)
trace      = relate:timeline episodes=12
                 gaps=[3300s, 3420s, 750s, 6300s, 3600s, 1800s, 1200s]   ← 7 silencios reales
```

**Esperado:** *"Mientras estabas fuera ocurrieron 12 eventos; hubo silencios
de hasta 1 h 45 min; la caída fue a las…"*

**Diferencia exacta:**
- **La frase-correctora funciona**: `"mientras estaba fuera"` →
  `Anchor.SESSION_START` (`recall_planner.py:56`), y con `session_start` la
  ventana se recorta al periodo real.
- **Pero el MCP lo descarta**: el dispatch construye
  `build_memory_recall_resolver(memory)` **sin `session_start`**
  (`memory_resolvers.py:541`) y el schema de la herramienta
  (`tools.py:295-311`) ni siquiera lo declara → la ventana cae a "últimas
  24 h". Sólo `/api/recall` lo admite (`main.py:195,243`).
- **Prueba empírica (sonda):** con un registro de hace 10 h (anterior a la
  salida), MCP lo incluye (`evidence=13`, respuesta empieza *"GATE_OPEN en
  jardín, hace 10 horas…"*) y HTTP con `session_start` lo excluye
  (`evidence=12`) → `same response? False`.
- Los 7 `gaps` calculados viven **sólo en la traza**; la respuesta no los
  nombra y la narración no los consume.

### Caso 5 — ¿Qué eventos están relacionados?

**Plan real:** `intent=search`, **`relations=[]`**, `entities=[text]`,
`ops=[search, range]`.

**Salida real:**

```
response         = "GATE_OPEN en patio, hace 6 horas. ..."   (idéntica)
context_items    = 0
context_response = ""          ← la capa de contexto ni se activa
trace            = retrieve:search / retrieve:range   ← sin NINGÚN "relate"
```

**Esperado:** la lista de eventos relacionados (p.ej. *la reja → la persona →
la caída*).

**Diferencia exacta (B4):** el vocabulario `_RELATION_PHRASES`
(`recall_planner.py:30-53`) no contiene *relación / relacionado / related /
entre*. El plan sale con `relations=()`, `_relate()` no recorre nada y
`_derive_relations` se salta (`recall_engine.py:299`, exige `plan.relations`).
**La pregunta más "de contexto" de las seis es la única que no llega a la
capa de contexto.**

**Contrafactual (mismo motor):** con `relations=(TIMELINE, BEFORE_AFTER,
CORRELATION, SPATIAL)` a mano → todo se ejecuta: `gaps`, `before_after`,
`groups` por cámara y por zona, `derived count=64`, `context_items=64`,
`narratable=1`. Rephrases que ya activan la capa hoy: *"al mismo tiempo"*,
*"junto con"*, *"simultáne…"* (`recall_planner.py:37-41`).

### Caso 6 — ¿Qué cámaras observaron la misma situación?

**Plan real:** `intent=search`, `relations=[correlation]`, `ops=[search, range]`.

**Salida real:**

```
response   = "GATE_OPEN en patio, hace 6 horas. ..."        (idéntica)
trace      = relate:correlation groups={
               cam-1: [m-01, m-02, m-04, m-05, m-11, m-12],
               cam-2: [m-03],
               cam-3: [m-06, m-09, m-10],
               cam-4: [m-07, m-08]} degraded=False
context    = "SMOKE en el mismo instante."    ← narración real (m-08 cocina/cam-4 + m-09 salón/cam-3)
```

**Esperado:** *"Las cámaras cam-3 y cam-4 observaron humo a la vez."*

**Diferencia exacta:**
- **La respuesta estructurada SÍ existe**: la traza agrupa por `camera_id`
  degradando a `source` cuando falta (`recall_engine.py:401-432`) — con
  `degraded=False`, o sea, con precisión de cámara real.
- La **narración ya dice el núcleo del hallazgo** (*"en el mismo instante"*,
  el caso `overlap_seconds==0` de A6f) pero narra **etiquetas, no cámaras**:
  `context_narrative.py` sólo consume `facts` de tiempo/etiquetas — no existe
  ningún `facts` con cámaras.
- `context_response` **no llega al usuario MCP**: `_render`
  (`recall_resolvers.py:100-115`) emite `response + evidencia + trace`,
  **nunca** `context_response`. (Sí está en el JSON de `/api/recall`,
  `recall_resolvers.py:96`.)

---

## 4. Experiencias funcionales que ya existen hoy

Comprobadas ejecutando, no por lectura:

- **F1 — "¿Cuándo fue la última vez que viste la mascota?"** (reformulación
  del caso 1): `intent=last_seen, label=PET, ops=[last_seen(PET),
  range(PET)]` → **respuesta 100 % dirigida a la pregunta**:
  `"PET en jardin, hace 5 horas. PET en patio, hace 30 minutos. PET en patio,
  hace 10 minutos."` con `evidence=3` (sólo mascota). *Existe hoy, sin
  cambios.*
- **F2 — Resumen con conteo por etiquetas en traza:** `aggregate(summary)`
  devuelve `label_counts` correctos (`{'PET':3, 'PERSON':3, 'SMOKE':2, …}`).
- **F3 — Dónde/cuándo se vio algo:** `last_seen` + `range` con entidad →
  evidencia filtrada y fechada (`recall_engine.py:178-197`).
- **F4 — Silencios temporales:** 7 `gaps` reales en el caso 4.
- **F5 — Qué vio cada cámara:** grupos por `camera_id` con `degraded=False`
  (caso 6).
- **F6 — Anclaje a un evento:** `anchor found=True`, `target_ts` exacto de la
  caída, 5 episodios previos (contrafactual CF2) — el motor está listo.
- **F7 — Narración contextual:** frases reales en español sobre hechos
  (`"SMOKE en el mismo instante."`), con `context_response` ya publicado en
  el payload HTTP.

Lo que **no** hace falta rebuildar: evidencia, traza, timeline, espacial,
relaciones, contexto, narración, ancla. Todo está construido y probado
(535 tests).

---

## 5. Brechas reales

| ID | Brecha | Ubicación | Evidencia |
|---|---|---|---|
| **B1** | **`plan.anchor` nunca se fija**: `understand()` construye `RecallPlan` sin `anchor=` — sólo los tests lo hacen (grep: 1 único constructor en `src/`, en `recall_planner.py:106`) | `recall_planner.py:106-114` vs `recall_engine.py:92-97` | CF2: `found=True, episodes=5` vs real `target_ts=NOW, episodes=12`. **Los casos 2/3 son imposibles con cualquier reformulación.** |
| **B2** | **Sin dirección antes/después**: ambas frases → `BEFORE_AFTER`; el motor sólo llama `episodes_before` | `recall_planner.py:31,33`, `recall_engine.py:281-290`, `memory_timeline.py:111` (`episodes_after`: 5 tests, **0 llamadores en src**) | Casos 2 y 3 producen plan y salida idénticos |
| **B3** | **La respuesta es insensible a la pregunta**: `response = 3 líneas más antiguas` de la ventana; `relate` y `aggregate` no entran en la utterance | `recall_engine.py:105` (orden ascendente), `evidence.py:17,173` (`_MAX_LINES=3`), `recall_engine.py:113` | **6 preguntas → 1 respuesta idéntica.** Sonda: *"¿cuántos eventos…?"* deja el `12` **sólo en la traza** y responde 3 líneas de eventos |
| **B4** | **"relacionados" no es disparador de relaciones**: vocabulario sin *relación/related/entre* | `recall_planner.py:30-53` | Caso 5: `relations=[]`, `context=0`, `context_response=''` |
| **B5** | **El MCP descarta `session_start`** y ni lo declara en el schema | `memory_resolvers.py:541`, `tools.py:295-311` (HTTP sí: `main.py:195,243`) | Sonda: `evidence 13 vs 12`, respuestas distintas |
| **B6** | **Entidades no se extraen salvo en rama LAST_SEEN**: 4 de 6 casos viajan con `entities=[text: pregunta completa]` → ops sin `label/location/risk` | `memory_intent.py:249-255`, `recall_planner.py:147-158` | Casos 1, 5, 6: `ops=[(search, None, None), (range, None, None)]` |
| **B7** | **El cap corta la narración**: grafo ordenado por `(kind, subject, object)` —alfabético— y luego `[:64]`; `temporal_transition` va el último de los 6 kinds → siempre truncado | `relation_rules.py:28,106-111` | **110 pre-cap → 64** con sólo 12 registros; `temporal_precedes 66→22`; **`temporal_transition 2→0`**; narrables **3→1** |
| **B8** | **La narración no llega al canal MCP** (ni se nombran cámaras en `facts`) | `recall_resolvers.py:100-115` vs payload `:96`; `context_narrative.py` | Sonda: `_render contains context_response? False` |
| **B9** | **Episodios muy fragmentados**: 12 registros → 12 episodios (cambia etiqueta/ubicación → episodio nuevo aunque los tiempos peguen) | `memory_timeline.py:69-81` | Cada `same_zone/precedes` compara episodios de 1 registro; reduce transiciones narrables |

**No es una brecha de motor en casi ningún caso:** B1–B6 y B8 son del lado
del planificador/superficie; el motor ejecuta bien lo que se le pide (CF1,
CF2, CF5 lo demuestran).

---

## 6. Próxima fase recomendada

**Propuesta A7 — "Cierre plan↔motor"** (sólo si se aprueba; A6g no toca nada).
En orden de retorno de experiencia:

1. **Hacer que la respuesta siga la pregunta (B3):** ordenar la evidencia
   descendente (lo más reciente primero) y renderizar en `response` los
   resultados de `relate`/`aggregate` que la pregunta disparó (conteos,
   gaps, grupos, episodios anclados). Es la brecha que separa "traza correcta"
   de "experiencia conversacional". *Incluye decidir límite de líneas.*
2. **Cablear `plan.anchor` desde el planificador (B1) + dirección
   antes/después (B2):** detectar la entidad ancla ("la caída" →
   `FALL DETECTED`, tabla ya existente en `_LABEL_TERMS`) y usar
   `episodes_after` cuando la frase sea "después de". *Desbloquea los casos
   2 y 3 completos — el motor ya está probado (CF2).*
3. **Ordenar el grafo por `salience` antes del cap (B7):**
   `key=(-salience, kind, subject, object)` — un solo cambio que evita que
   las 2 frases narrables se corten siempre. *Revaloriza todo lo construido
   en A6f.*
4. **Vocabulario de relaciones (B4) + `session_start` en MCP (B5):** fila de
   tabla para *relacionados/related* (con el kind que decida el diseño) y
   `session_start` en el dispatch y schema. *Desbloquea los casos 5 y 4.*
5. **Decisión de producto pendiente (A6f/A6g):** mostrar —y dónde—
   `context_response` al usuario final (hoy invisible en MCP).

No reproponer: nueva arquitectura, motores, adapters, dashboards, sensores ni
modelos — nada de eso es lo que falta.

---

## 7. Preguntas del encargo respondidas

1. **¿Qué casos ya pueden producirse?** Los 6 producen traza real y evidencia
   correcta; **0 de 6 responden habladamente**; 1 es funcional con
   reformulación natural (F1); el 5 es el único que ni siquiera activa la
   capa de contexto.
2. **¿Cuáles todavía no?** Como se preguntan: **todos a nivel de respuesta**;
   en profundidad: 2 y 3 (ancla+dirección, B1/B2) y 5 (vocabulario, B4) son
   los **bloqueos duros**; 4 depende de que MCP pase `session_start` (B5).
3. **¿Cuál es la salida real?** Mismo `response` para los 6 casos (§2) +
   trazas correctas y una frase de contexto (`"SMOKE en el mismo instante."`).
4. **¿Cuál es la salida esperada?** Secciones §3 por caso.
5. **¿Cuál es la diferencia exacta?** Brechas B1–B9 (§5), todas con archivo y
   línea.

---

## 8. Evidencia de que nada se modificó

| Verificación | Resultado |
|---|---|
| Hash de los 93 `.py` de `src/`+`tests/` vs `A6G_BASELINE.sha256` (capturado al cerrar A6f) | **`changed/missing: 0`** |
| `pytest -q` | **535 passed** |
| `flake8 src tests` | **0** |
| `black --check src tests --line-length 88` | **93 ficheros sin cambios** |
| `git log --oneline -1` | `b963c5f` (sin commits) |
| Archivos generados | **1**: `A6G_MEMORY_EXPERIENCE_REVIEW.md` |
| Harness de ejecución | En directorio temporal del sistema, fuera del repo |

Protegidos — `memory_converse` (`memory_resolvers.py` + `tools.py`),
`MemoryIntentClassifier`, `MemoryBridge`, Dashboard, Android, Vivotek:
**intactos** (hash 0).
