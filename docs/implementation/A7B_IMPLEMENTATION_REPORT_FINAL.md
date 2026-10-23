# A7B — Implementación Final: Síntesis dirigida por la pregunta

**Fase:** A7B (implementación, no análisis) · **Canal:** `memory_recall` / `/api/recall` (V2)
**Regla dura respetada:** `memory_converse` intacto · 535 tests previos siguen PASS · sin commits · sin push · HEAD = `b963c5f`

---

## 1. Objetivo cumplido

La respuesta de recall ya **no es únicamente evidencia cruda**. El motor compone ahora
una respuesta con la **forma de la pregunta**: dirección antes/después, panorama de
timeline, conteos de aggregate, cámaras, lugares y contexto narrado — con
`render_utterance()` como **fallback obligatorio** cuando no existe respuesta
estructural útil.

---

## 2. Archivos modificados y nuevos

### Modificados (3)

| Archivo | Cambio |
|---|---|
| `src/domain/services/recall_plan.py` | Campo nuevo `RecallPlan.direction: str \| None` (`"before"` / `"after"` / `None`) + `"direction"` en `plan_to_dict` (traza auditable). |
| `src/domain/services/recall_planner.py` | Tabla `_DIRECTION_PATTERNS` (regex con límites de palabra: `después/despues/after` → `after`, `antes/before` → `before`) + `_detect_direction()`. `understand()` fija `direction` **solo** cuando existe la relación `BEFORE_AFTER`; ambos marcadores a la vez = ambiguo = `None`. |
| `src/infrastructure/services/recall_engine.py` | `execute()` llama a `render_synthesis(...)` en lugar de `render_utterance(...)`. Docstring del pipeline actualizado. |

### Nuevos (2)

| Archivo | Contenido |
|---|---|
| `src/domain/services/recall_synthesis.py` | Módulo de dominio puro (stdlib + dominio): `render_synthesis()` con la política de prioridad, `_count_line`, `_directional_line`, `_timeline_line`, `_correlation_line`, `_spatial_line`, `_summary_line`, `_groups_line`, `_duration`, `_overlap_pair`. |
| `tests/unit/test_recall_synthesis.py` | 35 tests nuevos (ver §4). |

---

## 3. Política de síntesis (primera coincidencia gana)

```
1. AGGREGATE COUNT   → frase de conteo, incluso sin evidencia   ("12 eventos.")
2. BEFORE_AFTER      → episodios del lado pedido junto al anchor, con cabecera
                       explícita ("Antes de FALL DETECTED: …" / "Después de …")
3. TIMELINE          → resumen de episodios+silencios (duración del mayor gap)
                       + evidencia + contexto narrado
4. CORRELATION       → roster de cámaras con conteos + las dos cámaras que
                       vieron el mismo suceso + contexto narrado
5. SPATIAL           → roster de lugares con conteos + evidencia
6. AGGREGATE SUMMARY → conteos por etiqueta ("Resumen: PET 2, SMOKE 1.") + evidencia
7. FALLBACK          → render_utterance(evidence)  ← obligatorio, byte-idéntico a V1
```

Garantías por construcción:

- **Dirección explícita (req. 1):** `plan.direction` se propaga plan → traza → síntesis.
  Sin `anchor` + `direction` la síntesis **no afirma ningún lado** (vuelve al fallback).
  Lado vacío → `"No hubo eventos después de FALL DETECTED."` (nunca inventa).
- **Fallback obligatorio (req. 6):** sin respuesta estructural → `render_utterance()`;
  con evidencia vacía → abstención V1 byte-idéntica.
- **Límites:** cabecera + máximo 3 líneas direccionales; evidencia ≤ 3 líneas (techo V1);
  contexto narrado ≤ 3 frases (techo `MAX_NARRATION_ITEMS`).
- **Sin invención:** todo sale de la traza ya ejecutada (`relate`, `aggregation`) o de
  la evidencia recuperada. Determinístico, bilingüe, sin LLM, sin IO.

---

## 4. Tests nuevos (35 → total suite **570**)

`tests/unit/test_recall_synthesis.py`:

- **Fallback:** V1 idéntico sin respuesta estructural; abstención en evidencia vacía
  (almacén vacío vía motor).
- **Aggregate/counts:** es/en, singular, entidad (`2 detecciones de PET.`), riesgo
  (`4 CRITICAL risk events.`), cero honesto, e integración end-to-end
  (`¿cuántos eventos hubo hoy?` → `"6 eventos."`).
- **Dirección:** `understand` marca `before`/`after` (es y en); ambigüedad → `None`;
  sin relación `BEFORE_AFTER` → `None`; `plan_to_dict` y traza exponen la dirección;
  respuestas antes/después con cabecera, lado correcto y **distintas entre sí**;
  techo de 3 episodios; lado vacío (es/en); dirección sin anchor → fallback.
- **Timeline:** cabecera con `episodios, … silencios;`, evidencia conservada,
  contexto narrado dentro de la respuesta, gaps vacíos → fallback.
- **Cámaras:** roster ordenado por tamaño (`Cámaras: cam-1 (3), cam-2 (1).`),
  par de cámaras del suceso compartido, grupos vacíos → fallback.
- **Lugares y resumen:** cabecera `Lugares:` + evidencia detrás; `Resumen:` con
  conteos, sin conteos → fallback.
- **Motor/payload:** determinismo tras síntesis; `payload["response"] == utterance`.

---

## 5. Gates

| Gate | Resultado |
|---|---|
| `python -m pytest -q` | **570 passed** (535 previos + 35 nuevos), 0 failed |
| `python -m flake8 src tests` | **0 errores** |
| `python -m black --check src tests --line-length 88` | **95 files unchanged** (93 + 2 nuevos), 0 por reformatear |
| `git log --oneline -1` | `b963c5f` — **sin commits, sin push** |

### Prueba de impacto cero (hash SHA1, baseline `A7B_BASELINE.sha256`, 93 py)

```
CHANGED (3): src\domain\services\recall_plan.py
             src\domain\services\recall_planner.py
             src\infrastructure\services\recall_engine.py
NEW     (2): src\domain\services\recall_synthesis.py
             tests\unit\test_recall_synthesis.py
MISSING (0)
```

`memory_converse` **intacto**: `memory_resolvers.py` (dispatch), `tools.py` (schema),
`memory_intent.py`, `memory_bridge.py`, `main.py`, dashboard, Android y Vivotek
**no aparecen en CHANGED** — ninguna línea tocada en esta fase. El contrato V1 queda
probado además por los tests existentes que exigen verbatim byte a byte
(`La última detección de una mascota ocurrió hace …`).

---

## 6. Ejemplos reales (fixture HOUSEHOLD, NOW=1760000000, 12 registros)

### ANTES de A7B (estado medido al abrir la fase)

Las 6 preguntas producían **exactamente la misma respuesta**, evidencia cruda:

```
GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas.
```

(incluido `¿Cuántos eventos…?`: mismo texto, sin número).

### DESPUÉS de A7B

```
CASO 1: ¿Dónde vi mi mascota?
  plan: relations=['spatial'] direction=None anchor=None
  → Lugares: patio (6), salon (3), cocina (2), jardin (1). GATE_OPEN en patio, hace 6 horas.
    PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas.

CASO 2: ¿Qué ocurrió antes de la caída?
  plan: relations=['before_after'] direction='before' anchor='FALL DETECTED'
  → Antes de FALL DETECTED: GATE_OPEN en patio, hace 6 horas. PERSON en patio, hace 5
    horas. PET en jardin, hace 5 horas.

CASO 3: ¿Qué ocurrió después de la caída?
  plan: relations=['before_after'] direction='after' anchor='FALL DETECTED'
  → Después de FALL DETECTED: FALL DETECTED, PERSON en patio, hace 4 horas.
    PERSON_ELDERLY en salon, hace 3 horas. PERSON en cocina, hace 3 horas.

CASO 4: ¿Qué pasó mientras estaba fuera?
  plan: relations=['timeline']
  → 12 episodios, 7 silencios; el mayor de 1 h 45 min. GATE_OPEN en patio, hace 6 horas.
    PERSON en patio, hace 5 horas. PET en jardin, hace 5 horas. SMOKE en el mismo instante.

CASO 5: ¿Qué eventos están relacionados?
  plan: relations=['correlation']
  → Cámaras: cam-1 (6), cam-3 (3), cam-4 (2), cam-2 (1). Las cámaras cam-4 y cam-3
    vieron el mismo suceso: SMOKE en el mismo instante.

CASO 6: ¿Qué cámaras observaron el mismo evento?
  plan: relations=['correlation']  (mismo plan que caso 5)
  → Cámaras: cam-1 (6), cam-3 (3), cam-4 (2), cam-2 (1). Las cámaras cam-4 y cam-3
    vieron el mismo suceso: SMOKE en el mismo instante.

CASO 7: ¿Cuántos eventos de riesgo hubo hoy?
  plan: aggregation=COUNT
  → 12 eventos.
```

Inglés (misma fixture): `After FALL DETECTED: FALL DETECTED, PERSON at patio, 4 hours
ago. …` · `12 events.`

Respuesta **antes**: 1 idéntica para todos → **después**: 6 formas distintas
(casos 5 y 6 comparten plan y, por tanto, respuesta — ver §7).

MCP `_render` (herramienta `memory_recall`): la cabecera direccional sale en la línea
de `response` y la sección `evidencia:` + `trace:` sigue intacta debajo.

---

## 7. Observaciones y límites declarados

1. **Casos 5 y 6 idénticos a propósito:** `understand()` genera el **mismo plan**
   (`relations=['correlation']`, misma ventana) para «relacionados» y «cámaras».
   Diferenciarlos exigiría un campo extra de intención en el plan (fuera del
   alcance aprobado de 6 puntos). Ambas respuestas son coherentes: nombran cámaras,
   sus conteos y el suceso compartido.
2. **B5 (MCP `session_start`) no incluido:** no figuraba en la lista aprobada de 6
   items; el modo HTTP `/api/recall` ya lo soporta y el caso 4 funciona en ambos
   caminos.
3. **Observación menor (no regresión):** `¿Cuántos eventos de riesgo hubo hoy?`
   responde `12 eventos.` porque el clasificador V1 no convierte «de riesgo» en
   filtro `risk` — el contador es correcto para el plan emitido; afinar la
   extracción de riesgo pertenece a otra fase.
4. `context_response` sigue expuesto aparte en el payload (campo `context_response`);
   en las ramas TIMELINE/CORRELATION el contexto narrado **además** se integra en
   `response`.
5. Baselines consumidos: `A7B_BASELINE.sha256` (y el `A6G_BASELINE.sha256` obsoleto)
   se eliminan tras esta verificación, como en fases anteriores.

---

## 8. Comandos de verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q                      # 570 passed
.\.venv\Scripts\python.exe -m flake8 src tests               # 0
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88   # 95 unchanged
git log --oneline -1                                         # b963c5f, sin commits
```
