# CHECKPOINT DAY 1 — SUMMARY DE RESPALDO

> Punto de recuperación del estado funcional consolidado de EchoMind MCP Alexa.
> Fecha: 10-oct-2026 · HEAD de referencia: `92029c3`.
> Este documento permite reconstruir y verificar el trabajo de los sprints de memoria (V1–V3) y del Día 1 (Android Camera).

---

## 1. Estado funcional

| Capacidad | Estado |
|---|---|
| Visión (Vivotek) | ✅ operativa (con fallback determinista) |
| Visión (Android / IP Webcam) | ✅ implementada, **validación física pendiente** |
| Watchdog ambiental | ✅ movimiento real → `camera_alert` HIGH |
| Razonamiento | ✅ Bedrock Nova Micro + Quota Fallback Protocol (regla local) |
| SSE + Dashboard | ✅ Control Center con selector de fuente y SSE |
| MCP / Alexa+ | ✅ 8 tools, Streamable HTTP, session manager |
| Memoria V1 (store/search) | ✅ |
| Memoria V2 (bridge + tools) | ✅ |
| Memoria V3 (intent + converse) | ✅ |
| Android Camera Adapter | ✅ |
| E2E programático | ✅ `test_phone_camera_end_to_end.py` |
| **189 tests** | ✅ verdes |
| **flake8 / black** | ✅ limpios |

---

## 2. Arquitectura vigente

Hexagonal (puertos y adaptadores) — el dominio no conoce IO:

```
src/
  domain/            # modelos puros + servicios (MemoryIntentClassifier)
  application/       # use cases + DTOs
  infrastructure/
    adapters/
      aws/           # Bedrock + fallback LLM
      iot/           # VivotekCameraAdapter  (Opción A)
      camera/        # HttpPhoneCameraAdapter (Opción B)  <-- NUEVO
      mcp/           # servidor MCP, tool_resolvers, memory_resolvers, dashboard
    config/          # EventHub, Telemetry
    services/        # AmbientWatchService, MemoryBridge, VectorMemoryService, SensorBus
  static/            # dashboard.html
  main.py            # composition root
```

**Punto de integración único:** el protocolo `CameraFrameSource` (`get_frame()`, `record_detections()`). Cualquier fuente de frames (Vivotek o Android) es intercambiable sin tocar watchdog, MCP ni dashboard.

---

## 3. Diagrama actualizado

```
   ANDROID (IP Webcam)            VIVOTEK FD8367
   http://<ip>:8080/shot.jpg      192.168.40.10
            \                        /
             \  CAMERA=phone|vivotek /
              v                      v
        HttpPhoneCameraAdapter   VivotekCameraAdapter
               \                   /
                \ CameraFrameSource /
                 v                 v
              AmbientWatchService (tick 0.5s, delta de frames)
                        |
                        | camera_alert (HIGH/CRITICAL)
                        v
                    EventHub  ──────────────►  Dashboard SSE (/dashboard/events)
                        |                                 (PHONE LIVE / OFFLINE / SIM)
                        v
                  MemoryBridge (ingesta HIGH/CRITICAL)
                        v
                 VectorMemoryService   ◄─── memory_last_seen/search/summary
                        |
                        v
                 MemoryConverse (MemoryIntentClassifier, sin LLM)
                        |
                        v
               MCP Streamable HTTP  ──────►  ALEXA+ (skill.json)
```

---

## 4. Pruebas realizadas

| Tipo | Comando | Resultado |
|---|---|---|
| Suite completa | `python -m pytest -q` | **189 passed** |
| Lint | `python -m flake8 src tests` | **0 errores** |
| Formato | `python -m black --check src tests --line-length 88` | **limpio (60 archivos)** |
| E2E Android (mock) | `tests/integration/test_phone_camera_end_to_end.py` | ✅ phone → movimiento → alerta → memoria → conversación |
| Config | `test_http_phone_camera_adapter.py` | ✅ `CAMERA=phone`, `PHONE_CAM_URL`, fallback |

**Validación física (FASE 2/3):** pendiente de hardware Android; ver procedimiento abajo.

---

## 5. Procedimiento de recuperación

### 5.1 Restaurar código
- Si existe el commit de respaldo del working tree: `git checkout <hash> -- .` sobre una rama limpia.
- Si existe el ZIP de respaldo: descomprimir sobre una copia del repo (respetando `.venv`).

### 5.2 Recrear entorno
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q          # debe dar 189 passed
.\.venv\Scripts\python.exe -m flake8 src tests
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```

### 5.3 Levantar el sistema
```powershell
# Android (Opción B)
$env:CAMERA="phone"
$env:PHONE_CAM_URL="http://<ANDROID_IP>:8080/shot.jpg"
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000
# Dashboard: http://localhost:8000/dashboard  → selector "CAM-P: Android Phone"

# Hardware (Opción A, por defecto)
$env:CAMERA="vivotek"
$env:ECHOMIND_VIVOTEK_IP="192.168.40.10"

# Sin hardware
$env:CAMERA="simulation"
```

### 5.4 Validación física Android (FASE 2/3)
1. Instalar **IP Webcam** en el Android.
2. Misma red que el equipo de desarrollo (o hotspot propio).
3. Iniciar el servidor en la app; anotar `http://<ANDROID_IP>:8080`.
4. Desde el equipo: abrir `http://<ANDROID_IP>:8080/shot.jpg` → debe verse el snapshot.
5. `CAMERA=phone` + `PHONE_CAM_URL=...` → levantar EchoMind.
6. Dashboard → selector **PHONE** → comprobar badge **PHONE LIVE**.
7. Mostrar la mano frente a la cámara → esperar `camera_alert`.
8. "¿Qué ocurre ahora?" (tiempo real) → "¿Qué recuerdas de hoy?" (histórico).

---

## 6. Riesgos pendientes

1. **Todo el trabajo sigue sin commit** (riesgo #1): ejecutar el respaldo de FASE 4 sin demora.
2. **Validación física Android** no realizada (solo mock).
3. **Red del venue**: posible aislamiento de clientes; usar hotspot.
4. **Rutas vs. fuente activa**: vivotek/phone comparten la fuente; `X-Source` es la verdad.
5. **`MEMORY_ARCHITECTURE_V1.md`** desactualizado.
6. **Trabajo acoplado**: handlers privados reutilizados entre adaptadores.

---

## 7. Inventario de respaldo (checklist)

- [x] Punto de restauración creado: rama `checkpoint/day1-mobile-memory`, commit `0789ce4`, + ZIP del working tree.
- [x] `pytest` = 189 passed verificado tras el respaldo.
- [x] `flake8` / `black` limpios.
- [x] Arquitectura y dependencias documentadas (este archivo).
- [x] Procedimiento de recuperación documentado.
- [ ] Validación física Android — **diferida** (no bloquea; fuente física actual = webcam/Vivotek).

---

## 8. Punto de recuperación (resultado)

| Respaldo | Referencia |
|---|---|
| Rama git local | `checkpoint/day1-mobile-memory` |
| Commit | `0789ce4 feat: add historical memory (V1-V3) and Android phone camera source` |
| ZIP | `C:\Users\BagmDev\AppData\Local\Temp\opencode\echomind_checkpoint_day1_20261010_031728.zip` |
| `main` | intacta en `92029c3` (sin push, sin merge) |

Restaurar: `git checkout checkpoint/day1-mobile-memory` (o descomprimir el ZIP).
