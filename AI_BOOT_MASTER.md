# AI_BOOT_MASTER.md — Única fuente de verdad

> **Lee este archivo primero.** Si eres una IA/agente que retoma `echomind-mcp-alexa`,
> aquí está todo el contexto para continuar sin reconstruirlo. No hace falta auditar el
> repositorio de nuevo: esta es la verdad consolidada al `2026-10-11`.
>
> Este documento **no autoriza** cambios de arquitectura ni funcionalidades nuevas. Antes de
> tocar código, respeta la sección **10. NO HACER**.

> ### ⚠️ VISIÓN OFICIAL (obligatoria — ver `PROJECT_VISION_ALIGNMENT.md`)
> **EchoMind NO es una cámara, ni un dashboard, ni un robot Qdrant, ni una plataforma CCTV.**
> **EchoMind SÍ es ALEXA+** que puede **OBSERVAR → RECORDAR → COMPRENDER → CONVERSAR → RESPONDER**.
> La **protagonista siempre es Alexa**. La cámara, el Android y el dashboard son **medios**
> (sensor visual / consola operativa), nunca el producto. La **memoria** (`VectorMemoryService` +
> `MemoryBridge` + `MemoryConverse`) es el diferenciador real. Los dispositivos (Echo Show, Echo
> Hub, Ring, Blink…) aparecen solo como **Alexa Ecosystem Devices**. El **Facility Digital Twin**
> es **visión post-hackathon, no implementable** (§11).
>
> **Narrativa oficial:** `Alexa+ → EchoMind (agente cognitivo) → Memoria → Contexto → Conversación
> → Acción`. **La cámara NO es el producto. La Vivotek NO es el producto. Android NO es el
> producto.** Todos son **sensores o dispositivos del ecosistema de Alexa**.

> ### ✅ CHECKPOINT ACTUAL (2026-10-11) — **GO PARA VIDEO**
> - **208 tests PASS** (`pytest -q`) · `flake8` limpio · `black --check` limpio.
> - **BUG 1 corregido** — el panel ya no anuncia "movimiento" en `LOW`/`0%`/`[]` (aviso neutro ES/EN).
> - **BUG 2 corregido** — *Episode Coalescing*: una caminata = **un** recuerdo (no N).
> - Motion Fix, Voice Dock, DemoSeed, Bilingüismo y visión EchoMind/Alexa+ validados.
> - Detalle: `CHECKPOINT_DAY2_SUMMARY.md` · `UX_CLEANUP_REPORT.md`.

---

## 1. Identidad del proyecto

| Campo | Valor |
| --- | --- |
| Producto | **EchoMind** — agente cognitivo con memoria para Alexa+ |
| Repositorio | `echomind-mcp-alexa` |
| Remoto | `https://github.com/badolgm/echomind-mcp-alexa.git` (`origin`) |
| Owner | Badolgm |
| Licencia | MIT © 2026 |
| Hackathon | Amazon **Build, Ship, Shape 2026** (Alexa+ · AWS Builder · Open Source) |
| Stack | Python 3.11 · FastAPI · uvicorn · pydantic v2 · boto3 (Bedrock **Converse**) · `mcp` SDK · httpx |
| Arquitectura | **Hexagonal (Ports & Adapters)** + **DDD** · transporte **MCP Streamable HTTP** (`2025-11-25`) |
| Tema | Alexa+ se convierte en **cuidador proactivo**: vigila el hogar (caídas, mascotas, humo/fuego, intrusiones) y alerta sin que el usuario pregunte. |
| Protagonista | **ALEXA+** (observa → recuerda → comprende → conversa → responde). Cámara/dashboard = medios. Ver `PROJECT_VISION_ALIGNMENT.md`. |

**Propuesta de valor:** en lugar de esperar un comando de voz, EchoMind da a **Alexa+** una
**memoria ambiental**: observa señales del entorno (visuales/sensores), las **recuerda**, las
**comprende**, **conversa** sobre ellas y **responde** — siempre disponible gracias al **Quota
Fallback Protocol (QFP)** (motor de reglas local determinista que sustituye a Bedrock si AWS falla).
La **cámara es solo uno de los sentidos**; el valor es la memoria y la conversación.

---

## 2. Estado actual

| Indicador | Estado |
| --- | --- |
| Rama de trabajo | `checkpoint/day1-mobile-memory` |
| HEAD | **`407ca29`** — `docs: align EchoMind vision, Alexa+ narrative and hackathon strategy` |
| Árbol de trabajo | **Con cambios locales sin commitear** — BUG 1 + BUG 2 + `UX_CLEANUP_REPORT.md` (ver `CHECKPOINT_DAY2_SUMMARY.md` → FASE 4) |
| Push | **Nunca realizado** (`origin` existe pero no se ha subido nada) |
| Tests | **208 passed** (`pytest -q`) — 203 previos + 5 nuevos |
| flake8 | **0 violaciones** (`flake8 src tests`) |
| black | **Limpio** (`black --check src tests --line-length 88`) |
| Validación | Membresía de demo validada con navegador real (Chrome + Puppeteer): Seed, `/api/converse` EN/ES, micrófono (ruta STT) y TTS `en-US`/`es-ES`. `PAGE_ERRORS: []`. |
| **GO PARA VIDEO** | ✅ Motion Fix confirmado · Episode Coalescing (BUG 2) · aviso neutro (BUG 1) · 208 tests PASS |

**Gates obligatorias antes de cerrar cualquier fase** (PowerShell, venv explícito):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m flake8 src tests
.\.venv\Scripts\python.exe -m black --check src tests --line-length 88
```

Configuración: `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`), `setup.cfg`
(`max-line-length = 88`, `extend-ignore = E203,W503`).

---

## 3. Arquitectura oficial

### 3.1 Flujo canónico (pipeline de cognición ambiental)

> Nota de visión: en este pipeline la cámara es el **sensor de entrada**; la **protagonista es
> Alexa**, que recuerda (`VectorMemoryService`) y **conversa** (`MemoryConverse`). Ver
> `PROJECT_VISION_ALIGNMENT.md` §6.

```
CameraFrameSource
   → AmbientWatchService        (predicción determinista: sensores + frame_delta_ratio)
   → EventHub                   (broadcast SSE → /dashboard/events)
   → MemoryBridge               (ingesta de camera_alert HIGH/CRITICAL)
   → VectorMemoryService        (embeddings hash sha256 256-D, L2-normalizado)
   → MemoryIntentClassifier     (enrutado determinista ES/EN, sin LLM)
   → MemoryConverse             (narrativas deterministas ES/EN)
   → Alexa MCP                  (tools/call sobre Streamable HTTP)
```

### 3.2 Capas hexagonales (regla de dependencia **no negociable**)

```
domain  ←  application  ←  infrastructure        (las flechas apuntan SIEMPRE al dominio)
```

- `src/domain/` — núcleo puro. Sin FastAPI/boto3/MCP/IO. Solo stdlib (`dataclasses`, `abc`,
  `enum`, `typing`). Entidades inmutables (`@dataclass(frozen=True, slots=True)`).
- `src/application/` — casos de uso y DTOs. Dependen solo del dominio.
- `src/infrastructure/` — adaptadores (FastAPI MCP, Bedrock, fallback local, resolvers, cámara,
  memoria, watchdog, dashboard). Única capa que toca frameworks/SDKs.
- `tests/` — unit + integration, sin red ni AWS (puertos mockeados).

### 3.3 Catálogo de tools MCP (8) — `src/domain/models/tools.py`

| Tool | Categoría | Función |
| --- | --- | --- |
| `analyze_image_context` | analysis | Comprensión multimodal imagen/vídeo |
| `summarize_document` | knowledge | Resumen fiel de documentos |
| `schedule_reminder` | productivity | Recordatorios por tiempo |
| `analyze_ambient_stream` | **safety** | Monitorización continua (caídas, mascotas, humo, intrusiones) |
| `memory_last_seen` | knowledge | "¿Cuándo se vio X por última vez?" (memoria local, sin LLM) |
| `memory_search` | knowledge | Búsqueda semántica en memoria local |
| `memory_summary` | knowledge | Resumen de observaciones recientes |
| `memory_converse` | knowledge | Pregunta conversacional ES/EN → memoria local (enrutado determinista) |

### 3.4 Superficie HTTP (rutas reales)

| Ruta | Método | Función |
| --- | --- | --- |
| `/health` | GET | Liveness (`{"status":"ok","transport":"mcp/streamable-http"}`) |
| `/metrics` | GET | Telemetría (latencia, tool calls, QFP, `provider`) |
| `/` y `/dashboard` | GET | **EchoMind MCP Control Center** (dashboard) |
| `/dashboard/events` | GET (SSE) | Tools log + `camera_alert` en vivo |
| `/mcp` | POST/GET | Transporte MCP Streamable HTTP (Alexa+) |
| `/api/cam/vivotek/snapshot` | GET | JPEG en vivo (proxy inverso) |
| `/api/cam/vivotek/detections` | GET | `{source, live, detections}` |
| `/api/cam/vivotek/state` | GET | Último veredicto del watchdog |
| `/api/cam/phone/snapshot` | GET | JPEG desde Android IP Webcam |
| `/api/cam/phone/detections` | GET | Detecciones fuente PHONE |
| `/api/cam/phone/state` | GET | Estado watchdog fuente PHONE |
| `/api/demo/seed` | **POST** | Siembra 5 memorias históricas de demo |
| `/api/converse` | **POST** | Pregunta conversacional → memoria (ES/EN) |

### 3.5 Configuración por entorno

| Variable | Default | Propósito |
| --- | --- | --- |
| `CAMERA` | (vacío → Vivotek) | Fuente de visión: `vivotek` · `simulation` · `phone` |
| `PHONE_CAM_URL` | (IP Webcam) | URL del snapshot del teléfono Android |
| `PHONE_TIMEOUT` | (default del adapter) | Timeout HTTP del adapter PHONE |
| `PHONE_CACHE_TTL` | (default del adapter) | TTL de caché de frame PHONE |
| `ECHOMIND_VIVOTEK_IP` | `192.168.40.10` | Host de la cámara Vivotek FD8367 |
| `ECHOMIND_DEMO_SEED` | `0` | `1/true/yes` → siembra memoria al arrancar |
| `ECHOMIND_BEDROCK_MODEL_ID` | `amazon.nova-micro-v1:0` | Modelo primario |
| `ECHOMIND_BEDROCK_REGION` | `us-east-1` | Región AWS |
| `ECHOMIND_FALLBACK_COOLDOWN_SECONDS` | `300` | Cooldown del breaker QFP |
| `ECHOMIND_SESSION_IDLE_TIMEOUT` | `300` | Expiración de sesión MCP |
| `ECHOMIND_SSE_KEEPALIVE_SECONDS` | `15` | Keep-alive SSE |
| `ECHOMIND_HOST` / `ECHOMIND_PORT` | `0.0.0.0` / `8000` | Bind de uvicorn |

> Con `CAMERA=simulation` el sistema no toca hardware: genera frame de test determinista y el QFP
> mantiene todo operativo. Ideal para grabación de vídeo sin cámara.

---

## 4. Checkpoints

| Checkpoint | Commit | Doc | Contenido |
| --- | --- | --- | --- |
| Day 1 recovery point | `eee7355` | `HACKATHON_CHECKPOINT_DAY1.md` · `CHECKPOINT_DAY1_SUMMARY.md` | Punto de recuperación: rama, commit y ZIP de respaldo |
| Day 1 feature | `0789ce4` | — | Memoria histórica V1-V3 + fuente de cámara Android |
| **Estado validado actual** | **`407ca29`** | **este archivo** | Visión EchoMind alineada, narrativa Alexa+ |
| **Checkpoint Day 2** | **`407ca29`** (+ cambios locales) | **`CHECKPOINT_DAY2_SUMMARY.md`** · `UX_CLEANUP_REPORT.md` | 208 tests PASS, BUG 1 + BUG 2 corregidos, GO PARA VIDEO |

- Rama de checkpoint: **`checkpoint/day1-mobile-memory`**.
- `main` permanece intacta en `92029c3` (no se ha mezclado).
- Respaldo ZIP (máquina local): `C:\Users\BagmDev\AppData\Local\Temp\opencode\echomind_checkpoint_day1_20261010_031728.zip`.

---

## 5. Commits importantes (más reciente primero)

```
407ca29  docs: align EchoMind vision, Alexa+ narrative and hackathon strategy       ← HEAD
093a8ad  feat: demo seed, bilingual memory converse, voice dock and motion fixes
eee7355  docs(checkpoint): record day1 recovery point (branch, commit, zip)
0789ce4  feat: add historical memory (V1-V3) and Android phone camera source
92029c3  feat(watchdog): add visual trigger filtering and 10s speech cooldown       ← main
bc6e4d7  feat(dashboard): add dynamic camera selector, Alexa device catalog and graceful fallback
065d133  docs: update MASTERDOC and README with Web Control Center and Vivotek IoT integration
2fdd39b  fix(qfp): refine fallback rule engine precision and integrate ambient camera resolver
74e277b  feat(iot): add Vivotek FD8367 async camera adapter and detection endpoints
```

---

## 6. Tests actuales (208 passed)

**Integración** (`tests/integration/`):
`test_main_composition.py` · `test_mcp_streaming_session.py` · `test_memory_api_routes.py` ·
`test_phone_camera_end_to_end.py` · `test_telemetry_and_skill.py`

**Unitarios** (`tests/unit/`):
`test_agent_tools.py` · `test_ambient_awareness.py` · `test_ambient_watch_service.py` ·
`test_bedrock_multimodal_adapter.py` · `test_demo_seed_service.py` · `test_fallback_adapter.py` ·
`test_fastapi_mcp_adapter.py` · `test_http_phone_camera_adapter.py` · `test_memory_bridge.py` ·
`test_memory_converse.py` · `test_memory_converse_bilingual.py` · `test_memory_history.py` ·
`test_memory_intent.py` · `test_memory_query.py` · `test_memory_resolvers.py` ·
`test_memory_service.py` · `test_process_intent.py` · `test_process_multimodal_intent.py` ·
`test_vivotek_adapter.py` · `test_web_dashboard.py`

> Ejecutar con `.\.venv\Scripts\python.exe -m pytest -q`. Todo offline.

**Nuevos (+5, 208-203)** — `test_ambient_watch_service.py`:
`test_predict_low_without_detections_reports_calm`, `test_low_state_model_analysis_is_neutral`;
`test_memory_bridge.py`: `test_consecutive_motion_ticks_coalesce_into_one_episode`,
`test_motion_after_gap_starts_a_new_episode`, `test_distinct_detection_sets_are_distinct_episodes`.

---

## 7. Componentes terminados

| Componente | Estado | Ubicación / nota |
| --- | --- | --- |
| **Android Camera** | ✅ | Sensor visual de entrada · `src/infrastructure/adapters/camera/http_phone_camera_adapter.py` (`HttpPhoneCameraAdapter`, `mount_phone_camera_routes`); selección vía `CAMERA=phone` / `PHONE_CAM_URL`. Validación **física** final pendiente. |
| **Memory V1-V3** | ✅ | `src/infrastructure/services/memory_service.py` (`VectorMemoryService`, `MemoryRecord`, `embed_text` 256-D, `MemoryVectorStorePort` **stub**). 8 intenciones en `src/domain/services/memory_intent.py`. |
| **DemoSeed** | ✅ | `src/infrastructure/services/demo_seed_service.py` (`seed_demo_memory`, 5 registros canónicos: pet/patio, smoke/kitchen, gate/cam-01, fall/living, elderly/living). |
| **MemoryConverse** | ✅ | `src/infrastructure/adapters/mcp/memory_resolvers.py` (`build_memory_converse_resolver`); narrativas deterministas ES/EN. |
| **MemoryBridge** | ✅ | `src/infrastructure/services/memory_bridge.py`; ingesta de `camera_alert` HIGH/CRITICAL al EventHub. |
| **Voice Dock** | ✅ | `src/static/dashboard.html` — seed, input, mic (`SpeechRecognition`), `LANG EN/ES`, TTS (`speakAlexa`), pills. Fix de `renderBoxes()` (re-inserta `alertEl` + null-guards). |
| **Bilingüismo EN/ES** | ✅ | Clasificador con hints ES/EN (`_SPANISH_HINTS`/`_ENGLISH_HINTS`) + `lang` explícito. Validado en navegador. |
| **Motion Detection** | ✅ corregido | `ambient_watch_service.py`: `_image_payload()` recorta hasta SOS/IDAT (ignora EXIF de IP Webcam) y `MOTION_THRESHOLD = 0.20`. Evidencia: delta EXIF-only = 0.0, cambio real = 0.9998. |
| **BUG 1 — aviso neutro** | ✅ corregido | `ambient_watch_service.py`: `_NEUTRAL_ANNOUNCEMENT` + `_announcement()` — en `LOW`/`0%`/`[]` ya no anuncia "movimiento"; `model_analysis` coherente con `risk`. |
| **BUG 2 — Episode Coalescing** | ✅ corregido | `memory_bridge.py`: coalescing por episodio (`location` + set de labels, `episode_gap=30 s`). 60 ticks → **1** recuerdo MOTION. |
| **MCP funcional** | ✅ | `src/infrastructure/adapters/mcp/fastapi_mcp_adapter.py` + `alexa_skill/skill.json`. |
| **Dashboard** | ✅ | `src/infrastructure/adapters/mcp/web_dashboard.py` sirve `src/static/dashboard.html`. |
| **QFP (resiliencia)** | ✅ | `src/infrastructure/adapters/aws/fallback_llm_adapter.py` (`ResilientLLMAdapter`, `RuleBasedLLMAdapter`). |

---

## 8. Riesgos pendientes

1. **Validación Android física (IP Webcam) diferida** — el fix de movimiento se validó con EXIF
   sintético, no sobre un stream real de dispositivo. Único P0 técnico abierto.
2. **Semántica "today" == "yesterday"** — ambas consultas caen en la ventana de 24 h (sin corte
   de frontera diaria). Evitar la pregunta "yesterday" en el guion o aceptarlo.
3. **Sin LLM/embeddings reales** — narrativas deterministas y embeddings hash; Qdrant **no**
   implementado (`MemoryVectorStorePort` es solo contrato). A favor de la demo offline.
4. **Web Speech API** — el micrófono requiere `SpeechRecognition` → usar **Chrome/Edge**; la ASR
   acústica real necesita micrófono físico (comprobación manual de 10 s).
5. **Residuales cosméticos** — `404 /favicon.ico` y `<polyline> NaN` en el sparkline (preexistente,
   no bloquea).
6. **Sin push** — el trabajo vive solo en local. Commitear/empujar antes de la entrega si se desea
   respaldo remoto. **Cambios sin commitear:** BUG 1 + BUG 2 + `UX_CLEANUP_REPORT.md`
   (ver `CHECKPOINT_DAY2_SUMMARY.md` → FASE 4).

---

## 9. Roadmap del hackathon

**Pendientes de entrega (no son código):**
- [ ] **Validación Android física final** (IP Webcam real).
- [ ] **Guion de demo** → `DEMO_SCRIPT_V1.md` (hecho).
- [ ] **Vídeo en inglés** → `VIDEO_RECORDING_GUIDE.md` (hecho).
- [ ] **Devpost** → `DEVPOST_CHECKLIST.md` (hecho).

**Fases técnicas ya completadas (P6-P8 + memoria):**
- [x] Phase 1-5 — dominio, multimodal, sesiones/SSE, QFP, skill/Docker/observabilidad.
- [x] Phase 6 — EchoMind MCP Control Center (dashboard).
- [x] Phase 7 — cámara Vivotek en vivo + overlay de detecciones.
- [x] Phase 8 — watchdog ambiental autónomo (sensores + motion).
- [x] Memory V1-V3 — memoria vectorial local + conversación bilingüe + DemoSeed + Voice Dock.
- [x] Android Camera source (`CAMERA=phone`).

---

## 10. NO HACER

Prohibiciones explícitas (vigentes hasta nuevo aviso del owner):

- ❌ **Introducir Qdrant real** — `MemoryVectorStorePort` es contrato; el motor local es la verdad.
- ❌ **Introducir CLIP** (embeddings visuales).
- ❌ **Introducir Whisper** (ASR local).
- ❌ **Introducir `investigate_incident`** (tool).
- ❌ **Implementar el Digital Twin** (solo visión, ver sección 11).
- ❌ **Modificar la arquitectura** ni la regla de dependencia hexagonal.
- ❌ **Añadir funcionalidades** durante fase de documentación/entrega.
- ❌ **Commit o push autónomos** — solo si el owner lo pide explícitamente.
- ❌ **Force-push, amend o tocar config de git**; nunca commitear credenciales ni `.local/`.

Espacio de scratch permitido: **`.local/`** (gitignored).

---

## 11. Facility Digital Twin (VISIÓN POST HACKATHON — NO IMPLEMENTAR)

> **Estado: visión registrada, no implementada.** No introduce código, dependencias ni
> funcionalidades. Requiere aprobación explícita del owner tras el hackathon. Ver
> `PROJECT_VISION_ALIGNMENT.md` §9.

Concepto para una fase posterior al hackathon: un **gemelo digital de la instalación** que
reconstruya el estado físico (habitaciones, accesos, ocupantes, activos) a partir de la memoria
histórica ya persistida, y permita consultar escenarios ("¿qué pasaría si se abre la reja a las
3 a.m.?").

Cadena conceptual:

```
Plano PNG/SVG
      ↓
Ubicación de dispositivos Alexa   (Echo Hub / Show…)
      ↓
Ubicación de sensores             (cámaras / sensores de entrada)
      ↓
Memoria espacial                  (VectorMemoryService: eventos con ubicación)
      ↓
Alexa contextual                  ("¿qué pasó en la cocina?" / "ve a la reja")
```

Pilares conceptuales (reutilizan lo ya construido, sin nuevas dependencias):

1. **Memoria como base de conocimiento** — `VectorMemoryService` ya almacena eventos con
   ubicación, detección, riesgo y análisis; el gemelo los proyecta sobre un plano.
2. **Streaming de estado** — `AmbientWatchService` + `EventHub` ya emiten el estado vivo
   (`camera_alert`, `last_state`) que alimentaría el gemelo en tiempo real.
3. **Modelo determinista** — el gemelo sería una proyección explicable (sin ML runtime), coherente
   con la filosofía QFP/edge.

**Nota:** esta sección documenta la intención para no perderla; **no autoriza** trabajo de
implementación. Cualquier avance requiere aprobación explícita del owner y una fase propia.

---

## Archivos clave (mapa de navegación)

```
src/main.py                                          composition root (IoC) + rutas HTTP
src/domain/models/tools.py                           catálogo de 8 tools
src/domain/services/memory_intent.py                 clasificador de intención (8, ES/EN)
src/infrastructure/adapters/mcp/memory_resolvers.py  MemoryConverse + narrativas ES/EN
src/infrastructure/adapters/mcp/tool_resolvers.py    registro/ejecución de tools
src/infrastructure/adapters/mcp/web_dashboard.py     sirve dashboard.html
src/infrastructure/adapters/iot/vivotek_adapter.py   cámara Vivotek + frame_delta_ratio
src/infrastructure/adapters/camera/http_phone_camera_adapter.py  cámara Android
src/infrastructure/services/ambient_watch_service.py watchdog + MOTION_THRESHOLD
src/infrastructure/services/memory_service.py        VectorMemoryService (memoria local)
src/infrastructure/services/memory_bridge.py         ingesta EventHub → memoria
src/infrastructure/services/demo_seed_service.py     DemoSeed (5 registros)
src/infrastructure/services/sensor_bus.py            sensores simulados (ciclo 120 s)
src/static/dashboard.html                            Control Center + Voice Dock
alexa_skill/skill.json                               manifest Alexa+ (MCP Streamable)
tests/unit · tests/integration                       208 tests
```

**Docs relacionados:** `PROJECT_VISION_ALIGNMENT.md` (visión oficial) · `README.md` ·
`MASTERDOC.md` · `AI_INSTRUCTIONS.md` · `MEMORY_ARCHITECTURE_V1.md` · `HACKATHON_MASTER_PLAN.md` ·
`HACKATHON_CHECKPOINT_DAY1.md` · `CHECKPOINT_DAY1_SUMMARY.md` · `CHECKPOINT_DAY2_SUMMARY.md` ·
`DEMO_SCRIPT_V1.md` · `VIDEO_RECORDING_GUIDE.md` · `DEVPOST_CHECKLIST.md` · `UX_CLEANUP_REPORT.md`.

_Última actualización: 2026-10-11 · Fase: checkpoints de documentación y protección de estado · HEAD `407ca29` (+ BUG 1/BUG 2 sin commitear)._
