# A4_IMPLEMENTATION_REPORT.md

**Sprint:** ECHOMIND V2 PHASE A — **A4 (Memory Spatial Foundation)**
**Fecha:** 2026-10-18
**Alcance:** `camera_id` y `zone` como metadatos espaciales opcionales en `MemoryRecord`.
**Explícitamente fuera de alcance:** Digital Twin, Facility Maps, bbox, xy, map_id, coordenadas, visualización en plano, migraciones, dependencias nuevas.

---

## 1. Archivos modificados y creados

### 1.1 Modificados (3 — lista cerrada)

| Archivo | Cambio |
|---|---|
| `src/infrastructure/services/memory_service.py` | `MemoryRecord` + `camera_id: str \| None = None` + `zone: str \| None = None` |
| `src/infrastructure/services/memory_bridge.py` | + `_optional_spatial()`; el mapeo `camera_alert → MemoryRecord` y la fusión de episodios **conservan** los dos campos |
| `src/domain/services/evidence.py` | `Evidence.from_record()` **lee** `camera_id`/`zone` (duck-typing); + `_optional_text()` |

### 1.2 Creado (1)

| Archivo | Líneas | Tests |
|---|---|---|
| `tests/unit/test_memory_spatial_metadata.py` | 287 | 19 |

> `Evidence` **ya tenía** `camera_id`/`zone` desde A1 (`evidence.py:34-35`), pero `from_record` nunca los poblaba → permanecían `None` para siempre. A4 los convierte en metadatos reales.

---

## 2. Nuevos campos

```python
@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    timestamp: float
    location: str
    source: str
    detections: tuple[dict[str, object], ...]
    risk: str
    model_analysis: str
    camera_id: str | None = None   # NUEVO — opcional
    zone: str | None = None        # NUEVO — opcional
```

| Propiedad | Valor |
|---|---|
| Obligatorios | **No** — ambos con default `None` |
| Degradación | Sin ellos, todo se resuelve en `location` (como hoy) |
| Blanco/vacío | `""` o `"  "` se normalizan a `None` |
| Inmutabilidad | `frozen` + `slots` **preservados** (verificado empíricamente y por test) |

---

## 3. Pruebas añadidas — 19

| Bloque | Tests |
|---|---|
| **Defaults** (3) | `test_spatial_fields_default_to_none` · `test_legacy_positional_construction_still_works` · `test_explicit_none_matches_legacy_construction` |
| **Compatibilidad** (3) | `test_record_stays_frozen_and_slot_sealed` · **`test_spatial_metadata_does_not_change_v1_queries`** · `test_records_differing_only_spatially_are_distinct` |
| **Serialización** (3) | `test_public_field_contract_is_locked` · `test_payload_round_trip_includes_spatial_metadata` · **`test_legacy_payload_without_spatial_fields_loads_unchanged`** |
| **Metadatos espaciales** (5) | `test_evidence_from_record_carries_spatial_metadata` · `test_evidence_from_record_degrades_for_legacy_records` · `test_evidence_from_record_treats_blank_metadata_as_absent` · `test_evidence_from_record_still_duck_types_bare_objects` · `test_evidence_defaults_remain_none` |
| **Bridge** (5) | `test_bridge_ingest_leaves_spatial_metadata_absent_by_default` · `test_bridge_maps_spatial_metadata_when_the_event_carries_it` · `test_bridge_ignores_blank_spatial_metadata` · **`test_bridge_coalescing_preserves_spatial_metadata`** · **`test_bridge_coalescing_is_identity_for_legacy_events`** |

### Las dos pruebas que más importan
- **`test_spatial_metadata_does_not_change_v1_queries`**: construye **dos stores idénticos**, uno con metadatos espaciales y otro sin ellos, y exige que `records_between`, `last_seen`, `count_events`, `label_counts`, `top_events` y `size` devuelvan **exactamente lo mismo**. Es la prueba ejecutable de que "EchoMind funciona igual que hoy".
- **`test_legacy_payload_without_spatial_fields_loads_unchanged`**: un payload de 7 campos (los de V1) se carga y los nuevos campos quedan en `None`. Cumple "MemoryRecord antiguo debe cargarse sin cambios".

---

## 4. Gates

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `.venv\Scripts\python.exe -m pytest -q` | **358 passed** |
| Lint | `.venv\Scripts\python.exe -m flake8 src tests` | **0 violaciones** |
| Formato | `.venv\Scripts\python.exe -m black --check src tests --line-length 88` | **80 files unchanged** |
| Dependencias nuevas | `requirements.txt` | **ninguna** |

---

## 5. Resultado pytest

```
358 passed in 10.72s
```

| | Tests | Total |
|---|---|---|
| Baseline V1+A1+A2+A3 (antes de A4) | 339 | 339 |
| Nuevos A4 | +19 | — |
| **Total** | | **358** |

**Los 246 (V1), 301 (A2) y 339 (A3) preexistentes siguen verdes y ninguno fue editado.**

---

## 6. Compatibilidad demostrada

### 6.1 Huella SHA-256 (antes/después)
Huella de los **81 archivos existentes** capturada antes de la primera edición y recomparada al cerrar:

```
changed/missing: 3
CHANGED: src\domain\services\evidence.py
CHANGED: src\infrastructure\services\memory_bridge.py
CHANGED: src\infrastructure\services\memory_service.py
```

Exactamente los 3 autorizados. **0 `MISSING`**. El artefacto `A4_BASELINE.sha256` se **eliminó tras la verificación**.

### 6.2 Verificaciones previas hechas antes de tocar nada
| Comprobación | Resultado |
|---|---|
| `frozen=True, slots=True` admite defaults | ✅ verificado con un `Probe` aislado antes de editar |
| Serialización por reflexión (`asdict`, `**record`, `vars(record)`, `fields(MemoryRecord)`) | ✅ **no existe en ningún sitio** del repo → añadir campos no puede romperla |
| Puntos de construcción de `MemoryRecord` | 17 (2 en `memory_bridge`, 1 en `demo_seed_service`, 14 en tests) — **todos por keyword** |
| Posicional sobre los 7 campos primitivos | ✅ sigue funcionando (test dedicado) |

### 6.3 Contrato del store futuro
El docstring de `MemoryVectorStorePort` fija `payload = MemoryRecord fields minus id`. `test_public_field_contract_is_locked` congela ahora la lista de 9 campos, y `test_payload_round_trip_includes_spatial_metadata` prueba el round-trip completo → el esquema del futuro adaptador Qdrant Edge queda definido.

### 6.4 Superficies protegidas
| Superficie | Estado |
|---|---|
| `memory_converse` | ✅ intacto (ni un byte) |
| `memory_recall` (canal paralelo) | ✅ intacto |
| `MemoryBridge` — comportamiento | ✅ idéntico (ver §7) |
| Dashboard / Android / Vivotek / Voice Dock / MCP / TTS / STT | ✅ fuera de la lista de 3, intactos |
| `pytest.ini`, `setup.cfg`, `requirements.txt` | ✅ intactos |

---

## 7. Los dos cambios en `memory_bridge.py` y por qué son identidad hoy

Fueron necesarios para que la cadena `evento → record → evidencia` no tuviera un punto donde el metadato se descartara en silencio.

| Cambio | Por qué | Por qué es identidad hoy |
|---|---|---|
| `camera_alert_to_memory_record` lee `event.get("camera_id")` / `event.get("zone")` | Sin esto, **nada** en producción podría poblar jamás los campos nuevos | Ningún evento publicado hoy lleva esas claves → `_optional_spatial(None) is None` |
| La fusión de episodios copia `camera_id`/`zone` | Sin esto, un episodio coalescido **borraría** el metadato | Hoy todos los records tienen `None` → copiar `None` es identidad |

Ambos están cubiertos por tests que fijan la identidad: `test_bridge_ingest_leaves_spatial_metadata_absent_by_default` y `test_bridge_coalescing_is_identity_for_legacy_events`.

---

## 8. Desviaciones y limitaciones (documentadas)

| # | Punto | Decisión |
|---|---|---|
| 1 | `memory_spatial.py` (asignado a A4 en el roadmap) | **No creado.** Nada lo consumiría todavía, y `PHASE_A_IMPLEMENTATION_PLAN.md §9.4` prohíbe explícitamente escribir código para fases futuras ("evita riesgo de regresión y de código muerto"). El *cimiento* es el metadato; el módulo llegará con la fase que primero lo lea. |
| 2 | El engine **no lee** aún `camera_id`/`zone` | `recall_engine` sigue agrupando por `location` y marcando `degraded: true`. Cambiarlo alteraría comportamiento de `memory_recall` → fuera del alcance. Cablearlo es la siguiente fase, con su propia prueba de regresión. |
| 3 | `_episode_key` sigue siendo `(location, labels)` | Meter `camera_id` en la clave **partiría** episodios que hoy se fusionan → cambio de comportamiento, prohibido. |
| 4 | El watcher no publica aún `camera_id`/`zone` | Poblar el origen real de los datos es la fase D del roadmap. El canal ya está preparado y probado de punta a punta. |

---

## 9. Criterios de aceptación de A4

| # | Criterio | Estado |
|---|---|---|
| 1 | `MemoryRecord` 100% compatible hacia atrás | ✅ 17 construcciones intactas, positional y keyword |
| 2 | `camera_id`/`zone` opcionales, nunca obligatorios | ✅ default `None` |
| 3 | Ningún test existente roto | ✅ **358 passed**, 0 ediciones en tests previos |
| 4 | `memory_converse` intacto | ✅ |
| 5 | `memory_recall` sigue siendo canal paralelo | ✅ |
| 6 | `MemoryBridge` sin cambios de comportamiento | ✅ probado por identidad |
| 7 | Android / Vivotek / Dashboard / Voice Dock / MCP / TTS / STT sin tocar | ✅ fuera de la lista |
| 8 | Tests de compatibilidad, serialización, defaults y metadatos espaciales | ✅ 19 |
| 9 | Sin migraciones, sin dependencias nuevas, sin commits | ✅ |

**A4 → DoD cumplido.**

---

## 10. Qué queda preparado para V2

La memoria ya puede responder, cuando una fase posterior lo conecte:

| Pregunta futura | Estado del cimiento |
|---|---|
| **¿Dónde ocurrió?** | `zone` presente en el record y propagado a `Evidence.zone` |
| **En qué zona?** | `zone` con degradación a `location` cuando no existe |
| **¿Qué dispositivo lo observó?** | `camera_id` presente en el record y propagado a `Evidence.camera_id` |
| **¿Qué cámaras observaron el mismo evento?** | hay identidad de dispositivo por record para agrupar |

Falta sólo la **lectura** (engine + watcher), no el modelo de datos.

**Siguiente paso sugerido:** A5 — cablear `recall_engine` a `camera_id`/`zone` (agrupación espacial real con degradación) + que el watchdog publique el `camera_id` de la cámara que disparó la alerta. Pendiente de tu aprobación.
