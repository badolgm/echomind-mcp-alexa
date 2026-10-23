# DEMO_SCRIPT_V1.md — Guion de demo (< 3 minutos)

> **Protagonista: ALEXA+.** La cámara y el dashboard son **medios** (sensor / consola), nunca el
> producto. Guion alineado con `PROJECT_VISION_ALIGNMENT.md`.
>
> **Narrativa oficial:** `Alexa+ → EchoMind (agente cognitivo) → Memoria → Contexto → Conversación
> → Acción`. La Vivotek y Android **no** son el producto: son sensores del ecosistema de Alexa.
> Cadena de la demo: **OBSERVAR → RECORDAR → COMPRENDER → CONVERSAR → RESPONDER**.

**Duración objetivo:** 2:30–2:50 · **Idioma del vídeo:** inglés · **Formato:** screencast del
dashboard + (opcional) un **sensor visual** alternativo (Android).

**Preparación (fuera de cámara):**

```powershell
$env:CAMERA = "simulation"          # sin hardware; frame de test determinista
.\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
```

Abrir **Chrome** (no Firefox: el micrófono necesita `SpeechRecognition`) en
`http://localhost:8000/`. Cerrar notificaciones del SO. Zoom navegador ~110 %.

> **Respuestas esperadas** = salida real verificada del backend con los 5 registros de DemoSeed.
> Los valores relativos ("3 hours ago", "22 hours ago") dependen del momento del seed; vuelve a
> pulsar **Seed Demo Memory** justo antes de grabar para frescura exacta.

---

## Línea de tiempo

| Tiempo | Pantalla | Acción en cámara | Narración (EN) |
| --- | --- | --- | --- |
| 0:00–0:12 | Dashboard (hero) | — | "Smart homes today only answer when you talk. **EchoMind gives Alexa+ a memory** — so she can observe, remember, understand, converse and respond." |
| 0:12–0:30 | Diagrama de arquitectura (en `AI_BOOT_MASTER.md` §3 o slide) | Señalar el pipeline | "Alexa's senses feed a memory: a visual sensor streams into an autonomous watchdog, events flow through a memory bridge, and **Alexa recalls everything** — all over the **Model Context Protocol**." |
| 0:30–0:45 | Dashboard → Voice Dock | Scroll hasta el dock | "This is where **Alexa** meets her memory — the EchoMind Control Center." |
| 0:45–1:00 | Voice Dock | Clic **🌱 Seed Demo Memory** | "First, I load five days of home history in one click." → badge: `Memory seeded (5 events)` |
| 1:00–1:20 | Voice Dock → caption | Escribir **`What happened today?`** → clic **Ask** | "Now I just ask, in plain English." |
| 1:20–1:30 | Caption | (leer la respuesta) | — *(ver Respuesta 1)* |
| 1:30–1:45 | Voice Dock | Escribir **`Critical events?`** → **Ask** | "What about the dangerous moments?" |
| 1:45–1:55 | Caption | (leer) | — *(ver Respuesta 2)* |
| 1:55–2:15 | Voice Dock | Clic **LANG: EN → LANG: ES**; escribir **`¿Cuándo viste la reja abierta?`** → **Ask** | "And it's **fully bilingual** — same memory, Spanish in, Spanish out." |
| 2:15–2:30 | Caption + TTS | (escuchar voz ES) | "Alexa answers **out loud in Spanish**." |
| 2:30–2:45 | Panel AI Watchdog (sentido visual de Alexa) | Mostrar movimiento o `camera_alert` | "And **Alexa is proactive**: she notices real motion through her vision sense and speaks up on her own — no question asked." |
| 2:45–2:50 | Dashboard (cierre) | — | "EchoMind: memory for Alexa+. She observes, remembers, understands, converses and responds. **Build. Ship. Shape.**" |

> Si el tiempo aprieta, recorta 0:12–0:30. Los tramos que **no** se recortan: Seed, respuesta EN,
> salto a ES y alerta proactiva.

---

## Preguntas y respuestas esperadas (texto exacto)

### Respuesta 1 — EN `What happened today?`

> During the last 24 hours I have observed: 1 time the open gate, 1 time motion, 1 time a fall,
> 1 time a person, 1 time an elderly person. The last detection of a fall occurred **3 hours ago
> at living**. The last detection of the open gate occurred **22 hours ago at cam-01**…

### Respuesta 2 — EN `Critical events?`

> Recent critical events:
> - **3 hours ago at living: FALL DETECTED, PERSON (CRITICAL)**

### Respuesta 3 — EN `When was the gate last seen open?`

> The last detection of the open gate occurred **22 hours ago at cam-01**.

### Respuesta 4 — ES `¿Cuándo viste la reja abierta?`

> **La última detección de la reja abierta ocurrió hace 22 horas en cam-01.**

### Respuesta 5 — ES `¿Cuándo viste una persona?`

> **La última detección de una persona ocurrió hace 3 horas en living.**

### Respuesta 6 — ES `¿Qué recuerdas de hoy?`

> Durante las últimas 24 horas he observado: 1 vez la reja abierta, 1 vez movimiento, 1 vez una
> caída, 1 vez una persona, 1 vez una persona mayor…

> ⚠️ **No preguntar "yesterday"**: hoy/ayer devuelven la misma ventana de 24 h (ver riesgos).

---

## Momentos WOW (ordénalos como prioridad)

1. **Memoria sin LLM ni nube** — respuestas históricas exactas y al instante, offline, desde
   `VectorMemoryService`. *(El diferenciador técnico.)*
2. **Bilingüe real** — misma memoria, respuesta EN y ES con la misma pregunta, incluso forzando
   idioma con el botón `LANG`.
3. **Voz completa** — pregunta por micrófono y Alexa **responde en voz alta** (TTS `en-US`/`es-ES`).
4. **Proactividad de Alexa** — ante **movimiento real** (su sentido visual), **Alexa habla sin que
   nadie pregunte** (`camera_alert` → TTS). Corazón del "ambient awareness".
5. **Resiliencia 24/7 (QFP)** — mencionar que sin credenciales AWS el sistema sigue respondiendo
   con el motor de reglas local. *(Verificado en vivo.)*
6. **Un móvil como sentido extra de Alexa** — si se muestra el teléfono: "Alexa gained another
   eye — your old phone as a vision sensor".

---

## Cierre (frase final, memorizar)

> "EchoMind turns Alexa+ from a responder into a **guardian with memory** — she observes, remembers,
> understands, converses and responds, in any language, even without the cloud. Built on MCP and
> AWS Bedrock."

---

## Frases prohibidas en el vídeo

- No decir "simulation looks fake" ni disculparse por los datos sembrados.
- No prometer Qdrant/CLIP/Whisper/Digital Twin (no implementados).
- No preguntar "yesterday".
- No usar Firefox en cámara.
- No presentar la **cámara** ni el **dashboard** como protagonistas o producto: **la protagonista es Alexa**. La cámara es un sentido; el dashboard, la consola.
