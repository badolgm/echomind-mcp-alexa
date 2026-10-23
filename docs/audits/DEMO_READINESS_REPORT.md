# DEMO_READINESS_REPORT.md — Sprint Demo Readiness

> Preparación de EchoMind para grabación y presentación (vídeo del **17 OCT 15:00**).
> **No** se programaron funcionalidades nuevas, **no** se tocó arquitectura, memoria, Motion Fix
> ni Voice Dock. **Sin commits. Sin push.**
>
> Verificación: servidor real (`uvicorn src.main:app`) + Chrome headless (Puppeteer).
> Scripts de evidencia: `validate2.js`, `validate3.js`, `demo_timing.js`, `scan.js`
> (`C:\Users\BagmDev\AppData\Local\Temp\opencode\pptr\`).

---

## FASE 1 — Android físico real con IP Webcam

**Resultado: ⛔ NO VALIDADO (dispositivo ausente).**

- Escaneo de LAN (`scan.js`): interfaces `192.168.80.0/24` (Wi-Fi) y `192.168.7.0/30` (Ethernet).
- Puertos `8080`/`8081` en toda la subred → **único host abierto: `192.168.7.2` (BBB)**, que
  responde `404` en `/shot.jpg`. **No hay teléfono con IP Webcam en la red.**

**Lo que sí quedó validado (con IP Webcam emulado, `validate3.js`):**

| Comprobación | Resultado |
| --- | --- |
| `PHONE_CAM_URL` leída y usada | ✅ snapshot `200 image/jpeg`, header `X-Source: live` |
| Watchdog registra frame live | ✅ `/api/cam/phone/detections` → `live:true`, `source:"live"` |
| Badge del dashboard | ✅ **`PHONE LIVE`** |
| Fallback si la fuente cae | ✅ `X-Source: fallback`, badge degrada a `PHONE SIM` sin crash |

**Para cerrar FASE 1 con hardware real** (cuando el teléfono esté en la LAN):

```powershell
$env:CAMERA = "phone"
$env:PHONE_CAM_URL = "http://<IP-DEL-TELEFONO>:8080/shot.jpg"
.\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
```

Seleccionar **PHONE** en el selector del dashboard → debe mostrar **`PHONE LIVE`**. Mientras no
haya teléfono, la demo **no se bloquea**: `CAMERA=simulation` es válido.

---

## FASE 2 — Ejecución del Demo Script completo

Ejecutado el flujo de `DEMO_SCRIPT_V1.md` (run `demo_timing.js`), con respuestas reales:

| Paso | Resultado observado |
| --- | --- |
| Seed Demo Memory | `Memory seeded (5 events)` |
| Q1 `What happened today?` | "During the last 24 hours I have observed: 1 time the open gate, 1 time motion, 1 time a fall, 1 time a person, 1 time an elderly person…" |
| Q2 `Critical events?` | "Recent critical events: – 3 hours ago at living: FALL DETECTED, PERSON (CRITICAL)" |
| Toggle `LANG EN → ES` | ✅ `LANG: ES` |
| Q3 `¿Cuándo viste la reja abierta?` | "La última detección de la reja abierta ocurrió hace 22 horas en cam-01." |
| Watchdog (escena estática) | LOW estable, sin `camera_alert` |
| Fuente PHONE | badge `PHONE SIM` (sin teléfono) |

`page_errors: []` · todas las llamadas `/api/converse` → `200`.

---

## FASE 3 — Duración real del flujo

Motor (sin narración), medido por paso:

| Segmento | Tiempo |
| --- | --- |
| Carga `/dashboard` | 2.47 s |
| Seed Demo Memory | 0.28 s |
| Q1 `What happened today?` | 0.18 s |
| Q2 `Critical events?` | 0.05 s |
| Toggle LANG | 0.25 s |
| Q3 `¿Cuándo viste la reja abierta?` | 0.07 s |
| Observación watchdog (espera fija) | 8.02 s |
| Fuente PHONE | 1.53 s |
| **TOTAL activo** | **≈ 12.8 s** |

**Lectura:** el motor responde en **decenas a cientos de ms**; el vídeo lo marca la **narración**,
no la latencia. El objetivo de guion (**2:30–2:50**) es holgado y no depende de esperas técnicas.

---

## FASE 4 — Lista de capturas definitivas

Directorio: `C:\Users\BagmDev\AppData\Local\Temp\opencode\shots_real\` y `...\shots_demo\`.

| # | Captura | Para qué |
| --- | --- | --- |
| 01 | `shots_real\01-dashboard.png` | Hook — dashboard completo |
| 02 | `shots_real\02-seeded.png` | `Memory seeded (5 events)` |
| 03 | `shots_real\03-en.png` | Respuesta EN (What happened today?) |
| 04 | `shots_real\04-en.png` | Respuesta EN (Critical events?) |
| 06 | `shots_real\06-es.png` | Respuesta ES |
| 07 | `shots_real\07-es.png` | Respuesta ES (reja abierta) |
| 08 | `shots_real\08-mic.png` | Micrófono / STT |
| **10** | **`shots_real\10-phone-live.png`** | **`PHONE LIVE` (si hay teléfono)** |
| 11 | `shots_real\11-phone-offline.png` | Fallback PHONE |
| D1 | `shots_demo\D1-seeded.png` | Seed (run de timing) |
| D2/D3 | `shots_demo\D2-en.png` / `D3-critical.png` | Q1 / Q2 |
| D4 | `shots_demo\D4-es.png` | Q3 ES |
| D5 | `shots_demo\D5-watchdog.png` | Watchdog |
| D6 | `shots_demo\D6-phone.png` | Selector PHONE |

**Set mínimo para el vídeo:** 01, 02, 03 (o D2), D3, 04 (06/07), 08, 09/10, D5.

---

## FASE 5 — GO / NO GO para el 17 OCT

### GO ✅
- Ejecución completa del Demo Script con respuestas correctas EN/ES.
- Seed, conversación, bilingüismo, STT (ruta de código) y TTS (`en-US`/`es-ES`) operativos.
- Watchdog estable: 30 s estáticos → `LOW`, **0 falsos HIGH/CRITICAL**.
- Camino PHONE (`PHONE_CAM_URL` / `PHONE LIVE`) validado con IP Webcam **emulado**; fallback sin crash.
- Duración holgada (motor ≈ 12.8 s) frente a objetivo 2:30–2:50.

### NO GO ⛔ (solo para este punto)
- **"Android físico real validado".** No hay teléfono con IP Webcam en la LAN. No es un fallo de
  software: es hardware/entorno. Requiere conectar el teléfono y repetir FASE 1.

**Veredicto:** **GO para grabar el 17 OCT.** Grabación con `CAMERA=simulation` (y la fuente PHONE
solo si el teléfono está conectado y muestra `PHONE LIVE`). Marcar como pendiente la validación de
un teléfono físico.

---

## Estado del árbol

Este sprint **no** modificó código ni hizo commits/push. La alineación documental previa ya está
consolidada en el commit **`407ca29` — `docs: align EchoMind vision, Alexa+ narrative and hackathon
strategy`** (HEAD de `checkpoint/day1-mobile-memory`). El único cambio de este sprint es este
reporte (`DEMO_READINESS_REPORT.md`, untracked). Gates de referencia: **203 tests PASS**, flake8 y
black limpios.
