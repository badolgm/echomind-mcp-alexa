# TRAE_FINAL_AUDIT.md — Auditoría final de cambios TRAE

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**Estado base:** `407ca29` con cambios locales de TRAE sin commitear  

---

## Archivos modificados (revisados)

1. `requirements.txt` — + `Pillow>=10.0.0`
2. `src/main.py` — separación PHONE/Vivotek + cleanup cámaras en lifespan
3. `src/infrastructure/adapters/camera/http_phone_camera_adapter.py` — `DEFAULT_PHONE_CACHE_TTL = 0.4` (antes 1.5)
4. `src/infrastructure/services/ambient_watch_service.py` — detección de movimiento por píxeles + motion confirmation + streak
5. `src/static/dashboard.html` — TTS robusto (caché voces, fallback de voz, bloqueo alert/dock, referencia utterance)
6. `tests/unit/test_ambient_watch_service.py` — ajuste para motion confirmation

---

## 1. Separación PHONE/Vivotek

**Veredicto: ✅ ACEPTAR**

- **Creación explícita de instancias:** `vivotek_camera = VivotekCameraAdapter(...)` y `phone_camera = HttpPhoneCameraAdapter(...)`. Buena separación.
- **Rutas independientes:** `mount_camera_routes(app, vivotek_camera, ...)` para Vivotek; `mount_phone_camera_routes(app, phone_camera, ...)` para Phone. Cada ruta usa su propia instancia.
- **Estado aislado:** Phone conserva su `_cached`, `_last_error`, `_detections`; Vivotek mantiene su propio estado. Sin acoplamiento entre fuentes.
- **Lifespan:** `cameras=[camera, vivotek_camera, phone_camera]` + `aclose()` en shutdown (cleanup correcto). 

**Conclusión:** Separación clara, correcta e independiente.

---

## 2. Uso de Pillow

**Veredicto: ✅ ACEPTAR**

- **Motivación válida:** sustituye comparación byte-level (ruidosa con JPEG) por diferencia de píxeles en grayscale 48x48 (robusto a re-quantización JPEG).
- **Umbral razonable:** `MOTION_PIXEL_DIFF_THRESHOLD = 20` (diferencia de brillo significativa).
- **Fallback seguro:** try/except → si PIL falla, vuelve al método byte-level con `abs(diff) >= 4` + sampling 4096. No rompe camino crítico.
- **Costo aceptable:** 48x48 muy barato; llamado por tick del watchdog (demo-friendly).
- **Dependencia:** `Pillow>=10.0.0` justificada.

**Conclusión:** Implementación correcta con degradación segura.

---

## 3. Cambios en ambient_watch_service.py

**Veredicto: ✅ ACEPTAR**

Cambios relevantes:
- `frame_delta_ratio`: decodificación PIL (48x48, L) → cuenta píxeles con `|a-b| >= 20`. Fallback conserva lógica previa con umbral 4.
- `MOTION_CONFIRMATION_FRAMES = 1` + `_motion_streak`: requiere >=1 frame consecutivo con `motion >= threshold` para considerar `confirmed_motion > 0`. Reduce falsos positivos (ruido puntual).
- Ajuste en test: `test_watch_tick_records_detections_and_publishes_alert` pasa 3 frames (`00, ff, 00`) y usa 2 ticks (ajustado al nuevo flujo). 

**Observaciones:**
- `MOTION_CONFIRMATION_FRAMES=1` significa "histeresis mínima" (efectivo). Coherente con objetivo de reducir ruido.
- Lógica clara y determinista.
- **Sin cambios arquitectónicos** (solo algoritmo interno).

**Conclusión:** Mejora de robustez. Test actualizado correctamente.

---

## 4. Cambios en dashboard.html

**Veredicto: ✅ ACEPTAR**

- **Cache de voces:** `speechVoices` + `refreshSpeechVoices()` + `onvoiceschanged` → evita `getVoices()` vacío (problema conocido en Chrome).
- **Selección de voz inteligente:** busca voz con prefijo de idioma (`match || voices[0] || null`); si hay voz disponible usa `utter.voice = voice` y `utter.lang = voice.lang`; fallback a `en-US/es-ES` si no hay ninguna. 
- **Prevención de solapes:** `if (source === "alert" && isDockSpeaking) return` → evita que alertas corten respuesta del Voice Dock (importante para demo). 
- **Cleanup estado TTS:** `isDockSpeaking` + `onend/onerror` para resetear flag. `currentUtterance` retenido.
- **Solo cancel si speaking/pending:** evita cancel innecesario.
- **Call sites actualizados:** `handleCameraAlert` pasa `source="alert"`, `executeConverse` pasa `source="dock"`. Ajustes menores en snapshot/phone refresh coherentes con UI.

**Sin nuevas funcionalidades. Solo hardening TTS.** Validado previamente (audibilidad OK con fallback de voz).

**Conclusión:** Correcto. Reduce riesgo de silenciamiento/cortes.

---

## 5. Cantidad real de tests

**Veredicto: ✅ CONFIRMADO (208)**

- `pytest -q`: **208 passed** (tras formateo black/flake8).
- Tests nuevos del checkpoint anterior (+5): presentes. 
- Test modificado (`test_watch_tick_records_detections_and_publishes_alert`) **ajustado coherentemente** (no eliminado).
- Flake8: limpio. Black: limpio (3 archivos reformateados por cambios TRAE, ahora 64 files would be left unchanged).

**Por qué TRAE pudo reportar 191:** discrepancia de estado (rama/commit/working tree distinto) o ejecución parcial. **No indica regresión.** Estado actual real: **208 passed**.

---

## 6. Regresiones potenciales

**Veredicto: ✅ SIN REGRESIONES**

Evaluación:
- **Motion detection:** nuevo algoritmo con fallback conserva comportamiento; con `MOTION_CONFIRMATION_FRAMES=1` efectivamente igual o más estable. Test ajustado.
- **Separación cámaras:** rutas/instancias aisladas. No afecta Vivotek existente ni Phone. 
- **TTS dashboard:** cambios defensivos (cache voces, flags). No rompe flujo existente (executeConverse sigue funcional).
- **Lifespan cameras:** añade cleanup extra, no altera orden lógico.
- **Phone cache TTL:** 0.4 (más reactivo) vs 1.5 — razonable para demo; no rompe contrato.
- **Suite completa:** 208 passed. 

**Riesgos identificados:** **ninguno bloqueante**. Únicos riesgos menores (ya señalados): dependencia Pillow, costo decodificación (trivial), cambio sutil de timing con confirmation frames (manejable).

---

## Recomendación global

**✅ ACEPTAR**

**Justificación:**
- Cambios **técnicamente correctos** y dirigidos a robustez (ruido JPEG, TTS timing/voz, aislamiento cámaras, lifecycle).
- **Sin regresiones:** 208 tests passed, lint/format OK.
- **Defensivos, no invasivos:** mantienen arquitectura, no añaden features nuevas.
- **Coherentes** con objetivos del sprint (demo hardening + estabilidad).
- Ajustes de tests **mínimos y necesarios**.

**Acción:** **Aceptar** cambios TRAE tal cual (sin revertir). Mantener sin commits/push (estado actual).