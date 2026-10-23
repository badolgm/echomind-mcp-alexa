# UX CLEANUP REPORT — EchoMind

**Sprint:** UX Cleanup Final (BUG 1 + BUG 2)
**Fecha:** 11 OCT 2026
**Alcance:** corregir dos inconsistencias UX ya diagnosticadas. **Sin nuevas
funcionalidades. Sin cambios de arquitectura. Sin commits. Sin push.**

---

## Resumen

| Bug | Síntoma | Causa raíz | Estado |
|-----|---------|-----------|--------|
| 1 | `model_analysis` decía "Movimiento o cambio detectado en la cámara." con `LOW` / `0%` / `[]` | fallback incorrecto en `_announcement()` | ✅ Corregido |
| 2 | 1 episodio de movimiento → N registros `MOTION` en memoria | persistencia por tick sin coalescing | ✅ Corregido |

Resultado: **208 tests passed** (203 previos + 5 nuevos), `flake8` limpio,
`black --check` limpio.

---

## BUG 1 — Mensaje de "movimiento" en estado calmado

### Causa
`_announcement()` devolvía un texto fijo de movimiento cuando no había
detecciones, y `model_analysis = announcement + "\n" + recommendation` lo
propagaba al panel en cada tick, incluso con `risk=LOW` y `motion=0%`.

### Cambio
`src/infrastructure/services/ambient_watch_service.py`

- Nueva constante `_NEUTRAL_ANNOUNCEMENT` (línea 48):
  ```
  Sin detecciones activas. Todo normal.
  No active detections. All normal.
  ```
- `_announcement()` (línea 195): cuando **no** hay frases/detecciones, ahora
  devuelve ese mensaje neutro en vez de "Movimiento o cambio detectado…".
- `model_analysis` (línea 254): sin detecciones se usa el anuncio neutro;
  con detecciones se mantiene `announcement + "\n" + recommendation` (sin
  cambios para HIGH/CRITICAL/MEDIUM).

### Antes / Después

**Antes** (`risk=LOW`, `motion=0.0`, `detections=[]`):
```
Movimiento o cambio detectado en la cámara. Sigue monitoreando: todo se ve normal.
Sigue monitoreando: todo se ve normal.
```

**Después:**
```
Sin detecciones activas. Todo normal.
No active detections. All normal.
```

---

## BUG 2 — Memory flooding (episodios vs ticks)

### Causa
El watchdog publica un `camera_alert` **en cada tick (~0.5 s)** mientras el
episodio sigue activo, y `MemoryBridge` guardaba **un `MemoryRecord` por
evento**. Una caminata de 5 min ≈ 600 registros `MOTION`.

### Cambio
`src/infrastructure/services/memory_bridge.py`

- `_episode_key()` (línea 34): identidad del episodio = `location` + conjunto
  ordenado de labels.
- `_merge_detections()` (línea 40): unión de detecciones por label.
- `MemoryBridge.__init__` acepta `episode_gap` (default `30.0 s`) y mantiene un
  mapa de episodios (`_episodes`, línea 95).
- `MemoryBridge.ingest()` (línea 109): si llega un evento con la **misma firma**
  dentro de `episode_gap`, **actualiza el registro existente** (mismo `id`,
  timestamp al más reciente, detecciones unidas) en lugar de crear uno nuevo.

**Una caminata = un recuerdo.** Un episodio separado por más de `episode_gap`
(inactividad) genera un recuerdo nuevo, preservando la memoria histórica real.

### Antes / Después

| | Antes | Después |
|---|---|---|
| 60 ticks (30 s) de movimiento real | `MOTION = 59`, `size = 59` | `MOTION = 1`, `size = 1` |
| Episodio a los +100 s | nuevo registro | nuevo registro (correcto) |
| Conjuntos de labels distintos | 2 registros | 2 registros (correcto) |

---

## Evidencia

### Harness de reproducción (`repro_ux.py`, solo lectura)

**Antes:**
```
SYNTOMA 1 (calma):  announcement = "Movimiento o cambio detectado en la cámara…"
SYNTOMA 2 (60 ticks): memory records stored: 59   MOTION occurrences: 59
```

**Después:**
```
SYNTOMA 1 (calma):  announcement = "Sin detecciones activas. Todo normal.\nNo active detections. All normal."
SYNTOMA 2 (60 ticks): MOTION occurrences: 1   label_counts: {'MOTION': 1}
```

### Estado en vivo (servidor `CAMERA=simulation`, en reposo)

```
risk=LOW
motion_score=0.0
detections=
model_analysis=Sin detecciones activas. Todo normal.
No active detections. All normal.
```

---

## Validación

- `pytest -q` → **208 passed** (203 previos + 5 nuevos).
- `flake8 src tests` → limpio.
- `black --check src tests --line-length 88` → limpio.

**Tests nuevos**
- `tests/unit/test_ambient_watch_service.py`
  - `test_predict_low_without_detections_reports_calm`
  - `test_low_state_model_analysis_is_neutral`
- `tests/unit/test_memory_bridge.py`
  - `test_consecutive_motion_ticks_coalesce_into_one_episode`
  - `test_motion_after_gap_starts_a_new_episode`
  - `test_distinct_detection_sets_are_distinct_episodes`

---

## Coherencia final

- `LOW` + `0%` + `[]` → el panel ya **no** anuncia movimiento ("Sin detecciones
  activas. Todo normal." / "No active detections. All normal.").
- La **memoria histórica se conserva** (los recuerdos reales siguen ahí), pero
  agregada por **episodios**, no por ticks.

## Notas de alcance

- Cambios acotados a dos servicios (`ambient_watch_service`, `memory_bridge`)
  y sus tests. Sin tocar puertos, contratos ni composición.
- **No** se crearon commits; **no** se hizo push. Árbol de trabajo con las
  modificaciones locales.
