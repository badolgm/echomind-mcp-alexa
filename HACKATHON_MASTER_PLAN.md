# HACKATHON MASTER PLAN — EchoMind MCP Alexa

> Documento ejecutivo del estado real del sistema y el plan a 5 días.
> Auditoría verificada contra el working tree en fecha: 10-oct-2026.
> Sin código nuevo, sin commits, sin Docker en este sprint.

---

## FASE 1 — AUDITORÍA REAL

### 1.1 Estado de verificación

| Verificación | Resultado |
|---|---|
| Suite de tests | **175/175 verdes** (unidad + integración) |
| flake8 | **0 errores** |
| black (line-length 88) | **limpio** (56 archivos) |
| `git` | **7 commits** históricos; **la memoria V1–V3 y el watchdog/sensor/dashboard NO están commiteados** |

### 1.2 Componentes terminados (funcionan hoy)

| Componente | Evidencia en repo | Notas de auditoría |
|---|---|---|
| Visión | `vivotek_adapter.py`: snapshot async, cache TTL 1.5s, frame de fallback determinista, `record_detections` | Solo MJPEG/Vivotek; sin análisis en edge, el razonamiento visual lo hace Bedrock |
| Watchdog | `ambient_watch_service.py`: loop 0.5s, `motion` (delta 4096 muestras), reja/puerta/mascota/humo/temperatura | Emite `camera_alert` HIGH/CRITICAL solo con triggers visuales (GATE_OPEN/PET_ESCAPING/MOTION) |
| `model_analysis` | Presente en evento `camera_alert` (announcement+recomendación) y en reporte del resolver | Alimenta narrativa y memoria |
| SSE | `/dashboard/events` (EventHub → `asyncio.Queue` por suscriptor) | No bloquea al publicador; bridge y dashboard conviven |
| Dashboard | `static/dashboard.html`: refresh 250ms, alertas, selector de cámara, catálogo de dispositivos Alexa, `speakAlexa` (speechSynthesis, cooldown 10s) | **TTS en navegador; SIN STT/Whisper** |
| MCP | Streamable HTTP 2025-11-25, 8 herramientas, sesiones persistentes | Contrato consumible por Alexa+ vía skill manifest |
| Razón (fallback) | `ResilientLLMAdapter` (Bedrock Nova Micro) + `RuleBasedLLMAdapter` + Quota Fallback Protocol | El sensor-de-riesgo es determinista; el texto lo da el LLM o la regla |
| **Memoria** | `memory_service.py`, `memory_bridge.py`, `memory_intent.py`, `memory_resolvers.py`, 3 tools V2 + `memory_converse` | Sprint V1–V3 completos (32 tests) |
| Telemetría | `/metrics`: latencia por método, tool calls, estado fallback | Paneles útiles para el jurado |

### 1.3 Componentes incompletos (a medio camino)

| Componente | Qué falta | Por qué no está terminado |
|---|---|---|
| Integración `compose()` + lifespan | MemoryBridge arranca con el app **real**, pero los tests `ASGITransport` no ejecutan lifespan → el wiring bridge↔watcher solo está cubierto por unit tests, no E2E | Limitación conocida del transporte de tests |
| Persistencia de memoria | `VectorMemoryService` es **en proceso**; un reinicio borra la memoria | Existe el contrato `MemoryVectorStorePort` (Qdrant) sin implementar |
| `compose()` offline | El `HealthCheck`/MCP funcionan sin AWS, pero basta: no hay "modo demo sembrado" | Sembrar memoria + escenarios es trabajo de demo, no de código |
| Commit/versionado del trabajo de memoria | TODO V1–V3 está sin commitear (`git status` lo confirma) | Riesgo real de tiempo |

### 1.4 Componentes experimentales / no iniciados

| Componente | Estado real |
|---|---|
| Voz continua (bucle completo STT→Razonar→TTS) | **No existe** en repo; solo TTS de navegador. Whisper excluido |
| Cámara desde celular | **No existe**. Dependencia única de hardware Vivotek (IP 192.168.40.10) |
| Aprendizaje de objetos | **No existe** (no hay catálogo incremental ni embeddings de objetos) |
| Consulta web | **No existe** (sin herramientas de websearch/URL-fetch en el catálogo) |
| Investigación autónoma | **No existe** |
| Qdrant Edge | Solo el **contrato** (`MemoryVectorStorePort`); sin adaptador |
| CLIP | **No existe** (embeddings actuales son hash-term-freq, funcionan para vocabulario fijo) |
| Whisper | **No existe** (excluido por decisión) |

### 1.5 Riesgos técnicos (honestos)

1. **La cámara es el punto único de fallo de la demo.** Si la Vivotek no está en el venue, `get_frame()` devuelve el frame de fallback determinista → el delta de movimiento es **cero**, y la demo de "visión" muere. Esto es **crítico**.
2. **Latencia de Bedrock en vivo.** Si el jurado sigue con Amazon, en la demo la red/AWS puede tardar; el Quota Fallback Protocol cubre caída, pero no la latencia bruta. Mitigación: el watchdog da respuesta en <1s sin LLM; el texto LLM puede tardar 2–5s.
3. **Dashboard depende de Tailwind CSS vía CDN.** Sin internet en el venue, la UI queda sin estilo. Riesgo medio, mitigable (bundlear CSS).
4. **Trabajo sin commitear de memoria.** Si se pierde el working tree, se pierde el diferenciador del proyecto.
5. **Lifespan real ≠ lifespan en tests.** El wiring de bridge/memoria/watcher no se ejecuta en la suite hasta uvicorn real. Riesgo de "funciona en unit, falla en vivo".
6. **Latencia de casos múltiples de memoria**: embeddings hash (sha256 por token) con 2000 records = nanosegundos; no es riesgo. Pero `MemoryError` cuando se llena: el puente se traga el error (testeado).

### 1.6 Riesgos de tiempo

- **Feature-creep:** la tentación de añadir CLIP/Qdrant/objetos los días 2–3 destruye el ensayo del día 4.
- **Ensayo subestimado:** la demo en vivo requiere guion, data sembrada, y 3+ ensayos completos; no es "un commit más".
- **Hardware/venue:** cámara real + red + elevación (Alexa) son amenazas externas no controlables.

---

## FASE 2 — ANÁLISIS DE IMPACTO (P0 a P3)

Clasificación para maximizar probabilidad de ganar (P0 = imprescindible para la demo, P3 = después del hackathon).

| Funcionalidad | Prioridad | Esfuerzo | Impacto demo | Justificación |
|---|---|---|---|---|
| **Memoria histórica** | **P0** | ✔ hecho | **Crítico** | Es el diferenciador real que ya está terminado (V1–V3). |
| **Cámara desde celular** | **P0** | 0.5–1 día | **Crítico** | Elimina el punto único de fallo (#1 técnico). Con el celular del propio stand se demuestra "visión en vivo" sin depender de la Vivotek. |
| **Hardening/seed + E2E de demo** | **P0** | 1 día | **Alto** | Memoria "sembrada" (datos plausibles de ayer/antier) para que "¿recuerdas de hoy?" y "¿cuándo fue la última vez?" funcionen SIEMPRE, aunque no haya eventos en vivo. |
| **Voz continua** | **P1** | 1–2 días | Alto | El jurado espera interacción hablada. Sin dispositivo Alexa físico real, el bucle es: teclado→voz del dashboard. Depende de hardware. |
| **Consulta web ("¿Qué es esto?")** | **P1** | 1–1.5 días | Medio-Alto | Una solo herramienta `web_lookup` + grounding con frame = "sorpresa" que el jurado no espera. Riesgo: NOVA micro razona pobre sobre texto web desconocido. ROI medio. |
| **Aprendizaje de objetos** | **P2** | 2–3 días | Medio | Name-a-new-object: requiere contador de apariciones + memoria de labels nuevos. Cute, no diferente sobre la memoria que ya está. |
| **Investigación autónoma** | **P2** | 3+ días | Medio | Orquestar "buscar→leer→resumir→hablar" es multi-llamada; NOVA micro no es agente fuerte. Riesgo alto de quedar "a medias". |
| **Qdrant Edge** | **P2** | 1–2 días | Bajo-Medio | Aporta persistencia y "functional presence offline"; el demo de 10 min no lo nota. Mejor previo al corte, después de cámara y seed. |
| **CLIP** | **P2/P3** | 2–3 días | Medio | Mejora `memory_search` (semántica real vs hash-tf). Riesgo: peso del modelo, latencia en el stand, y no cambia el guion del jurado. |
| **Whisper** | **P3** | 2+ días | Bajo con hardware | STT local; sin micrófono/device físico el ROI es casi nulo. |

**Conclusión de impacto:** la demo gana con **memoria + visión en vivo por celular + voz + un giro inesperado (web/objeto)** — NO con 8 features.

---

## FASE 3 — PLAN DE 5 DÍAS

> Regla dura: **congelación de features el día 4 a las 18:00**. Los días 4–5 son solo ensayo, pulido y guion.

### Día 1 — Estabilizar y asegurar el trabajo
- **Objetivo:** dejar el repo en estado "demo-safe": todo commiteado, gates verdes, y cerrar el riesgo #1 de cámara.
- **Entregables:**
  1. `git commit` de memoria V1–V3 + watchdog/sensor/dashboard + main (acción de equipo, no la dejo yo).
  2. **Cámara desde celular**: endpoint `POST /api/cam/phone/snapshot` (sube un JPEG/base64 del celular al stand vía una página `phone.html` que captura `getUserMedia`) + `PhoneCameraAdapter` que implementa `CameraFrameSource` y alimenta el watchdog y `_auto_attach_frame`. Selector fuente en el dashboard.
  3. Bundle CSS local (quitar dependencia de CDN de Tailwind).
- **Pruebas:** unit: `PhoneCameraAdapter` (get_frame ok/fallback, formatos), ruta de subida; integración: `compose()` con phone en lugar de Vivotek.
- **Criterio de aceptación:** con el frame del celular, `watchdog.tick()` detecta movimiento real (delta > 0.10) y publica `camera_alert`; sin celular, fallback determinista y **dashboard sigue vivo** con badge "phone".

### Día 2 — Memoria sembrada + modo demo + investigación web
- **Objetivo:** garantizar que el demo de memoria funcione incluso sin eventos en vivo, y añadir el "giro" de consulta.
- **Entregables:**
  1. **`demo_seed`**: utilitario que siembra `MemoryRecord` (personas/abuelos/mascotas/reja 24h–7d con horas plausibles) para "¿cuándo fue la última vez?" y "¿qué recuerdas de hoy?" → **siempre hay respuesta**.
  2. **Tool `web_lookup`** (categoría KNOWLEDGE): argumento `query`; fetch de 1–2 fuentes (Wikipedia/DuckDuckGo-lite via httpx, timeout 2s) y respuesta corta. No se enrosca en crawling.
  3. Script E2E `demo_script.py` en `.local/` que orquesta: teléfono→alerta→pregunta memoria→respuesta.
- **Pruebas:** unidad: seed produce respuestas last_seen/summary/count; `web_lookup` con servidor fake (httpx MockTransport); integración: `memory_converse` responde desde seed.
- **Criterio de aceptación:** `memory_summary` con seed responde al menos a 3 de las 5 preguntas del guion sin LLM; `web_lookup` responde < 3s.

### Día 3 — Voz continua + respuestas más naturales
- **Objetivo:** cerrar el bucle conversacional mostrable: entrada (teclado o Alexa simulada) → herramienta → TTS en dashboard con pausa/barge-in.
- **Entregables:**
  1. Bucle de "conversación" en `dashboard.html`: campo de voz+texto que llama `memory_converse`/`analyze_ambient_stream` y **habla la respuesta** (speechSynthesis, `cancel()` antes de hablar, cooldown 10s ya existente).
  2. Pulido de narrativas de `memory_converse` (más cortas, tono Alexa): repasar 3–4 casos de prueba del jurado.
  3. **Offline mode explícito**: un interruptor en el stand que fuerza `RuleBasedLLMAdapter` para demostrar el Quota Fallback Protocol en vivo (corte de red/Bedrock).
- **Pruebas:** tests de narrativa (frases exactas en los 6 intents de `memory_converse`); test del interruptor offline (resolver devuelve sí aunque Bedrock devuelva 429 simulado).
- **Criterio de aceptación:** del stand: escribir o dictar "¿hubo eventos críticos hoy?", el dashboard habla la respuesta ≤ 2s.

### Día 4 — Pulido, corte de features y primer ensayo completo
- **Objetivo:** congelar features, cerrar "dirty edges" y hacer **el primer ensayo completo** de la demo (10 min).
- **Entregables:**
  1. Congelar catálogo de tools (revisar descripciones para el jurado).
  2. Fix de latencia visible: spinner + "analizando…" mientras Bedrock responde; skip de doble alerta.
  3. Guion de demo escrito (ver Fase 6) y **ensayo cronometrado** con celular en mano.
- **Pruebas:** suite completa 175+verdes previa al corte; registro de tiempos por paso del guion.
- **Criterio de aceptación:** demo corre de principio a fin en un solo flujo de red/offline sin desviaciones > 60s.

### Día 5 — Ensayos, respaldo y presentación
- **Objetivo:** pulido final sin tocar código salvo bugs P0.
- **Entregables:**
  1. 3 ensayos completos (2 online, 1 forzado offline).
  2. Carpeta de respaldo del working tree (zip) + branch de backup.
  3. Congelar más: si aparece un bug P0, fix mínimo + volver a correr suite; si no, nada.
- **Pruebas:** suite completa; checklist del stand (celular cargado, Wi-Fi, DNS, video demo grabado como respaldo).
- **Criterio de aceptación:** score de ensayo ≥ 9/10 en fluidez; DEMO GRABADA como plan de contingencia.

---

## FASE 4 — ARQUITECTURA FINAL DEMO

```
ESCUCHAR        →  Dashboard / Alexa+ (TTS) o Simulador MCP → memoria_converse
      ↓
VER             →  Cámara del celular (phone_camera) o Vivotek → frame live
      ↓          └── Fallback determinista si no hay fuente
RAZONAR         →  watchdog.tick() (determinista < 1s) + Bedrock/NovaMicro (narrativa)
      ↓          └── Quota Fallback Protocol → RuleBasedLLMAdapter (offline)
RECORDAR        →  MemoryBridge (HIGH/CRITICAL) → VectorMemoryService
      ↓          └── Seed de demo: respuestas garantizadas a preguntas históricas
INVESTIGAR      →  web_lookup(query) [P1] sobre frame/contexto
      ↓
RESPONDER       →  memory_converse (sin LLM) + speakAlexa (TTS 10s-cooldown)
```

| Paso | Existe hoy | Falta (5 días) |
|---|---|---|
| Escuchar | TTS; entrada texto | Bucle voz continua (Día 3), simulador Alexa en stand |
| Ver | Vivotek | **Cámara celular (Día 1)** + selector |
| Razonar | Watchdog + Bedrock + fallback | Pulido latencia (Día 4) |
| Recordar | ✅ V1–V3 | Seed (Día 2), persistencia opcional |
| Investigar | — | `web_lookup` (Día 2) |
| Responder | ✅ memory_converse | Narrativas pulidas + offline switch (Día 3) |

---

## FASE 5 — RUTA CRÍTICA (si solo quedan 3 funcionalidades)

### 1. Cámara desde celular (P0) — impacto: ALTÍSIMO
**Justificación técnica:** el watchdog depende de `frame_delta_ratio` sobre frames distintos; con fallback determinista el delta es 0 y la demo de visión muere. Sustituir/paralelizar la fuente de frames es **el único cambio que salva la demo completa** y además es barato (≈0.5–1 día). Sin esto, cualquier cosa que se construya mañana no se podrá demostrar.

### 2. Memoria sembrada + script E2E (P0) — impacto: ALTO
La memoria es el diferenciador; que funcione en el jurado depende de que haya eventos. El seed garantiza que "¿cuándo fue la última vez que viste…?" y "¿qué recuerdas de hoy?" **siempre** respondan con datos plausibles. Es el "cono de helado" de la demo: seguro, barato, elimina el riesgo de "memoria vacía".

### 3. Voz continua en el stand (P1) — impacto: ALTO (pero con dependencia hardware)
El hackathon es de **Alexa**; el jurado espera conversar. Si no hay dispositivo físico, bucle dashboard (dictado + TTS). Si hay Alexa real: skill manifest→tools vía MCP (ya pronta). Sin esto la demo es "una web con cámaras", no "Alexa que recuerda".

**Honestidad:** el orden de rendimiento (probabilidad de ganar por día invertido) es Cámara > Seed/E2E > Voz > web_lookup > Qdrant/CLIP ≈ 0 en el margen de 5 días.

---

## FASE 6 — MODO JURADO

### 6.1 Preguntas probables del jurado y respuestas del sistema

| Pregunta jurado | Respuesta Alexa (demo) | Qué muestra el dashboard |
|---|---|---|
| "¿Qué hace tu solución?" | "Recuerdo de memoria ubicua: cada evento de cámara se vuelve un recuerdo vectorial; pregúntame qué vi o cuándo lo vi." | Flujo `camera_alert → MemoryBridge` en el log de eventos |
| "¿Y si se cae AWS/Bedrock?" | Pulsar el interruptor offline: "funciono con reglas locales; no dejo de vigilar." | badge **FALLBACK activo** en `/metrics`, latencia estable |
| "¿Y si se cae la cámara?" | "Ahora uso mi fuente de respaldo (celular), sin perder alertas." | selector de fuente + badge phone/live/fallback |
| "¿Cuándo fue la última vez que viste la reja abierta?" | "La última vez que vi la reja abierta fue ayer a las 21 h en la entrada." | línea temporal de memoria (seed + eventos reales) |
| "¿Es esto un video editado?" | Confrontar con el celular del stand en el momento: "¿ves esto? eso es lo que estoy analizando ahora." | snapshot live con timestamp + delta de movimiento |
| "¿Cómo mejoras con el tiempo?" | "Aprendo objetos; cada nuevo label queda en mi memoria; pregúntame cuántos eventos HIGH vi hoy." | contadores por label (`label_counts`) en panel |
| "¿Por qué Alexa y no otra plataforma?" | "Soy un skill MCP Streamable HTTP; Alexa+ me invoca sin tocar la nube." | session manager + skill manifest |

### 6.2 Demos más impactantes (en orden)
1. **Live surprise:** pedir al jurado acercar su cara/billete al celular del stand → "detecto una persona" en < 2s → pregunta inmediata "¿y antes?" → memoria.
2. **Resiliencia:** interrumpir la red del stand → seguir vigilando (fallback) → recuperar y explicar.
3. **Memoria histórica:** 3 preguntas seguidas con datos seed de 2 días ("¿cuántas veces viste una mascota ayer?").
4. **Giro web/objeto [P1]:** foto de un paquete → "un paquete quedó junto a la puerta" → "¿algo así lo había visto antes?" → memoria + (web_lookup para conocimiento extra).

### 6.3 Mensaje único de la demo
**"La casa que recuerda": visión + razonamiento + memoria + conversación sobre arquitectura limpia (hexágono + MCP + Quota Fallback)".** 30 segundos de intro y que el sistema hable.

---

## PLANES ALTERNATIVOS Y PROBABILIDAD REAL

> Probabilidades estimadas con esperanza y humildad: dependen de hardware, venue y jurado — no del código.

### 💼 Plan CONSERVADOR (días 1–2: commit + cámara celular + seed; 3–4: pulido; 5: ensayos)
- **Riesgo de fallo:** muy bajo. Implementa exactamente lo ya existente y garantiza que se vea.
- **Probabilidad real de ganar: ~25–30%.**
- **Debilidad:** la demo es "correcta pero sin sorpresa"; compite con equipos que mostrarán algo nuevo.

### ⚖️ Plan EQUILIBRADO (CONSERVADOR + web_lookup + voz continua + offline switch, congelación D4 18:00)
- **Riesgo de fallo:** bajo-medio (la voz depende del dispositivo de entrada).
- **Probabilidad real de ganar: ~35–45%.**
- **Ventaja:** cubre los 5 verbos de la demo (escuchar→ver→razonar→recordar→responder) 🇮y añade resiliencia visible.

### 🚀 Plan AGRESIVO (EQUILIBRADO + Qdrant/CLIP/objetos/investigación autónoma)
- **Riesgo de fallo:** alto (features a medias compiten por el tiempo de ensayo y las gates).
- **Probabilidad real de ganar: ~30–40%** (la cola de probabilidad alta sube, pero la media baja por features rotas).
- **Debilidad:** el jurado evalúa la demo en vivo, no el README; 8 features medianas pierden contra 4 excepcionales.

### Veredicto
> **El plan EQUILIBRADO tiene la mayor probabilidad real de ganar**: ataca el riesgo #1 (cámara celular), blinda el diferenciador (memoria con seed), añade un giro barato (web/objeto y offline switch), y reserva 1.5 días para **ensayar el guion**, que es lo que de verdad decide un hackatón.
>
> Regla innegociable: **congelación de features el día 4 a las 18:00** y un backup del working tree el día 1 (hoy mismo el trabajo de memoria está sin commitear).