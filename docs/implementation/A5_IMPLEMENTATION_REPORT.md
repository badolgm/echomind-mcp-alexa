# A5_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A5 (Spatial Reasoning Activation)**
**Fecha:** 2026-10-18
**Objetivo:** que `recall_engine` use **realmente** `camera_id` y `zone`, degradando limpiamente a `location` y `source` cuando no existen.

---

## 1. Archivos modificados y creados

### 1.1 Modificados (2)

| Archivo | Cambio |
|---|---|
| `src/infrastructure/services/recall_engine.py` | `SPATIAL` agrupa por **zona**; `CORRELATION` agrupa por **cámara**; cada uno degrada a su identidad V1 |
| `src/infrastructure/adapters/mcp/recall_resolvers.py` | `recall_result_payload()` expone `camera_id` y `zone` (claves aditivas) |

### 1.2 Creados (2)

| Archivo | Contenido |
|---|---|
| `src/domain/services/memory_spatial.py` | Helpers **puros y duck-typed**: `resolve_zone()`, `resolve_camera()` |
| `tests/unit/test_memory_spatial.py` | 18 tests |

> `memory_spatial.py` es el módulo que A4 difirió deliberadamente bajo la regla de código muerto (`PHASE_A_IMPLEMENTATION_PLAN.md §9.4`), con la promesa de que "el módulo llegará con la fase que primero lo lea". **A5 es esa fase.**

---

## 2. Reglas de degradación (requisitos 1 y 2)

```python
# memory_spatial.py
def resolve_zone(record)   -> tuple[str, bool]   # (zona, degradado)
def resolve_camera(record) -> tuple[str, bool]   # (cámara, degradado)
```

| Campo | Fallback | Devuelve `degraded` |
|---|---|---|
| `zone` | **`location`** | `True` cuando tuvo que usarse el fallback |
| `camera_id` | **`source`** | `True` cuando tuvo que usarse el fallback |

| Regla | Detalle |
|---|---|
| Blanco/vacío | `""` o `"   "` se tratan como **ausente** → se degrada |
| Duck-typing | Funcionan sobre `MemoryRecord`, `Evidence` y stand-ins sin campos (precedente de `evidence.py`) |
| Objeto sin ni siquiera `location`/`source` | Devuelve `("", True)` — nunca lanza |

El segundo elemento de la tupla es lo que permite al engine marcar `degraded` **con honestidad**: sólo si **algún** registro tuvo que degradar. Si todos los registros llevan el campo espacial, `degraded: False` y **sin** cadena `reason`.

---

## 3. Cambio en el engine

```python
elif relation is RelationKind.SPATIAL:
    entry.update(_group_by_zone(records))       # zone → location
elif relation is RelationKind.CORRELATION:
    entry.update(_group_by_camera(records))     # camera_id → source
```

Antes, `SPATIAL` y `CORRELATION` caían **ambos** en un único `else` → `_group_by_location`, con `degraded: True` fijo y el motivo `"camera_id/zone not available in this engine version"`. Ahora cada relación responde a su pregunta natural y el flag refleja el respaldo real.

---

## 4. Los 4 casos objetivo

| Pregunta | Relación | Identidad usada | Sin metadatos |
|---|---|---|---|
| ¿Dónde ocurrió la caída? | `SPATIAL` | `zone` | `location` |
| ¿Dónde vi mi mascota? | `SPATIAL` | `zone` | `location` |
| ¿Qué zona observó el evento? | `SPATIAL` | `zone` | `location` |
| ¿Qué dispositivo observó el evento? | `CORRELATION` | `camera_id` | `source` |

---

## 5. El único delta observable (y por qué es correcto)

Verificado contra el fixture de A2 (4 registros, todos con `source="camera_alert"`, localizaciones `patio/patio/kitchen/patio`):

```
SPATIAL     -> {'patio': [mem-1, mem-2, mem-4], 'kitchen': [mem-3]}   degraded: True
CORRELATION -> {'camera_alert': [mem-1, mem-2, mem-3, mem-4]}         degraded: True
```

| Relación | Antes de A5 | Después de A5 con datos legados |
|---|---|---|
| `SPATIAL` | agrupa por `location` | agrupa por `location` → **idéntico** |
| `CORRELATION` | agrupa por `location` | agrupa por `source` → **distinto** |

`SPATIAL` es **byte-idéntico** al comportamiento previo: sin `zone`, `resolve_zone` devuelve exactamente `record.location`, la misma clave de siempre.

`CORRELATION` cambia de `location` a `source` porque el **requisito 2 lo exige literalmente**: `camera_id ↓ source si no existe`. Con los datos de hoy (una sola fuente) agrupa en un solo grupo en lugar de dos. Es **más grueso pero más honesto**: `source` identifica al productor del evento, y `location` no es una identidad de dispositivo. En cuanto el watchdog publique el `camera_id` real (fase D del roadmap), la correlación pasa a ser útil de verdad.

Ningún test V1 ni A1/A2/A3 dependía de esto: `test_execute_correlation_relation_groups_by_location` sólo fija el nombre de la relación y `degraded is True`, no las claves del grupo.

---

## 6. Requisito 3 y 4 — V1 intacto, canal paralelo intacto

| Superficie | Estado |
|---|---|
| `memory_converse` | **ni un byte** |
| `MemoryBridge` | intacto (fuera de la lista de tocar) |
| Dashboard / Android / Vivotek / Voice Dock | intactos |
| `memory_recall` sigue siendo **canal paralelo** | sí — no se añadió switch, flag ni migración |
| `EPISODE` / `TIMELINE` / `BEFORE_AFTER` | intactos (la activación sólo toca las dos relaciones espaciales) — probado por `test_spatial_activation_leaves_episode_relations_untouched` |

---

## 7. Nuevos tests — 18

| Bloque | Tests |
|---|---|
| **Helpers (8)** | `test_resolve_zone_prefers_the_recorded_zone` · `test_resolve_zone_degrades_to_location_when_absent` · `test_resolve_zone_treats_blank_zone_as_absent` · `test_resolve_camera_prefers_the_recorded_camera` · `test_resolve_camera_degrades_to_source_when_absent` · `test_resolve_camera_treats_blank_camera_as_absent` · `test_helpers_duck_type_objects_without_spatial_fields` · `test_helpers_tolerate_objects_missing_the_v1_fields_too` |
| **Spatial (3)** | `test_spatial_groups_by_zone_when_records_carry_it` · `test_spatial_degrades_to_location_for_legacy_records` · `test_spatial_folds_missing_zone_into_its_location` |
| **Correlación (3)** | `test_correlation_groups_by_camera_when_records_carry_it` · `test_correlation_degrades_to_source_for_legacy_records` · `test_correlation_splits_one_camera_from_several_by_id` |
| **Identidad V1 (2)** | **`test_legacy_store_keeps_the_pre_a5_spatial_groups`** · `test_spatial_activation_leaves_episode_relations_untouched` |
| **Payload (2)** | `test_payload_exposes_camera_and_zone` · `test_payload_keeps_the_legacy_evidence_keys` |

**Las dos que más importan:**
- `test_legacy_store_keeps_the_pre_a5_spatial_groups` — reconstruye el esperado **leyendo `location` directamente del store** (no a mano) y exige que el grupo del engine sea ese mismo: la prueba ejecutable de que "sin metadatos espaciales, el agrupado es el de siempre".
- `test_correlation_splits_one_camera_from_several_by_id` — tres registros en **la misma** `location` pero dos cámaras distintas: el grupo se separa por dispositivo. Es la capacidad que antes era imposible.

---

## 8. Gates

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `.venv\Scripts\python.exe -m pytest -q` | **376 passed** |
| Lint | `.venv\Scripts\python.exe -m flake8 src tests` | **0 violaciones** |
| Formato | `.venv\Scripts\python.exe -m black --check src tests --line-length 88` | **82 files unchanged** |
| Dependencias nuevas | `requirements.txt` | **ninguna** |

### Resultado pytest
```
376 passed in 10.45s
```

| | Tests |
|---|---|
| Baseline V1+A1+A2+A3+A4 (antes de A5) | 358 |
| Nuevos A5 | +18 |
| **Total** | **376** |

**Los 246 (V1), 301 (A2), 339 (A3) y 358 (A4) preexistentes siguen verdes. Ninguno fue editado.**

---

## 9. Evidencia de impacto cero

Huella SHA-256 de los **80 ficheros `.py`** de `src/` + `tests/` capturada antes de la primera edición (`A5_BASELINE.sha256`) y recomparada al cerrar:

```
changed/missing: 2
CHANGED: .\src\infrastructure\adapters\mcp\recall_resolvers.py
CHANGED: .\src\infrastructure\services\recall_engine.py
```

Exactamente la lista autorizada. **0 `MISSING`.**

Ficheros nuevos (no estaban en la huella): `src/domain/services/memory_spatial.py`, `tests/unit/test_memory_spatial.py`.

El artefacto `A5_BASELINE.sha256` se **eliminó tras la verificación**.

---

## 10. Notas y seguimiento

| # | Punto | Estado |
|---|---|---|
| 1 | Nombre obsoleto en A2 | `tests/unit/test_recall_engine.py:242` se llama `test_execute_correlation_relation_groups_by_location` y ahora agrupa por `source`. **Sigue pasando** (no fija claves de grupo), pero el nombre miente. Propuesto renombrarlo a `test_execute_correlation_relation_groups_by_source_for_legacy_records` en A6 — **no hecho aquí** para mantener el impacto cero en 2 ficheros. |
| 2 | El payload expone `camera_id`/`zone` | 2 claves aditivas en `/api/recall`. Los clientes existentes que sólo leen claves conocidas no se afectan (`test_payload_keeps_the_legacy_evidence_keys` congela la lista). |
| 3 | Origen de los datos | El watcher aún no publica `camera_id`/`zone`, así que en producción todo degrada hoy. El motor ya está cableado y probado de punta a punta. |
| 4 | Narración | `render_utterance()` sigue diciendo `location` — la redacción plena con metadatos espaciales es **Fase B**, fuera de A5. |

---

## 11. Criterios de aceptación

| # | Requisito | Estado |
|---|---|---|
| 1 | Degradación obligatoria `zone → location` | ✅ `resolve_zone` + `test_resolve_zone_degrades_to_location_when_absent` |
| 2 | Degradación obligatoria `camera_id → source` | ✅ `resolve_camera` + `test_resolve_camera_degrades_to_source_when_absent` |
| 3 | No romper ningún comportamiento V1 | ✅ 376 passed; huella: 2 ficheros autorizados |
| 4 | Mantener `memory_recall` como canal paralelo | ✅ sin switch, sin flag, sin migración |
| 5 | Añadir los tests necesarios | ✅ 18 |
| — | Sin commits, sin push | ✅ HEAD intacto en `b963c5f` |

**A5 → DoD cumplido.**
