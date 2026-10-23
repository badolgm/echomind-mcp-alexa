# DEVPOST_CHECKLIST.md — Entrega en Devpost

> **Protagonista: ALEXA+.** EchoMind no es una cámara ni un dashboard: es **Alexa+ con memoria**
> (observa → recuerda → comprende → conversa → responde). La Vivotek y Android **no** son el
> producto. **Narrativa oficial:** `Alexa+ → EchoMind (agente cognitivo) → Memoria → Contexto →
> Conversación → Acción`. Ver `PROJECT_VISION_ALIGNMENT.md`.

Estado de cada bloque con casillas accionables. Marca solo lo verificado. Referencias:
`DEMO_SCRIPT_V1.md`, `VIDEO_RECORDING_GUIDE.md`, `AI_BOOT_MASTER.md`, `PROJECT_VISION_ALIGNMENT.md`.

---

## 1. Vídeo

- [ ] Duración **< 3:00** (objetivo 2:30–2:50). Ver `DEMO_SCRIPT_V1.md`.
- [ ] Idioma: **inglés** (subtítulos EN opcionales, recomendados).
- [ ] Audio claro; narración sin muletillas; se escucha el TTS ES en el tramo bilingüe.
- [ ] Se ve el flujo completo: **Seed → pregunta EN → pregunta ES → alerta proactiva**.
- [ ] Subido a **YouTube/Vimeo** como **público** o "no listado" con enlace válido.
- [ ] Título del vídeo: `EchoMind — Cognitive Memory Agent for Alexa+ | MCP × AWS Bedrock`.
- [ ] Enlace del vídeo pegado en Devpost.

## 2. Repositorio

- [ ] Repo público: `https://github.com/badolgm/echomind-mcp-alexa`.
- [ ] ⚠️ **El trabajo está solo en local** (rama `checkpoint/day1-mobile-memory`, HEAD `093a8ad`,
      **sin push**). → Decidir: **push a `main`** o abrir **PR** antes de la entrega.
- [ ] `README.md` actualizado (stack, arranque, gates, dashboard).
- [ ] `LICENSE` presente (MIT © 2026 Badolgm).
- [ ] `requirements.txt` sin secretos; `.gitignore` cubre `.venv/`, `.local/`, `__pycache__/`.
- [ ] Enlace del repo pegado en Devpost.

## 3. Descripción (texto de la submission)

- [ ] **Elevator pitch** (1-2 frases): *"EchoMind da a Alexa+ una memoria: observa, recuerda,
      comprende, conversa y responde, en inglés y español, incluso sin la nube. La cámara es solo
      uno de sus sentidos."*
- [ ] Dejar claro que **la protagonista es Alexa** (no la cámara ni el dashboard).
- [ ] **Problema**: los asistentes son reactivos y de un solo turno; nadie vigila el hogar.
- [ ] **Solución**: ambient awareness con 4 pilares (safety, multimodal, memoria, productividad).
- [ ] **Cómo se construyó**: enumerar los 8 tools, Hexagonal+DDD, MCP Streamable HTTP.
- [ ] **Cómo se usa**: pasos de arranque (env `CAMERA=simulation`, uvicorn, abrir dashboard).
- [ ] **Retos superados**: QFP (fallback sin credenciales), falsos positivos de movimiento
      (EXIF de IP Webcam), bilingüismo determinista.
- [ ] **Tecnologías**: Python 3.11, FastAPI, MCP, AWS Bedrock (Converse), boto3, httpx, Web Speech API.
- [ ] Wording honesto: **no** afirmar Qdrant/CLIP/Whisper/Digital Twin (no implementados).

## 4. Capturas (screenshots)

Tomar/adjuntar al menos:
- [ ] **Dashboard completo** (hero + panel de sensores + métricas).
- [ ] **Voice Dock con `Memory seeded (5 events)`**.
- [ ] **Respuesta EN** (`What happened today?`) en el caption.
- [ ] **Respuesta ES** (`¿Cuándo viste la reja abierta?`) en el caption.
- [ ] **Panel AI Watchdog / `camera_alert`** (riesgo + detecciones) — como **sentido visual de Alexa**.
- [ ] (Opcional) **Móvil como sentido visual alternativo de Alexa** (fuente PHONE).

> Capturas de la validación local disponibles en
> `C:\Users\BagmDev\AppData\Local\Temp\opencode\shots\` (01-dashboard-initial, 03-seeded,
> 04-converse-en, 05-converse-es, 06-mic-stt, 07-tts).

## 5. Arquitectura

- [ ] Dejar claro en el diagrama que **Alexa+ es el agente principal**; cámara/dashboard son sensor
      y consola.
- [ ] Diagrama hexagonal (de `AI_BOOT_MASTER.md` §3 / `README.md` / `MASTERDOC.md`).
- [ ] Diagrama del pipeline: `CameraFrameSource (sensor) → AmbientWatchService → EventHub →
      MemoryBridge → VectorMemoryService → MemoryIntentClassifier → MemoryConverse → Alexa MCP`.
- [ ] Tabla de 8 tools del catálogo.
- [ ] Mención a MCP Streamable HTTP (`2025-11-25`, `Mcp-Session-Id`) y `alexa_skill/skill.json`.

## 6. Friction Logs

- [ ] **Friction 1 — Quota/credenciales AWS**: Bedrock throttling/ausencia de credenciales
      rompía la sesión → se diseñó el **QFP** (`ResilientLLMAdapter` → `RuleBasedLLMAdapter`).
      Verificado en vivo sin credenciales.
- [ ] **Friction 2 — Falsos positivos de movimiento**: `frame_delta_ratio` sobre JPEG completos
      se disparaba por el **EXIF/timestamp** de IP Webcam → se recorta hasta el marcador **SOS**
      (`_image_payload`) y se sube el umbral a **0.20**. Evidencia: delta EXIF-only = 0.0.
- [ ] **Friction 3 — Navegador y cámara física**: el FD8367 usa MJPEG/ActiveX y CORS bloquea el
      navegador → proxy inverso `httpx` en `/api/cam/vivotek/snapshot` + frame de fallback.
- [ ] **Friction 4 — Bilingüismo sin LLM**: el reconocimiento de idioma debía ser determinista →
      hints ES/EN + parámetro `lang` explícito en `/api/converse`.
- [ ] **Friction 5 — Error JS en `renderBoxes()`**: limpiar `innerHTML` destruía el nodo de alerta
      y rompía listeners → re-insertar `alertEl` + null-guards; verificado `PAGE_ERRORS: []`.
- [ ] **Friction 6 — Integrar un móvil como cámara**: se añadió `HttpPhoneCameraAdapter`
      (`CAMERA=phone`) para reutilizar un Android con IP Webcam.

## 7. Requisitos Alexa+

- [ ] **Pista Alexa+**: servidor **MCP Streamable HTTP** operativo (`/mcp`, spec `2025-11-25`).
- [ ] `alexa_skill/skill.json` con:
  - [ ] `apis.mcp` `type: agent`, `protocol: streamable-http`, versión `2025-11-25`.
  - [ ] Sesión por header `Mcp-Session-Id`, idle timeout, stream server-initiated, keep-alive SSE.
  - [ ] `capabilities.tools`, `notifications: ["initialized"]`, JSON-RPC 2.0.
  - [ ] Permisos de cámara/media (`camera:view`, `camera:capture`, `mediaStreaming`, `audioCapture`, `notification`).
  - [ ] `examplePhrases` (3 utterances de ejemplo).
  - [ ] `fallbackProtocol` (`onQuotaExceeded: local-rule-engine`, `transparent: true`, `24-7`).
- [ ] **Minidesafío AWS Builder**: visión multimodal vía **Bedrock Converse** + **Graceful
      Fallback** (QFP).
- [ ] **Minidesafío Open Source**: repo público, hexagonal/DDD, **203 tests** offline, flake8 0,
      black limpio, documentación completa.

---

## Checklist final de envío (Devpost)

- [ ] Título, tagline y descripción completos.
- [ ] Vídeo (enlace público/no listado) OK.
- [ ] Repo (enlace público) OK.
- [ ] Capturas subidas.
- [ ] Tecnologías/tracks seleccionados (Alexa+, AWS Builder, Open Source).
- [ ] Flujo de submission de Devpost **guardado y enviado**.
