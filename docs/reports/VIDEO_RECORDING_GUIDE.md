# VIDEO_RECORDING_GUIDE.md — Grabación paso a paso de la demo

> **Protagonista: ALEXA+.** Cámara y dashboard son **medios** (sensor / consola). Guion alineado con
> `DEMO_SCRIPT_V1.md` y `PROJECT_VISION_ALIGNMENT.md`.
>
> **Narrativa oficial:** `Alexa+ → EchoMind (agente cognitivo) → Memoria → Contexto → Conversación
> → Acción`. La Vivotek y Android **no** son el producto: son sensores del ecosistema de Alexa.

Run sheet operativo para grabar el vídeo de demo (EN, < 3:00). Alineado con
`DEMO_SCRIPT_V1.md`. Sigue las órdenes en **orden**; cada paso dice **qué mostrar**, **qué decir**,
**qué responder** y **cuándo cambiar de pantalla**.

---

## 0. Pre-grabación (checklist de 5 minutos)

**Hardware/software**
- [ ] Cerrar Slack/Teams/Discord y notificaciones de Windows (**No molestar**).
- [ ] Resolución 1920×1080; navegador **Chrome** maximizado; zoom **110 %**.
- [ ] Micrófono de buena calidad; grabador listo (OBS / Game Bar `Win+G` / Loom).
- [ ] Fondo sin distracciones; barra de marcadores limpia.

**Servidor**
```powershell
$env:CAMERA = "simulation"
.\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
```
- [ ] `GET http://localhost:8000/health` → `{"status":"ok",...}`.
- [ ] Abrir `http://localhost:8000/` y dejar el dashboard cargado.

**Ensayo (sin grabar)**
- [ ] Pulsar **Seed Demo Memory** y confirmar `Memory seeded (5 events)`.
- [ ] Preguntar `What happened today?` y `Critical events?` → confirmar respuesta EN.
- [ ] Cambiar `LANG: EN → LANG: ES` y preguntar `¿Cuándo viste la reja abierta?` → confirmar ES.
- [ ] Comprobar que el navegador **puede** sintetizar voz (TTS) y que el micrófono funciona.
- [ ] **Dejar el dashboard en estado limpio**: recargar `http://localhost:8000/` para partir de
      cero (sin captions previos).

> Si el motion/`camera_alert` depende de hardware, usa `CAMERA=simulation` y **no** dependas de la
> alerta real: para el WOW proactivo usa el panel **AI Watchdog** y describe el comportamiento.
> Si tienes cámara física o teléfono, ver la **Sección Android** más abajo.

---

## 1. Grabación — toma única (2:30–2:50)

Empieza a grabar **2 segundos antes** de hablar. Habla despacio y marca los silencios con calma.

### Toma 1 — Hook (0:00–0:12)
- **Pantalla:** dashboard completo, quieto (hero + panel de sensores + métricas).
- **Decir:** *"Smart homes today only answer when you talk. EchoMind gives Alexa+ a memory — so
  she can observe, remember, understand, converse and respond."*

### Toma 2 — Arquitectura (0:12–0:30) *(opcional, recortable)*
- **Cambio de pantalla:** abre una pestaña/slide con el pipeline:
  `CameraFrameSource → AmbientWatchService → EventHub → MemoryBridge → VectorMemoryService →
  MemoryIntentClassifier → MemoryConverse → Alexa MCP`.
- **Decir:** *"Alexa's senses feed a memory: a visual sensor streams into an autonomous watchdog;
  events flow through a memory bridge; and Alexa recalls everything — all over the Model Context
  Protocol, with a local fallback engine that keeps it running 24/7."*
- **Recalcar:** la cámara es el **primer eslabón** (sensor); el valor está en la **memoria y la
  conversación**.
- **Volver:** regresa a `localhost:8000/`.

### Toma 3 — DemoSeed (0:30–1:00)
- **Cambio de pantalla:** otra vez el dashboard.
- **Mostrar:** scroll hasta el **Voice Dock** (botón 🌱 Seed Demo Memory, `LANG: EN`, mic, input, Ask).
- **Decir:** *"This is the EchoMind Control Center — the console where Alexa's memory lives. First,
  I load days of home history in one click."*
- **Clic:** **🌱 Seed Demo Memory**.
- **Responder/confirmar (lo que aparece):** `Memory seeded (5 events)`.

### Toma 4 — Pregunta EN (1:00–1:30)
- **Mostrar:** caja de texto del Voice Dock.
- **Decir:** *"Now I just ask, in plain English."*
- **Escribir:** `What happened today?` → **Clic: Ask**.
- **Esperar** a que el caption se rellene. **Dejar 2-3 s para que se lea.**
- **Respuesta esperada:** *"During the last 24 hours I have observed: 1 time the open gate,
  1 time motion, 1 time a fall, 1 time a person, 1 time an elderly person. The last detection of a
  fall occurred 3 hours ago at living…"*
- **Decir (encima):** *"It recalls the exact history — no cloud round-trip, no model needed."*

### Toma 5 — Eventos críticos (1:30–1:55)
- **Escribir:** `Critical events?` → **Ask**.
- **Respuesta esperada:** *"Recent critical events: 3 hours ago at living: FALL DETECTED,
  PERSON (CRITICAL)."*
- **Decir:** *"What about the dangerous moments? Right there."*

### Toma 6 — Salto a español (WOW bilingüe, 1:55–2:15)
- **Cambio de estado:** **Clic: `LANG: EN`** → cambia a **`LANG: ES`**.
- **Escribir:** `¿Cuándo viste la reja abierta?` → **Ask**.
- **Decir:** *"And it's fully bilingual — same memory, Spanish in, Spanish out."*
- **Respuesta esperada:** *"La última detección de la reja abierta ocurrió hace 22 horas en
  cam-01."*
- **Subrayar:** se escucha el **TTS en español** al responder.

> **No preguntar "yesterday"** (hoy/ayer = misma ventana de 24 h).

### Toma 7 — Proactividad de Alexa (2:15–2:45)
- **Cambio de pantalla:** panel del **sentido visual de Alexa** (AI Watchdog) — `AI Risk · Temp ·
  Smoke · Gate · Motion`.
- **Decir:** *"And Alexa is proactive: she notices real motion through her vision sense and speaks
  up on her own — no question asked."*
- **Mostrar:** un `camera_alert` (caja de detección + ALERT naranja) si está disponible; si no,
  señala la fila de watchdog reaccionando. **Enmarca el evento como Alexa reaccionando**, no como
  "una cámara mostrando cosas".

### Toma 8 — Cierre (2:45–2:50)
- **Cambio de pantalla:** dashboard quieto.
- **Decir:** *"EchoMind turns Alexa+ from a responder into a guardian with memory — she observes,
  remembers, understands, converses and responds, in any language, even without the cloud. Build.
  Ship. Shape."*
- **Parar grabación.**

---

## 2. Cuándo mostrar Android (opcional — 10-15 s)

Android es un **sentido visual alternativo de Alexa** (fuente PHONE), no un protagonista. Solo si
tienes **un Android con IP Webcam** y decides incluir la fuente PHONE:

1. **Preparación:** en el teléfono, app **IP Webcam** → *Start server*; anota la URL
   (ej. `http://192.168.x.x:8080/video`).
2. **Configuración (antes de grabar):**
   ```powershell
   $env:CAMERA = "phone"
   $env:PHONE_CAM_URL = "http://192.168.x.x:8080/shot.jpg"
   .\.venv\Scripts\python.exe -m uvicorn src.main:app --port 8000
   ```
3. **En cámara:** en el selector de fuente del dashboard, elige la fuente **PHONE** (badge
   `PHONE LIVE`).
4. **Mostrar:** el teléfono apuntando a la escena **y** su feed en el dashboard al mismo tiempo.
5. **Decir:** *"Alexa gained another eye — your old phone as a vision sensor, no proprietary
   hardware."*

**Momento del montaje:** inserta este clip **entre la Toma 7 y la Toma 8** (antes del cierre). Si
no hay Android físico, **omítelo**: `CAMERA=simulation` ya es válido para el vídeo.

---

## 3. Grabación de pantalla — órdenes técnicas

- **Ventana de captura:** solo la ventana de Chrome (no todo el escritorio) → evita fugas de datos.
- **Cursor:** visible, movimientos lentos; los clics se ven claros.
- **Pausas:** tras cada respuesta, **2-3 s** de lectura antes de la siguiente acción.
- **Sin cortes en mitad de una petición** (el caption tarda < 1 s; no corras).
- **Audio:** prueba 10 s y escúchate antes de la toma larga.

---

## 4. Post-grabación (edición de 10 minutos)

- [ ] Recortar el inicio (antes del hook) y la cola final.
- [ ] Duración final **< 3:00** (objetivo 2:30–2:50).
- [ ] Subir volumen de la narración; **no** silenciar el TTS español (es parte del WOW).
- [ ] Subtítulos EN opcionales (auto-generar y corregir).
- [ ] Exportar **1080p**, subir a YouTube/Vimeo → **público/no listado**.
- [ ] Pegar el enlace en Devpost (ver `DEVPOST_CHECKLIST.md` §1).

---

## 5. Si algo falla durante la toma

| Síntoma | Acción |
| --- | --- |
| Caption vacío tras **Ask** | Verifica server arriba y `POST /api/converse` en DevTools; repite la toma. |
| No hay voz ES (TTS) | Revisa volumen/permiso de audio del navegador; el texto sigue siendo válido. |
| Micrófono no responde | Usa el **input de texto** (el flujo se ve igual); micrófono es opcional. |
| Sin `camera_alert` en vivo | Muestra el panel **AI Watchdog** y describe la proactividad. |
| Dashboard lento | Recarga `localhost:8000/`; evita Firefox. |

---

## 6. Reset rápido entre tomas

```powershell
# En el dashboard: recargar pestaña (Ctrl+F5) para limpiar captions
# Volver a sembrar: clic "🌱 Seed Demo Memory"
```
