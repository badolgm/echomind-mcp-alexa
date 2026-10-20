# PRE_DEMO_FREEZE_REPORT.md — Pre-Demo Consolidation

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**Estado:** 208 tests PASSED

---

## 1. Inventario de cambios (working tree vs HEAD)

| Archivo | Tipo | Impacto |
|---|---|---|
| `requirements.txt` | +Pillow>=10.0.0 | Dependencia nueva |
| `src/main.py` | Separación PHONE/Vivotek + cleanup cámaras en lifespan | Infra cámara |
| `src/infrastructure/adapters/camera/http_phone_camera_adapter.py` | `DEFAULT_PHONE_CACHE_TTL=0.4` (antes 1.5) | Comportamiento phone |
| `src/infrastructure/services/ambient_watch_service.py` | PIL-based delta + `MOTION_PIXEL_DIFF_THRESHOLD` + `MOTION_CONFIRMATION_FRAMES` + motion streak | Motion detection robusto |
| `src/static/dashboard.html` | TTS mejorado (cache voces, preferencias EN/ES, bloqueo alert/dock, sync recognition.lang) | UX/voz bilingüe |
| `tests/unit/test_ambient_watch_service.py` | Ajustado para motion confirmation | Test alineado al nuevo algoritmo |

---

## 2. Clasificación: Obligatorio / Opcional / Revertible

### 2.1 OBLIGATORIOS (mantener para demo)

| Cambio | Razón | Riesgo |
|---|---|---|
| **main.py: separación PHONE/Vivotek** | Rutas independientes `/api/cam/phone/*` vs `/api/cam/vivotek/*`. Validado Android LIVE + Vivotek LIVE. | **Bajo** |
| **main.py: cierre cámaras en lifespan** | Cleanup correcto (`aclose()`) evita leaks. | **Bajo** |
| **http_phone_camera_adapter: TTL 0.4** | Más reactivo para demo (phone). Sin romper fallback. | **Bajo** |
| **ambient_watch_service: PIL delta + confirmation** | Reduce falsos por JPEG noise. Motion estable. Tests actualizados. | **Bajo** (con fallback byte-level) |
| **dashboard.html: sync `recognition.lang`** | Coherencia bilingüe EN/ES (corregido). | **Muy bajo** |
| **dashboard.html: preferencias voz EN/ES + fallback** | Mejora audibilidad, evita silencio. Mantiene fallback seguro. | **Muy bajo** |
| **test ajustado** | Alineado con comportamiento real (motion confirmation). | **Ninguno** |

### 2.2 OPCIONALES (útiles pero no estrictamente críticos)

| Cambio | Razón | Riesgo revertir |
|---|---|---|
| **dashboard.html: `isDockSpeaking` + bloqueo alert/dock** | Evita solapes TTS (alert corta dock). Buena UX. No bloquea demo si se quita. | **Muy bajo** (solo UX) |
| **dashboard.html: `currentUtterance` retenido** | Referencia extra (no crítico). | **Muy bajo** |

### 2.3 REVERTIBLES (sin pérdida funcional demo)

| Cambio | Notas | Recomendación |
|---|---|---|
| **requirements.txt: Pillow** | Usado por nuevo `frame_delta_ratio`. Si revertimos algoritmo PIL→byte-level, Pillow deja de usarse. **Pero** algoritmo actual mejor. | **Mantener** (mejora robustez motion). |

**Conclusión:** Casi todo es **útil/obligatorio** para estabilidad demo. Únicamente detalles UX menores son opcionales.

---

## 3. Análisis por archivo

### requirements.txt (+Pillow)
- **Justificado:** nuevo algoritmo motion usa PIL con fallback byte-level. OK.

### main.py (separación + cleanup)
- **Crítico:** valida separación PHONE/Vivotek. `aclose()` correcto.
- **Sin regresión:** 208 passed.

### http_phone_camera_adapter (TTL 0.4)
- **OK:** más ágil, mantiene fallback.
- **Sin impacto negativo:** probado con simulation.

### ambient_watch_service (PIL + confirmation)
- **Mejor robustez:** detecta movimiento real vs ruido JPEG.
- **Conservador:** `MOTION_CONFIRMATION_FRAMES=1`, threshold 20, fallback byte-level.
- **Test alineado:** `test_watch_tick_records_detections_and_publishes_alert` actualizado coherentemente.

### dashboard.html (bilingüe + voz + sync)
- **Mejor UX demo:** corrige inconsistencias observadas. Fallback seguro. Sin backend changes.
- **Validado conceptual:** audibilidad previa OK.

### tests/unit/test_ambient_watch_service.py
- **Correcto:** refleja nuevo comportamiento.

---

## 4. Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| **Pillow no disponible** | **Muy baja** | Fallback byte-level existe en código. |
| **Motion confirmation retrasa primer alerta** | **Muy baja** | `MOTION_CONFIRMATION_FRAMES=1` (mínimo). |
| **Dashboard TTS preferencias no encuentran voces** | **Muy baja** | Usa `voices[0]` + fallback `en-US/es-ES`. |
| **TTL phone muy bajo** | **Muy baja** | Cache TTL pequeño pero con fallback correcto. |

---

## 5. Estado actual

- **Working tree limpio tras cambios:** 6 archivos modificados (vs HEAD).
- **Tests:** 208 PASSED.
- **Lint/format:** flake8/black OK (verificados previamente).
- **Funcional:** Android/Vivotek/Phone routing OK, motion OK, bilingüe OK, Voice Dock OK.

---

## 6. Recomendación

**GO para congelación funcional**

**Razones:**
- Cambios **mejoran estabilidad/robustez** sin romper arquitectura.
- **0 regresiones** (208 passed).
- Todos relevantes para demo profesional.
- Fallbacks seguros en lugar crítico (motion + TTS + cámara).
- Separación PHONE/Vivotek correcta.

**Acción:** mantener todos los cambios actuales. **No revertir nada.** Sin commits/push (solo freeze).