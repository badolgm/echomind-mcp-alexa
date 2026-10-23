# CHECKPOINT DAY 2 — EchoMind

**Fecha:** 11 OCT 2026
**Rama:** `checkpoint/day1-mobile-memory`
**HEAD:** `407ca29`
**Objetivo del checkpoint:** consolidar y proteger el estado actual antes de la
grabación de vídeo.

> **Veredicto: GO PARA VIDEO.** 208 tests PASS · BUG 1 y BUG 2 corregidos ·
> Motion Fix, Voice Dock, DemoSeed, Bilingüismo y visión EchoMind/Alexa+
> alineada y validada.

---

## 1. Estado técnico

| Indicador | Estado |
| --- | --- |
| Tests | **208 passed** (203 previos + 5 nuevos) |
| `flake8 src tests` | **0 violaciones** |
| `black --check src tests --line-length 88` | **Limpio** |
| Motion Fix | ✅ Confirmado (`_image_payload` + `MOTION_THRESHOLD=0.20`) |
| BUG 1 (aviso "movimiento" en calma) | ✅ Corregido |
| BUG 2 (memory flooding) | ✅ Corregido (Episode Coalescing) |
| Voice Dock | ✅ Validado (navegador real) |
| DemoSeed | ✅ Validado (5 memorias) |
| Bilingüismo EN/ES | ✅ Validado (converse + TTS) |
| Visión EchoMind / Alexa+ protagonista | ✅ Alineada en los 8 docs |
| Referencias "Echosystem" | ✅ **0** (grep global sin resultados) |

### 1.1 Cambios de código de este checkpoint

**BUG 1 — `src/infrastructure/services/ambient_watch_service.py`**
- `_NEUTRAL_ANNOUNCEMENT` (ES/EN) y `_announcement()`: sin detecciones ya no
  anuncia "Movimiento o cambio detectado…"; en `LOW` muestra
  `"Sin detecciones activas. Todo normal.\nNo active detections. All normal."`.
- `model_analysis`: sin detecciones usa el aviso neutro; con detecciones se
  mantiene `announcement + "\n" + recommendation`.

**BUG 2 — `src/infrastructure/services/memory_bridge.py`**
- `_episode_key()` (location + set de labels) y `_merge_detections()`.
- `MemoryBridge(..., episode_gap=30.0)`: agrupa ticks consecutivos del mismo
  episodio en **un** `MemoryRecord`. 60 ticks → `MOTION=1` (antes 59).

**Tests nuevos (+5)**
- `tests/unit/test_ambient_watch_service.py`:
  `test_predict_low_without_detections_reports_calm`,
  `test_low_state_model_analysis_is_neutral`.
- `tests/unit/test_memory_bridge.py`:
  `test_consecutive_motion_ticks_coalesce_into_one_episode`,
  `test_motion_after_gap_starts_a_new_episode`,
  `test_distinct_detection_sets_are_distinct_episodes`.

---

## 2. Commits

**Historial de la rama (más reciente primero):**

```
407ca29  docs: align EchoMind vision, Alexa+ narrative and hackathon strategy       ← HEAD
093a8ad  feat: demo seed, bilingual memory converse, voice dock and motion fixes
eee7355  docs(checkpoint): record day1 recovery point (branch, commit, zip)
0789ce4  feat: add historical memory (V1-V3) and Android phone camera source
92029c3  feat(watchdog): add visual trigger filtering and 10s speech cooldown       ← main
```

- `main` permanece intacta en `92029c3`.
- **Push:** nunca realizado (`origin` no tiene nada subido).

**Cambios locales sin commitear (este checkpoint):**

```
 M AI_BOOT_MASTER.md
 M src/infrastructure/services/ambient_watch_service.py
 M src/infrastructure/services/memory_bridge.py
 M tests/unit/test_ambient_watch_service.py
 M tests/unit/test_memory_bridge.py
?? DEMO_READINESS_REPORT.md
?? UX_CLEANUP_REPORT.md
```

---

## 3. Riesgos pendientes

1. **P0 abierto — Validación Android física (IP Webcam real).** El camino PHONE
   se validó con IP Webcam **emulado** (snapshot 200, `PHONE LIVE`, fallback
   `PHONE SIM` sin crash). Falta hardware real en la LAN.
2. **Semántica "today" == "yesterday"** — ambas caen en la ventana de 24 h. No
   usar la pregunta "yesterday" en el guion.
3. **Sin LLM/embeddings reales** — narrativas deterministas + embeddings hash;
   Qdrant no implementado (a favor de la demo offline).
4. **Web Speech API** — micrófono requiere Chrome/Edge y micrófono físico
   (comprobación manual de 10 s).
5. **Residuales cosméticos** — `404 /favicon.ico` y `<polyline> NaN` (preexistente).
6. **Sin push / cambios sin commitear** — el trabajo vive solo en local; riesgo
   de pérdida hasta commitear.

---

## 4. Próximos pasos

1. **Día 12 (12 OCT):** validación Android **física** (cerrar P0). Comando:
   ```powershell
   $env:CAMERA="phone"; $env:PHONE_CAM_URL="http://<IP-TEL>:8080/shot.jpg"; `
   .\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
   ```
   → el selector PHONE debe mostrar `PHONE LIVE`.
2. **Día 13 (13 OCT):** validación de conversación end-to-end.
3. **Día 14 (14 OCT):** ensayos del guion (`DEMO_SCRIPT_V1.md`).
4. **Día 15 (15 OCT):** hardening.
5. **Día 16 (16 OCT):** congelación funcional.
6. **Día 17 (17 OCT 15:00):** grabación de vídeo.

---

## 5. Resultado del checkpoint

- Estado **consolidado y reproducible**: 208 tests PASS, gates limpias, ambos
  bugs UX cerrados y visión alineada.
- **GO PARA VIDEO** con un único NO-GO parcial: "Android físico validado"
  (hardware/entorno, no software).

_Documentos relacionados:_ `AI_BOOT_MASTER.md` · `UX_CLEANUP_REPORT.md` ·
`DEMO_READINESS_REPORT.md` · `PROJECT_VISION_ALIGNMENT.md`.
