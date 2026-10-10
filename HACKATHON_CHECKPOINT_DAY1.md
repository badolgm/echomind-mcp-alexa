# HACKATHON CHECKPOINT — DÍA 1

> Auditoría de Git del estado consolidado de EchoMind MCP Alexa.
> Fecha: 10-oct-2026 · HEAD: `92029c3 feat(watchdog): add visual trigger filtering and 10s speech cooldown`
> Objetivo del checkpoint: congelar el estado técnico y crear un punto de recuperación seguro.

---

## 1. Estado del repositorio

| Métrica | Valor |
|---|---|
| Rama | (working branch, sin commit definitivo del trabajo de los últimos sprints) |
| HEAD | `92029c3` |
| Últimos 11 commits | historia limpia; el **trabajo de memoria V1–V3 y de Android Camera NO está commiteado** |
| Tests | **189 passed** (175 + 13 unit + 1 integración) |
| flake8 | **0 errores** |
| black | **limpio** (60 archivos) |
| Archivos nuevos (untracked) | 18 rutas |
| Archivos modificados | 8 |

> ⚠️ Todo el valor reciente vive en el working tree. Sin commit/push no existe respaldo remoto.

---

## 2. Archivos modificados (tracked, sin commit)

| Archivo | Δ | Qué representa |
|---|---|---|
| `src/domain/models/tools.py` | +101 | Catálogo de tools: `memory_last_seen/search/summary/converse` + contrato de memoria |
| `src/infrastructure/adapters/mcp/tool_resolvers.py` | +97 | Registry: `memory=`, `current_state_provider=`, wiring del resolver de memoria |
| `src/infrastructure/services/ambient_watch_service.py` | 45 | Watchdog: filtrado por trigger visual + `model_analysis` + estado |
| `src/infrastructure/services/sensor_bus.py` | 73 (net −) | Sensor bus simplificado: **el movimiento real lo decide exclusivamente la cámara** |
| `src/main.py` | +86 | Composition root: `_build_camera()` (`CAMERA=vivotek/simulation/phone`), env phone, memoria, phone routes |
| `src/static/dashboard.html` | +77 | Control Center: fuente `PHONE` (LIVE/OFFLINE/SIM), SSE, TTS Alexa |
| `tests/unit/test_ambient_watch_service.py` | +161 | Tests del watchdog (movimiento/alertas) |
| `tests/unit/test_vivotek_adapter.py` | +69 | Tests del adaptador de cámara existente |

## 3. Archivos nuevos (untracked)

### Memoria (V1–V3)
| Archivo | Rol |
|---|---|
| `src/infrastructure/services/memory_service.py` | `MemoryRecord` + `VectorMemoryService` (embeddings hash deterministas, `MemoryVectorStorePort` para Qdrant futuro — NO implementado) |
| `src/infrastructure/services/memory_bridge.py` | Ingesta `camera_alert` (HIGH/CRITICAL) → `MemoryRecord` |
| `src/domain/services/memory_intent.py` + `__init__.py` | `MemoryIntentClassifier` (dominio puro, sin IO) |
| `src/infrastructure/adapters/mcp/memory_resolvers.py` | Resolvers deterministas de memoria + `memory_converse` |
| `MEMORY_ARCHITECTURE_V1.md` | Doc V1 (no actualizada a V2/V3) |

### Android Camera (Día 1)
| Archivo | Rol |
|---|---|
| `src/infrastructure/adapters/camera/http_phone_camera_adapter.py` | `HttpPhoneCameraAdapter` (IP Webcam) + `mount_phone_camera_routes` |
| `src/infrastructure/adapters/camera/__init__.py` | Paquete |

### Tests nuevos
`tests/unit/test_memory_service.py`, `test_memory_bridge.py`, `test_memory_query.py`, `test_memory_resolvers.py`, `test_memory_intent.py`, `test_memory_history.py`, `test_memory_converse.py`, `test_http_phone_camera_adapter.py`, `tests/integration/test_phone_camera_end_to_end.py`.

### Documentos de planificación
`HACKATHON_MASTER_PLAN.md`, `HACKATHON_CHECKPOINT_DAY1.md` (este), `CHECKPOINT_DAY1_SUMMARY.md`.

---

## 4. Resumen de cambios por bloque funcional

### Referencia — "Opción A+B" (fuente de visión dual)
> **Interpretación en este checkpoint:** las dos fuentes de visión **coexistentes y seleccionables** que implementan el mismo contrato `CameraFrameSource`:
> - **Opción A** = `VivotekCameraAdapter` (hardware IP `192.168.40.10`, ya existía).
> - **Opción B** = `HttpPhoneCameraAdapter` (Android + IP Webcam, nuevo en Día 1).
>
> ⚠️ **Aclaración honesta:** la variante B del análisis previo ("push desde navegador": `phone.html` + `POST /api/cam/phone/snapshot` con `getUserMedia`) **NO está implementada** — se descartó en favor de A (IP Webcam HTTP), que es la que está estable. Si "Opción A+B" se refería a esa variante del navegador, entonces solo la parte IP-Webcam existe.

Ambas fuentes:
- Comparten el fallback determinista (mismo frame limpio de `_generate_fallback_frame`).
- Alimentan **watchdog**, **MCP resolvers** (`_attach_raw_frame`) y rutas `/api/cam/vivotek/*` y `/api/cam/phone/*`.
- Se seleccionan por `CAMERA=vivotek|simulation|phone` o por `PHONE_CAM_URL`.

### Memoria
- V1: `VectorMemoryService` (store/search/last_seen/forget) + Port Qdrant (contrato).
- V2: `MemoryBridge` (ingesta solo HIGH/CRITICAL, tolerante a `MemoryError`), tools `memory_last_seen/search/summary`.
- V3: `MemoryIntentClassifier` (8 intenciones), capacidades históricas (top/high/critical/count), tool `memory_converse` con narrativa en español y estado actual + historia. **Sin LLM.**

### Alexa
- `alexa_skill/skill.json` (manifest de Alexa+ Agent Skill, commiteado).
- Servidor MCP Streamable HTTP 2025-11-25 + `SessionManager` (commiteado).
- Las 8 tools del catálogo (incluidas las 4 de memoria) son el contrato que consume Alexa+.

### Android Camera
- `HttpPhoneCameraAdapter`: snapshot `http://<android>:8080/shot.jpg`, cache TTL, timeout, fallback.
- `mount_phone_camera_routes`: `/api/cam/phone/snapshot|detections|state`.
- `_build_camera()` en `main.py` + selector `PHONE` en el dashboard.
- E2E programático: `tests/integration/test_phone_camera_end_to_end.py` (phone → watchdog → `camera_alert` → MemoryBridge → `memory_converse`).

---

## 5. Tests actuales

```
189 passed in 5.57s
```
| Grupo | Archivos | Cobertura |
|---|---|---|
| Memoria | 7 archivos (`test_memory_*`) | store/search/bridge/intent/history/converse |
| Android Camera | `test_http_phone_camera_adapter.py` (13) | live/fallback/ttl/routes/config |
| E2E Phone | `test_phone_camera_end_to_end.py` (1) | cadena completa |
| Watchdog/Visión/MCP | existentes | sin regresiones |

---

## 6. Dependencias

`requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic`, `boto3`, `mcp`, `httpx`, `pytest`, `pytest-asyncio`, `black`, `flake8`.

- **Día 1 no añadió ninguna dependencia** (httpx y FastAPI ya estaban).
- `pytest.ini`: `asyncio_mode = auto`.
- `setup.cfg`: flake8 `max-line-length=88`, `extend-ignore=E203,W503`, excluye `.venv,.local,build,dist`.

---

## 7. Riesgos actuales

1. **Sin respaldo remoto:** todo el trabajo de memoria + Android Camera vive sin commit. Pérdida del working tree = pérdida del valor.
2. **Validación física pendiente:** el camino Android real (`PHONE_CAM_URL`) no se ha probado contra hardware; solo con transporte mockeado.
3. **Dependencia de red del venue** para el celular (aislamiento de clientes Wi‑Fi).
4. **Rutas duales comparten fuente activa:** `/api/cam/vivotek/*` y `/api/cam/phone/*` sirven la misma instancia; `X-Source`/`detections.source` son la fuente de verdad.
5. **`MEMORY_ARCHITECTURE_V1.md` desactualizado** (no cubre V2/V3).
6. **Acoplamiento interno:** `mount_phone_camera_routes` reutiliza handlers privados de `vivotek_adapter`.

---

## 8. Acciones de recuperación

Si el working tree se pierde **antes** del respaldo: solo los 11 commits (`92029c3…b9b0708`) son recuperables; memoria y Android Camera se pierden.

Recuperación planificada en FASE 4 (`CHECKPOINT_DAY1_SUMMARY.md`) mediante punto de restauración (commit de respaldo y/o ZIP del working tree).
