# A7D — Implementación: Response Intent Adapter

**Fase:** A7D (implementación, no análisis) · **Módulo:** enrutado de la respuesta al tipo de pregunta
**Regla dura respetada:** `memory_converse`/`MemoryBridge`/`VectorMemoryService`/Dashboard/Android/Vivotek intactos · los planes directos se siguen renderizando igual · sin commits · sin push · HEAD = `b963c5f`
**Objetivo del encargo cumplido:** las seis preguntas obligatorias ya **no comparten una sola respuesta**; cada una se enruta a la capacidad del motor que la responde, y el caso 5 (*relacionados*) deja de ser idéntico al caso 6 (*cámaras*).

---

## 1. Objetivo cumplido

A6g midió que el motor calcula mucho más de lo que dice: contaba etiquetas, agrupaba
por zona y cámara, calculaba silencios, resolvía anclas y construía un grafo de
relaciones — y, aun así, **las seis preguntas devolvían tres líneas de evidencia
idénticas**. A7B atacó parte del problema (ancla, dirección, políticas estructurales);
A7D cierra la brecha de **intención**: la respuesta se elige por el *tipo de respuesta*
que la pregunta pide, no por la primera política que encaje.

El mecanismo es un **adaptador de intención**: el planificador resuelve
`ResponseIntent`, el motor lo deja en la traza (`plan_to_dict`), y el sintetizador
despacha a **un renderizador por intención** desde una tabla. Dos preguntas distintas
obtienen dos respuestas distintas aunque disparen la misma relación de motor.

---

## 2. Archivos nuevos y modificados

### Nuevos (2)

| Archivo | Contenido |
|---|---|
| `src/domain/services/response_intent.py` | `ResponseIntent` (enum) + `resolve_intent(...)` (texto + señales estructurales) + `derive_intent(...)` (solo señales estructurales). Puro dominio, sin dependencias del plan. |
| `tests/unit/test_recall_response_intent.py` | 32 tests: tabla del adaptador, derivación estructural, los seis casos end-to-end, distinguibilidad, `plan_to_dict`, planes directos. |

### Modificados (4)

| Archivo | Cambio |
|---|---|
| `src/domain/services/recall_plan.py` | Campo `RecallPlan.response_intent: ResponseIntent \| None` (por defecto `None`) + clave `"response_intent"` en `plan_to_dict`. |
| `src/domain/services/recall_planner.py` | `understand()` calcula `response_intent` con `resolve_intent`; para `LAST_SEEN_PLACE` extrae la etiqueta con `_detect_label` (reutiliza la tabla `_LABEL_TERMS` del clasificador, **sin duplicarla**) y **sobrescribe la op primaria a `LAST_SEEN`** en `_build_ops`. Se reordena el ensamblado para que las relaciones/dirección/agregación precedan a entidades y ops. |
| `src/domain/services/recall_synthesis.py` | `render_synthesis` pasa de cadena de `if` a **tabla de despacho** `_INTENT_RENDERERS`; nuevos `_last_seen_place_line` (caso 1) y `_relations_line` (caso 5); `_timeline_line` enriquecida con el conteo de etiquetas del agregado (caso 4); guarda de evidencia conservada (`COUNT`/`BEFORE`/`AFTER` no la exigen). |
| `tests/unit/test_recall_synthesis.py` | 1 test de A7B actualizado (§7). |

---

## 3. El adaptador de intención (`response_intent`)

Precedencia fija (primera coincidencia gana). `resolve_intent` añade las reglas de
texto que la estructura sola no puede separar; `derive_intent` reproduce el orden
estructural **exacto** de las políticas A7B/A7C previas.

| # | Intención | Disparador |
|---|---|---|
| 1 | `COUNT` | `aggregation == count` (o agregado `count` en la traza) |
| 2 | `BEFORE` / `AFTER` | relación `before_after` **y** dirección explícita |
| 3 | `LAST_SEEN_PLACE` | texto con lugar (`dónde`/`where`) **y** verbo de ver |
| 4 | `TIMELINE` | relación `timeline` |
| 5 | `CAMERAS` | texto con cámara(s) |
| 6 | `RELATIONS` | texto con `relacionad…`/`related` |
| 7 | `CAMERAS` | relación `correlation` (sin texto de cámara) |
| 8 | `SPATIAL` | relación `spatial` |
| 9 | `SUMMARY` | `aggregation == summary` |
| — | `FALLBACK` | ninguna de las anteriores → narración V1 |

**Separación 5 ≠ 6 (encargo):** ambas preguntas activan la relación `correlation`,
pero el texto las separa — *«eventos relacionados»* → `RELATIONS`; *«cámaras»* →
`CAMERAS`. Regla explícita, no heurística de orden.

---

## 4. Renderizadores nuevos

- **`_last_seen_place_line` (caso 1):** toma la evidencia **más reciente** del label
  del plan y dice *dónde*, *por qué cámara* y *cuándo*, con un sustantivo hablado
  (`PET → «una mascota»`). No nombra etiquetas ajenas.
- **`_relations_line` (caso 5):** lee la entrada `relate:derived` y locuta su digest
  narrado: **la lista de eventos relacionados**.
- **`_timeline_line` (caso 4):** añade el conteo de etiquetas (`Sucesos: …`) del
  agregado `summary` entre el resumen de silencios y la evidencia.
- `_correlation_line` (caso 6), `_spatial_line`, `_summary_line` y `_count_line` se
  conservan intactos como renderizadores de sus intenciones.

---

## 5. Los seis casos obligatorios — antes/después (misma fixture)

Fixture: 8 registros con `camera_id` + `zone`, `NOW` fijo. El «antes» se reproducen
con `dataclasses.replace(plan, response_intent=None, …)` más el *override* de op del
caso 1 desactivado (y la agregación de timeline desactivada para el caso 4) — es decir,
el camino estructural exacto pre-A7D.

| # | Pregunta | Antes (pre-A7D) | Después (A7D) | Δ |
|---|---|---|---|---|
| 1 | ¿Dónde vi mi mascota? | `Lugares: patio (4), salon (2)… GATE_OPEN en patio… PET en jardin…` | `La última vez que vi una mascota fue en patio (cámara cam-1), hace 1 hora.` | **cambia** |
| 2 | ¿Qué ocurrió antes de la caída? | `Antes de FALL DETECTED: …` | `Antes de FALL DETECTED: …` | igual |
| 3 | ¿Qué ocurrió después de la caída? | `Después de FALL DETECTED: …` | `Después de FALL DETECTED: …` | igual |
| 4 | ¿Qué pasó mientras estaba fuera? | `8 episodios, 5 silencios; el mayor de 1 h. …` | `8 episodios, 5 silencios; el mayor de 1 h. Sucesos: PERSON 2, …` | **cambia** |
| 5 | ¿Qué eventos están relacionados? | `Cámaras: cam-1 (3), … Las cámaras … vieron el mismo suceso…` | `Eventos relacionados: … Cambio de GATE_OPEN a PERSON…` | **cambia** |
| 6 | ¿Qué cámaras observaron el mismo evento? | `Cámaras: cam-1 (3), …` | `Cámaras: cam-1 (3), …` | igual (pero ahora ≠ 5) |

**Verificaciones:** las seis respuestas son **distintas entre sí** (`len(set) == 6`) y
`caso5 != caso6` (test `test_the_six_cases_no_longer_share_one_answer`).

---

## 6. Compatibilidad con planes construidos directamente

El sintetizador usa `plan.response_intent` **si está fijado**; si no, llama a
`derive_intent(...)` sobre las relaciones/agregación — que reproduce el orden de las
políticas A7B. Por eso un `RecallPlan` construido a mano (tests de bajo nivel,
llamadores programáticos) se renderiza **exactamente como antes de A7D**
(`test_a_directly_built_plan_has_no_intent_and_still_renders`).

La guarda de evidencia original se conserva: `COUNT`/`BEFORE`/`AFTER` responden sin
evidencia; el resto abstiene por la narración V1 cuando no hay evidencia.

---

## 7. Test de A7B actualizado (justificación)

`tests/unit/test_recall_synthesis.py:402`
`test_a_where_question_leads_with_the_place_roster` → `test_a_where_did_i_see_question_answers_with_the_last_seen_place`.

Se actualiza **una sola** aserción, cumpliendo las tres condiciones del encargo:

1. **El nuevo comportamiento es verificablemente mejor:** A6g §3 caso 1 fija el
   esperado (*«La última vez que vi la mascota fue en el patio…»*) y prueba que el
   roster `Lugares:` era un artefacto de coincidencia que desaparece con 500 registros.
2. **Usa información ya presente en el motor:** evidencia (`last_seen`/`range`),
   `location`, `camera_id` y `ts` ya existían y ya se calculaban.
3. **Hay evidencia en A6g de que la respuesta antigua no explotaba el motor:** A6g §3
   caso 1 (plan sin entidad) y §5 B3/B6.

No se modificó ningún test para ocultar un fallo: los planes directos con `SPATIAL`
siguen rindiendo `Lugares:` (`test_the_place_roster_keeps_the_evidence_behind_it`).

---

## 8. Pruebas y puertas

| Verificación | Resultado |
|---|---|
| `pytest -q` | **700 passed** (668 previos + 32 nuevos A7D) |
| `flake8 src tests` | **0** |
| `black --check src tests --line-length 88` | **105 ficheros sin cambios** (eran 103; +2 nuevos) |
| `git log --oneline -1` | `b963c5f` (sin commits) |

Hashes SHA-256 (12) de los 6 ficheros de A7D:

```
1F49A3D86B8E  src/domain/services/response_intent.py
19B77B5F901F  src/domain/services/recall_plan.py
933A32C7A5BD  src/domain/services/recall_planner.py
7990D7F24634  src/domain/services/recall_synthesis.py
7228D847AA7B  tests/unit/test_recall_synthesis.py
35EB4568A753  tests/unit/test_recall_response_intent.py
```

---

## 9. Protegidos — intactos

`memory_converse` (`memory_resolvers.py` + `tools.py`), `MemoryBridge`,
`VectorMemoryService` (`memory_service.py`), Dashboard (`src/static/dashboard.html`),
Android y Vivotek: **A7D no los toca**. No se añadió ninguna arquitectura, motor,
adapter, dashboard ni sensor nuevo — solo el adaptador de intención y sus
renderizadores, sobre lo ya construido.

---

## 10. Resumen

- **Qué se hizo:** un adaptador explícito de intención de respuesta que enruta cada
  pregunta al renderizador correcto; caso 1 = última vez (lugar+cámara+tiempo),
  caso 4 = timeline + agregación, caso 5 = lista de relacionados, caso 6 = cámaras.
- **Qué no se hizo:** nada que A6g desaconsejara — sin arquitectura nueva, sin tocar
  las seis superficies protegidas, sin reescribir V1.
- **Coste:** 2 ficheros nuevos, 4 modificados, 1 aserción de A7B actualizada con
  justificación; 32 tests nuevos; suite verde (700), lint limpio, formato limpio.
