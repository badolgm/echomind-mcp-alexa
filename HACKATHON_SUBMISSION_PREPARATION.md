# HACKATHON_SUBMISSION_PREPARATION.md

**Hackathon:** Build, Ship, Shape: Amazon Developer Hackathon (Devpost `amazonappdev2026`)
**Submission Period:** 31 AGO 2026 (10:15 PT) → **23 OCT 2026 (12:00 PT)** · Judging: 9–20 NOV · Winners: ~3 DIC
**Project:** EchoMind — Cognitive Memory Agent for Alexa+
**Primary Track:** **Alexa+** · **Mini Challenges:** **AWS Builder** + **Open Source**
**Fecha del documento:** 2026-10-17
**Alcance:** SOLO preparación de entrega. **No código · no commits · no push.**

> Fuente normativa: Rules oficiales (`amazonappdev2026.devpost.com/rules`). Los textos marcados **“TEXTO PARA DEVPOST (EN)”** son copy-paste directo al formulario (inglés obligatorio).

---

## 0. Datos clave del formulario

| Campo | Valor |
|---|---|
| Nombre del proyecto | **EchoMind — Cognitive Memory Agent for Alexa+ (MCP × AWS Bedrock)** |
| Tagline | *EchoMind gives Alexa+ a memory: it observes, remembers, understands, converses and responds — in English and Spanish, even offline.* |
| Primary Track | **Alexa+** |
| Mini Challenges | **AWS Builder**, **Open Source** |
| Repo URL | `https://github.com/badolgm/echomind-mcp-alexa` |
| License | MIT © 2026 Badolgm |
| Video URL | _pendiente de grabar/subir (YouTube/Vimeo, público/no listado, <3 min, EN)_ |
| Testing access | Repo público → sin credenciales; si privado → añadir colaboradores + login |

**Reglas duras a recordar:**
- Todos los materiales (vídeo, descripción, docs) **en inglés** o con traducción EN.
- Repo **público con licencia** detectables en *About* **o** privado compartido con `chris-trag, knmeiss, giolaq, anishamalde, mosesroth, emersonsklar`.
- Hook de runtime (Alexa+): tecnología requerida **importada y llamada en código** (no solo README). ✅ EchoMind.
- Un proyecto puede ganar **1 premio de track + 1 premio de mini-challenge**.

---

## 1. Submission Checklist completo

### 1.1 Formulario Devpost (campos obligatorios)
- [ ] Título + tagline.
- [ ] **Text description** (features + functionality) — ver §1.3 y borradores en §7/§9.
- [ ] **Which Primary Track** = Alexa+.
- [ ] **Which Mini Challenge(s)** = AWS Builder, Open Source.
- [ ] **Repo URL** (público o privado compartido).
- [ ] **Demo video URL** (YouTube/Vimeo, EN, <3 min).
- [ ] **Product Feedback** por cada tool/API/SDK (§2).
- [ ] **AWS Builder**: describir servicios AWS usados y cómo, en Product Feedback (§4).
- [ ] **Open Source**: contribution URL + repo URL + GitHub username + descripción (§5).
- [ ] **Optional – Feature Requests** (§2.3).
- [ ] **Optional – Friction Logs** (bonus hasta +10%) (§3).
- [ ] **“Significant updates”** si el proyecto existía antes (§9).

### 1.2 Repositorio (para *Stage One* pass/fail)
- [ ] Repo público **con licencia visible en About** (MIT) **o** privado + 6 colaboradores Amazon.
- [ ] `README.md` con **setup & run instructions claras** (§8).
- [ ] Todo el código/activos/instrucciones necesarios presentes.
- [ ] `.gitignore` sin secretos; `requirements.txt` limpio.
- [ ] ⚠️ **Resolver `.local/`**: los scripts de demo/simulador están **gitignored** (`gitignore:6`) pero referenciados en README/skill.json → **rompen el requisito de “setup & run instructions”**. Ver §6.
- [ ] 🚩 **Corregir conteos de tests obsoletos** (README “102” ×2; checklist “203”; real **208**).

### 1.3 Vídeo (para *Stage One/Two*)
- [ ] Duración **< 3:00** (objetivo 2:30–2:50).
- [ ] **Inglés** (subtítulos EN).
- [ ] Muestra el proyecto **funcionando en la plataforma** (browser + PowerShell).
- [ ] Muestra la **tecnología requerida en acción** (MCP Streamable HTTP: `initialize` → `tools/list` → `tools/call`).
- [ ] Sin **trademarks de terceros** ni **música con copyright**.
- [ ] Subido a **YouTube/Vimeo** público/no listado; enlace en Devpost.

### 1.4 Cierre
- [ ] Guardar **draft** y enviar antes del **23 OCT 12:00 PT**.
- [ ] (Opcional) Pedir créditos AWS — **cerrado el 7 OCT** (sin stock).

---

## 2. Product Feedback draft

Formato oficial (responder **por cada** tool/API/SDK):
**(a)** ¿Qué usaste y para qué? · **(b)** ¿Qué funcionó bien? · **(c)** ¿Qué necesita mejorar? · **(d)** Onboarding (zero → hello world) · **(e)** ¿Construirías de nuevo? Sí/No y por qué.

### 2.1 MCP (Model Context Protocol) — spec `2025-11-25`, Streamable HTTP
- **(a)** Núcleo del track Alexa+: servidor MCP self-hosted que emula un Agent Skill de Alexa+ sobre Streamable HTTP (`POST /mcp`, SSE, `Mcp-Session-Id`), con 8 tools del catálogo.
- **(b)** El transporte Streamable HTTP con sesiones y keepalive SSE fue sólido; el handshake `initialize`/`notifications/initialized` y `tools/list`/`tools/call` funcionaron con latencia sub-ms en ASGI.
- **(c)** La spec `2025-11-25` aún evoluciona: faltan ejemplos canónicos de **session server-initiated stream** y de **reconnection/resume**; el versionado del protocolo obliga a tocar código al subir de revisión.
- **(d)** Buena: docs en `modelcontextprotocol.io` y JSON-RPC 2.0 familiar. La parte más lenta fue modelar correctamente el ciclo de vida de la sesión y el `text/event-stream`.
- **(e)** **Sí.** El protocolo es agnóstico de framework y encaja con arquitectura hexagonal; permitió exponer tools sin atar el dominio a un SDK.

### 2.2 Amazon Bedrock (Bedrock Runtime · Converse API · Amazon Nova)
- **(a)** LLM primario del agente. `boto3.client("bedrock-runtime").converse(...)` con bloques multimodales (imagen/vídeo/audio/documento) vía `BedrockLLMAdapter`; modelo `amazon.nova-micro-v1:0`.
- **(b)** Una sola API **Converse** unifica texto + visión + documentos, sin `promptTemplates` por modelo; los content blocks multimodales son directos.
- **(c)** **Throttling/cuota y errores de credenciales** llegan como `ClientError` con códigos variados; la disponibilidad por región/modelo no es homogénea. Pediría manejo de cuota más predecible y errores más accionables.
- **(d)** Onboarding rápido con la cadena de credenciales estándar (env/IAM); el *hello world* fue inmediato, el reto fue la **resiliencia** (→ QFP).
- **(e)** **Sí.** Converse simplifica lo multimodal; solo pido mejor telemetría de cuota.

### 2.3 AWS SDK for Python (boto3)
- **(a)** Cliente de Bedrock Runtime; envuelto en `asyncio.to_thread` para no bloquear el event loop.
- **(b)** Maduro, documentado, inyección de cliente trivial para tests.
- **(c)** Es **síncrono**; en un servidor async obliga a usar hilos. Un cliente async nativo evitaría el puente.
- **(d)** Inmediato.
- **(e)** **Sí**, aunque preferiría una ruta async-first para cargas I/O-bound.

### 2.4 FastAPI + Uvicorn (+ Starlette/SSE)
- **(a)** Servidor HTTP del endpoint MCP, dashboard, endpoints `/api/*`, `/health`, `/metrics` y stream SSE.
- **(b)** DX excelente, tipado con Pydantic, ASGI rápido, SSE sencillo con `StreamingResponse`.
- **(c)** SSE de larga vida requiere cuidado con keepalive/timeouts; nada bloqueante.
- **(d)** Muy rápida.
- **(e)** **Sí.**

### 2.5 httpx
- **(a)** Simulador MCP, runner de demo y **proxy inverso** de la cámara IP (`/api/cam/vivotek/snapshot`).
- **(b)** API async limpia, timeouts y `stream()` directos.
- **(c)** Para MJPEG/streaming continuo, un helper de reconexión integrado ayudaría.
- **(d)** Inmediata.
- **(e)** **Sí.**

### 2.6 Pillow (PIL)
- **(a)** Comparación de frames (grayscale 48×48, diff de píxeles) para movimiento robusto frente a falsos positivos por EXIF.
- **(b)** Rápido y estable; ideal para el test de movimiento.
- **(c)** Ninguna relevante.
- **(d)** Inmediata.
- **(e)** **Sí.**

### 2.7 Web Speech API (browser: STT + TTS)
- **(a)** Voz de la consola (es-ES/es-MX) y reconocimiento de habla para el flujo conversacional.
- **(b)** Sin backend y soportada en Chrome/Edge.
- **(c)** **Selección de voz no determinista entre navegadores/SO** (p.ej. ausencia de voz `en-US` en ciertos hosts) y comportamiento distinto de `voiceschanged`. Pediría una API estable de selección de voz y garantía de voces por idioma.
- **(d)** Sencilla, con fricción en la selección de voz.
- **(e)** **Sí**, para demos; para producción usaría una voz de nube (p.ej. Polly).

### 2.8 Otras tecnologías (respuestas breves)
- **Alexa+ Agent Skills (`skill.json`)** — (a) manifiesto del skill MCP; (b) estructura clara; (c) faltan ejemplos canónicos para `mcp`+multimodal; (d) guiado por docs; (e) Sí.
- **Docker (multi-stage python:3.11-slim)** — (a) empaquetado y healthcheck; (b) reproducible; (c) imagen base grande; (d) trivial; (e) Sí.
- **SSE / JSON-RPC 2.0** — (a) mensajería MCP; (b) estándar; (c) nada; (d) conocido; (e) Sí.

### 2.9 Product Feedback — resumen para el formulario
> **EN:** “EchoMind uses the Model Context Protocol (spec 2025-11-25, Streamable HTTP) for the Alexa+ agent surface; Amazon Bedrock (Converse API, Amazon Nova) with boto3 for multimodal reasoning; FastAPI/Uvicorn for the MCP server; httpx for the MCP client, demo runner and camera reverse-proxy; Pillow for motion analysis; and the browser Web Speech API for voice. Full per-tool feedback is included below [pegar §2.1–2.8].”

---

## 3. Friction Log draft (opt-in · bonus hasta +10%)

Formato oficial por entrada: **task attempted · steps · expected vs actual · severity · workaround · actionable suggestion.**

### Friction 1 — Cuota/credenciales AWS rompen la sesión
- **Task:** Responder una alerta ambiental CRITICAL end-to-end vía MCP.
- **Steps:** Levantar servidor sin credenciales → `tools/call analyze_ambient_stream`.
- **Expected vs actual:** Esperaba respuesta; obtenía excepción `ClientError` (credenciales/throttling) que cortaba la sesión.
- **Severity:** **High**.
- **Workaround:** `ResilientLLMAdapter` (circuit breaker) → `RuleBasedLLMAdapter` determinista (Quota Fallback Protocol). Sesión intacta.
- **Suggestion:** Errores de cuota/credencial normalizados y un modo “graceful degradation” documentado en el Converse API.

### Friction 2 — Falsos positivos de movimiento (EXIF de IP Webcam)
- **Task:** Detección de movimiento fiable sobre JPEG.
- **Steps:** Diff de bytes entre frames consecutivos de Android IP Webcam.
- **Expected vs actual:** Esperaba movimiento real; el **EXIF/timestamp** cambiaba cada frame → disparo constante.
- **Severity:** **High**.
- **Workaround:** Recortar hasta el marcador `SOS` (`_image_payload`) + umbral `0.20`. Delta EXIF-only verificado = 0.0.
- **Suggestion:** En IP Webcam, opción para strips EXIF/timestamp, o documentación explícita del solapamiento JPEG.

### Friction 3 — Navegador vs cámara física (MJPEG/ActiveX/CORS)
- **Task:** Ver el feed del Vivotek FD8367 en el dashboard.
- **Steps:** `<img src>` directo al stream MJPEG del dispositivo.
- **Expected vs actual:** Esperaba render; el navegador bloquea MJPEG/ActiveX y aplica CORS.
- **Severity:** **Medium**.
- **Workaround:** Proxy inverso `httpx` en `/api/cam/vivotek/snapshot` + frame sintético de fallback.
- **Suggestion:** Documentar consumo de MJPEG en navegadores modernos y ejemplos CORS en la doc del dispositivo.

### Friction 4 — Bilingüismo determinista sin LLM
- **Task:** Responder igual en ES/EN incluso sin nube.
- **Steps:** Clasificar intención y narrar recuerdos sin LLM.
- **Expected vs actual:** Esperaba paridad; la heurística de idioma era ambigua.
- **Severity:** **Medium**.
- **Workaround:** Hints ES/EN + parámetro `lang` explícito en `/api/converse`.
- **Suggestion:** APIs de detección de idioma ligeras y deterministas para edge.

### Friction 5 — Error JS en `renderBoxes()` (nodo destruido)
- **Task:** Render de cajas de detección + alerta.
- **Steps:** `innerHTML = ""` y re-render.
- **Expected vs actual:** Esperaba actualización; se destruía el nodo de alerta y se perdían listeners.
- **Severity:** **Medium**.
- **Workaround:** Re-insertar `alertEl` + null-guards; verificado `PAGE_ERRORS: []`.
- **Suggestion:** — (bug de app, corregido).

### Friction 6 — Integrar un móvil como cámara
- **Task:** Usar un Android con IP Webcam como sensor.
- **Steps:** Adaptar la fuente de frames.
- **Expected vs actual:** Esperaba plug-and-play; formato/EXIF distintos.
- **Severity:** **Low/Medium**.
- **Workaround:** `HttpPhoneCameraAdapter` (`CAMERA=phone`) con TTL de caché ajustado (1.5 s → 0.4 s).
- **Suggestion:** Documentar formatos/credenciales de IP Webcam.

---

## 4. AWS Builder — Eligibility Review

**Requisito:** *“Any primary track project that incorporates AWS services (Bedrock, AgentCore, Strands SDK, Kiro Crew, SageMaker…) with documented integrations.”* + describirlo en Product Feedback.
**Cláusula clave:** *“Kiro Crew qualifies on its own… a submission does not need to also call a runtime AWS service.”*
**Ejemplo “obvious” del jurado:** *“single Bedrock call”*. **“Creative”:** *“multi-service pipeline (Bedrock + AgentCore + Strands)”*.

| Criterio | Estado | Evidencia |
|---|---|---|
| Servicio AWS incorporado | ✅ | **Amazon Bedrock** (Bedrock Runtime, **Converse API**), modelo **Amazon Nova Micro** |
| Llamado en runtime | ⚠ | `BedrockLLMAdapter` es `primary` en `ResilientLLMAdapter`; con 0 credenciales cae al rule engine (QFP) → hay que **demostrar la llamada real** o declarar Kiro |
| Integración **documentada** | ⚠ | Requiere texto explícito en Product Feedback + README |
| Valor técnico (“creative”) | ⚠ | Hoy ≈ “single Bedrock call” → subir a multi-servicio o declarar Kiro |

**Veredicto: ELEGIBLE** (con 2 acciones): (1) pegar la descripción de §4 abajo; (2) si se usó **Kiro** en el desarrollo, declararlo (califica solo). Ideal: en el vídeo, mostrar una llamada Bedrock real (o explicar QFP honestamente).

**TEXTO PARA DEVPOST (EN) — AWS Builder:**
> **AWS service(s) used and how:** EchoMind uses **Amazon Bedrock** as its primary reasoning engine, calling the **Converse API** via **boto3** (`bedrock-runtime`) with the **Amazon Nova Micro** model from the composition root (`ResilientLLMAdapter → BedrockLLMAdapter`). Bedrock handles multimodal reasoning (image/video/audio/document content blocks) for the agent tools. To guarantee 24/7 availability, a **Quota Fallback Protocol** (`ResilientLLMAdapter` circuit breaker) fails over transparently to a deterministic local rule engine when Bedrock throttles or credentials/quota are unavailable — the MCP/Alexa+ session never breaks. Region/model are configurable (`ECHOMIND_BEDROCK_REGION`, `ECHOMIND_BEDROCK_MODEL_ID`); IAM role/credential-chain ready. [Si aplica:] We also used **Kiro** during development.

---

## 5. Open Source — Eligibility Review

**Requisito:** *“Create a **new, additional** open-source project **or** contribute to an existing public repository during the hackathon window, **alongside** a primary track submission. Contributions can be a new repo (with license), a branch, a fork, or a PR. Required: contribution URL, project repository URL, GitHub username, and a description of what you did, how it works, and why it matters.”*
**Ejemplo “obvious”:** README/typo/formatting. **“Creative”:** feature con tests, bug fix que desbloquea a otros, nuevo patrón de integración.

| Criterio | Estado | Nota |
|---|---|---|
| Licencia open-source | ✅ | MIT en repo EchoMind |
| Repo público | ⚠ | Confirmar visibilidad + licencia en *About* |
| **Artefacto ADICIONAL** (nuevo repo/rama/fork/PR) | ⚠/❌ | El repo del track Alexa+ **por sí solo puede no contar**; el texto dice *“new, **additional** … alongside a primary track submission”* |
| Contribution URL + descripción | ❌ | Pendiente |

**Veredicto: ELEGIBLE si se añade una contribución ADICIONAL.** Para asegurar la elegibilidad, elegir 1 de:
- **(Recomendado, “creative”)** Extraer un componente reutilizable a un repo/paquete propio con tests y licencia, p.ej. **`resilient-llm-adapter`** (circuit breaker + graceful fallback) o **`mcp-streamable-session`** (gestión de sesiones/keepalive MCP). → nueva feature con tests = encaja en “creative”.
- **Contribución a un repo público existente** (branch/fork/PR, aunque no se fusione) durante la ventana del hackathon.

**TEXTO PARA DEVPOST (EN) — Open Source (usar la opción elegida):**
> **Contribution URL:** `<url del repo/rama/PR adicional>` · **Project repository URL:** `https://github.com/badolgm/echomind-mcp-alexa` · **GitHub username:** `badolgm`
> **What I did / how it works / why it matters:** I factored EchoMind's resilience layer into a standalone, dependency-light open-source package [`resilient-llm-adapter`]: a generic **circuit-breaker + graceful-fallback** adapter that transparently fails over from a cloud LLM (Amazon Bedrock Converse) to a deterministic local rule engine when quota/credentials are unavailable. It ships with unit tests and works with any `LLMServicePort` implementation, so other developers building MCP/Alexa+ agents can keep their sessions alive under cloud outages instead of crashing.

---

## 6. Required repository assets

| Activo | Estado | Acción |
|---|---|---|
| `LICENSE` (MIT) visible en *About* | ✅ | Confirmar en GitHub |
| `README.md` (setup/run EN) | ⚠ | Corregir refs a `.local/` y conteos de tests |
| `requirements.txt` sin secretos | ✅ | Revisar |
| `src/` (dominio/aplicación/infra) | ✅ | — |
| `alexa_skill/skill.json` | ⚠ | Cambiar `testingInstructions` a ruta **tracked**; resolver `<host>` de privacy/terms |
| `Dockerfile` + `docker-compose.yml` | ✅ | — |
| `tests/` (unit+integration) | ✅ | 208 passed |
| Simulador + `run_demo.py` | ❌ | **Mover fuera de `.local/`** (o dejar de ignorarlos) |
| Assets de ejemplo (p.ej. `photo.jpg`, `sample.png`) | ⚠ | Añadir si el vídeo usa adjuntos multimodales |
| Capturas para README | ⚠ | Adjuntar screenshots EN/ES |
| Docs (visión, checklist, guías) | ✅ | Revisar idioma EN |

**🚩 Inconsistencias a corregir (riesgo de credibilidad/elegibilidad):**
1. `README.md:63` y `README.md:306` dicen **“102 tests”** → actual **208**.
2. `DEVPOST_CHECKLIST.md:101` dice **“203 tests”** → actual **208**.
3. `README.md:118` lista `.local/` como *“scratch scripts (gitignored)”* pero el arranque y el simulador dependen de esa carpeta → mover scripts a carpeta **tracked** (p.ej. `scripts/`).
4. `README.md:10` afirma **“100% test coverage”** → evitar claims no verificados (usar “comprehensive offline suite, 208 tests”).
5. `skill.json:25-26` placeholders `https://<host>/privacy` y `/terms`.

---

## 7. Required demo video structure

**Requisitos:** <3:00, **EN**, público (YouTube/Vimeo), muestra el proyecto en la **plataforma** y la **tecnología requerida en acción**, sin trademarks/música con copyright.

| Tiempo | Escena | Qué mostrar | Criterio cubierto |
|---|---|---|---|
| 0:00–0:20 | **Problema + hook** | “Alexa is single-turn and reactive; EchoMind gives her memory of the home.” | Potential Impact |
| 0:20–0:45 | **Visión** | Diagrama `Alexa+ → EchoMind → Memoria → Contexto → Conversación → Acción` | Quality of the Idea |
| 0:45–1:30 | **MCP en acción** (núcleo Alexa+) | Terminal: `initialize` → `tools/list` (8 tools) → `tools/call analyze_ambient_stream`; mostrar `Mcp-Session-Id` y SSE | Tech Implementation |
| 1:30–2:15 | **Dashboard demo** | Seed memoria → ask **EN** (“What happened today?”) → ask **ES** (“¿Cuándo viste la reja abierta?”) → **alerta proactiva** con TTS | Design / Impact |
| 2:15–2:40 | **AWS + resiliencia** | Mencionar Bedrock Converse/Nova y QFP; `/metrics` (tool calls, fallbacks, latencias) | AWS Builder / Tech |
| 2:40–2:55 | **Cierre** | Repo MIT + instrucciones; “built for Alexa+ with MCP × Bedrock” | — |

**Checklist de grabación:**
- [ ] 1920×1080, audio claro, sin música con copyright ni logos de terceros.
- [ ] Mostrar el **MCP server** (no solo el dashboard) → evita verlo como “app de cámara/CCTV”.
- [ ] Bilingüe pero comprensible: EN en narración; usar una **voz EN** o subtítulos para el tramo ES.
- [ ] Título sugerido: `EchoMind — Cognitive Memory Agent for Alexa+ | MCP × AWS Bedrock`.

---

## 8. Required testing instructions

> Deben estar **en inglés**, en el README, con rutas **tracked** (no `.local/`). El repo público no requiere credenciales; si fuera privado, añadir credenciales de login aquí.

**TEXTO PARA DEVPOST (EN):**

```powershell
# 0. Requirements: Python 3.11+, Windows/macOS/Linux. No AWS account required (QFP handles it).

# 1. Clone
git clone https://github.com/badolgm/echomind-mcp-alexa
cd echomind-mcp-alexa

# 2. Virtualenv + deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # macOS/Linux
pip install -r requirements.txt

# 3. Offline test suite + quality gates (no network, no AWS)
pytest -q                            # 208 passed
flake8 src tests                     # 0 violations
black --check src tests --line-length 88

# 4. Run the MCP Streamable HTTP server
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
# Dashboard (demo console): http://localhost:8000/dashboard

# 5. Drive it like Alexa+ (MCP client simulator)
python scripts/alexa_mcp_simulator.py --server http://localhost:8000 --interactive
#   list / call analyze_ambient_stream '{"location":"kitchen","observation":"smoke"}' / session / quit

# 6. One-command end-to-end demo (boots server, runs scenarios, prints /metrics)
python scripts/run_demo.py
```

**TEXTO PARA DEVPOST (EN) — Testing access:**
> The repository is public and MIT-licensed; no login or credentials are required. AWS is optional: without credentials the server runs fully via the Quota Fallback Protocol. To evaluate with Bedrock, provide standard AWS credentials (env vars or IAM role) and set `ECHOMIND_BEDROCK_REGION`/`ECHOMIND_BEDROCK_MODEL_ID`.

**Checklist testing:**
- [ ] Rutas apuntan a `scripts/…` **tracked** (§6).
- [ ] Comandos verificados en Windows PowerShell y POSIX.
- [ ] Conteo de tests correcto (208).
- [ ] Sin secretos; `.env` no requerido.

---

## 9. Explicación de “significant updates during hackathon”

**Requisito:** si el proyecto existía antes del **31 AGO 2026**, explicar **cómo** se actualizó significativamente y **demostrar** las features durante la ventana.

> ⚠️ **Pendiente de verificar contra `git log`** (fechas reales de commits). Borrador basado en el roadmap por fases:
> - **Phase 1–3** (dominio, tools multimodales, sesiones/SSE/simulador) — base previa.
> - **Phase 4–5** (Ambient Awareness + QFP; skill manifest, `/metrics`, Docker, demo runner) — **dentro de la ventana**.
> - **Phase 6–8** (Control Center dashboard; integración Vivotek en vivo; watchdog autónomo + alertas proactivas y TTS) — **dentro de la ventana**.
> - **Actualizaciones recientes** (memoria `memory_*` tools + reclasificador de intención; bilingüismo determinista; fixes de voz/UX) — **dentro de la ventana**.

**TEXTO PARA DEVPOST (EN) — Significant updates:**
> EchoMind's project skeleton (pure domain core, MCP Streamable HTTP transport, and the initial tool catalog) predated the Submission Period. During the Hackathon window (Aug 31 – Oct 23, 2026) I significantly extended it with: (1) the **Autonomous Ambient Watchdog** (`AmbientWatchService`) with explainable risk verdicts, proactive `camera_alert` events and bilingual voice announcements; (2) the **agentic memory layer** (`memory_last_seen`, `memory_search`, `memory_summary`, `memory_converse`) with an intent classifier; (3) the **EchoMind MCP Control Center** dashboard (SSE tool log, live metrics, AI detection overlay); (4) **live Vivotek IP-camera integration** with a graceful fallback frame; (5) the **Quota Fallback Protocol** (Bedrock → deterministic local rule engine); (6) the **Alexa+ Agent Skill manifest** (`alexa_skill/skill.json`) targeting MCP spec `2025-11-25`; and (7) the offline quality-gate suite. The demo video shows these updates working.

---

## 10. Resumen de acciones antes del 23 OCT

| # | Acción | Bloquea |
|---|---|---|
| 1 | Mover simulador/`run_demo` fuera de `.local/` y arreglar refs (`skill.json`, README) | Stage One (viability) |
| 2 | Corregir conteos de tests (102/203 → 208) y claims | Credibilidad |
| 3 | Grabar/subir vídeo <3 min EN mostrando MCP en acción | Obligatorio |
| 4 | Pegar Product Feedback (§2) | Obligatorio |
| 5 | Friction Log (§3) | Bonus +10% |
| 6 | Feature Requests (§2.3) | Bonus |
| 7 | Declarar AWS (§4) + Kiro si aplica | AWS Builder |
| 8 | Afianzar elegibilidad Open Source con artefacto ADICIONAL (§5) | Open Source |
| 9 | Confirmar repo público/licencia o añadir 6 colaboradores | Elegibilidad dura |
| 10 | Escribir sección “significant updates” vs `git log` (§9) | Elegibilidad |
| 11 | Revisar vídeo: sin trademarks/música con copyright | Regla dura |

**No** se modifica código en este entregable. Sin commits, sin push.
