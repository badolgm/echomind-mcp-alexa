# ECHOMIND_INTELLIGENT_RECALL_ROADMAP.md — Intelligent Recall Evolution

**Fecha:** 2026-10-11  
**Estado:** Análisis conceptual. Sin implementación/cambios/código.  
**Base:** rama `checkpoint/day1-mobile-memory`, **208 tests PASSED**.  
**Inspiración conceptual:** `teach/remember/recall` (sc-on-device-ai-memory), sin copiar arquitectura.

---

## 1. Estado actual (validado)

- **Memoria estructurada:** `MemoryBridge` (ingesta + episodio coalescing) + `VectorMemoryService` (last_seen, search, counts, top_events, high/critical, occurrences). 
- **Conversación:** `MemoryConverse` + `MemoryIntentClassifier` + `memory_resolvers` (MCP). 
- **Percepción:** Android (IP Webcam) + Vivotek + AmbientWatch + EventHub. 
- **UI/voz:** Dashboard + Voice Dock + TTS (mejor voz EN masculina observada). 
- **Ecosistema:** MCP (Streamable HTTP), Alexa+ narrative alineada.

**Memoria actual:** `MemoryRecord` = `{id, timestamp, location, source, detections[], risk, model_analysis}`.  
**Localización:** `location` = string (`patio`, `kitchen`, `living`, `cam-01`, etc). **No hay coordenadas (x,y,w,h), room_id, floor, map_id, ni relación cámara↔zona física.**

---

## 2. Brechas

| Brecha | Descripción | Impacto |
|---|---|---|
| **Ubicación espacial** | Solo `location` (etiqueta). Falta mapeo físico (habitación/zona/punto exacto). | "¿Dónde ocurrió la caída?" solo responde `living`/cámara, no punto en plano. |
| **Relación entre cámaras** | Vivotek (cam-01) + Android (phone) independientes. Sin contexto unificado de espacio. | No correlaciona eventos entre dispositivos/zona. |
| **Recall-centric vs intent-centric** | Routing `classify→intent→resolver` limita formas coloquiales (ej. "última hora de detección de movimiento"). | Respuestas menos naturales; dependencia a intents rígidos. |
| **Recuperación→Síntesis** | `search` devuelve listado; `last_seen/summary` usan plantillas. Falta síntesis basada en **conjunto de evidencias** (no tipo único). | "¿Qué pasó mientras estaba fuera?" difícil sin correlación temporal + síntesis. |
| **Contexto temporal compuesto** | No hay "timeline" (sucesión, antes/después, causa-efecto implícita). | No responde "hubo movimiento antes o después de...". |
| **Multilingual/voz inconsistente** | Cambio EN/ES no siempre consistente; voz ES actual vs EN masculina más natural. | UX conversacional (observado). |
| **Estado Bedrock** | "ACTIVE" visual pero requiere verificación real/honestidad. | No bloqueante demo; importante para transparencia. |

---

## 3. Visión objetivo (recall-centric)

Pasar de **clasificar pregunta → ejecutar ruta** a:

> **Understand → RecallPlan → Retrieve (deterministic) → Relate (spatial/temporal) → Synthesize (evidence-based) → Respond**

Principios:
- **Evidence-first:** toda respuesta deriva exclusivamente de `MemoryRecord` recuperados.
- **Retrieve deterministic, synthesize constrained:** memoria nunca delegada al modelo.
- **Offline-first / QFP compatible:** ruta determinista 100% si razonador no disponible.
- **Trazable:** evidencia + plan deben poder explicarse.
- **Sin plantillas rígidas por tipo:** síntesis guiada por evidencia + pregunta + contexto.

Inspiración `teach/remember/recall`:
- **Remember**: consolidar (MemoryBridge ya hace bien: episodio coalescing)
- **Recall**: recuperar + razonar sobre lo recordado (evidencia)
- **Teach**: opcional (no prioritario para demo)

---

## 4. Capacidades futuras

### 4.1 Memoria espacial

Necesario enriquecer `MemoryRecord` (sin romper existente):

| Campo (conceptual) | Tipo | Uso |
|---|---|---|
| `room_id` | `str\|None` | Habitación/zona canónica (living/kitchen/patio/corridor) |
| `device_id` | `str\|None` | Origen (vivotek/cam-01/phone) |
| `bbox`/`roi` | `tuple\|None` | (x,y,w,h) cuando disponible (detección visual) |
| `zone` | `str\|None` | Zona lógica (acceso/reja/entrada/sala) |
| `map_context` | `dict\|None` | Metadatos mínimos (futuro: plano digital twin) — **NO implementar ahora** |

**Regla:** añadir campos opcionales (backward compatible). No forzar migración.

### 4.2 Relación entre cámaras

- **Unified space model**: mapa lógico `device_id → room_id/zone` (config estático, sin GUI nueva).
- **Cross-device correlation**: al recuperar, permitir agrupar por zona (no solo por `location` string).
- **Temporal proximity**: vincular eventos cercanos (<30–60s) entre cámaras (misma zona) para explicar contexto.

### 4.3 Preguntas de localización

Casos objetivo:

- `"¿Dónde vio mi mascota?"` / `"Where was my pet last seen?"`  
  → `last_seen(PET)` + enriquecer con `room_id/device_id` + timestamp + evidencia. Síntesis natural (no "pet detected").
- `"¿Dónde ocurrió la caída?"` → último `FALL DETECTED` + ubicación + cámara + momento.
- `"¿Dónde estaba la reja abierta?"` → GATE_OPEN + contexto espacial.

### 4.4 Preguntas temporales

- `"¿Qué pasó mientras estaba fuera?"` (implícito ventana) → recuperar eventos desde última ausencia plausible / ventana razonable (24h o inferida) + **orden cronológico** + correlacionar + sintetizar resumen coherente (no lista).
- `"¿Hubo movimiento antes de la caída?"` → timeline: encontrar caída → buscar MOTION con `timestamp < fall.timestamp` y cercano (minutos) → responder con evidencia ordenada.
- `"¿Qué ocurrió entre X y Y?"` → filtrar por rango temporal + agrupar por zona/episodio.

### 4.5 Razonamiento sin perder trazabilidad

- **Plan estructurado (opcional):** `RecallPlan {intent_hint?, filters:{labels, since, until, room_id, device_id}, require_evidence:true, synthesis:'constrained'}`
- **Evidencia obligatoria:** respuesta debe basarse solo en registros devueltos. Si vacío → "No tengo registros..." (actual).
- **Constrained synthesis:** solo describir hechos (qué/cuándo/dónde/riesgo). Sin inferencias causales no soportadas.
- **Fallback determinista:** si razonador falla → ruta actual intacta.

---

## 5. Roadmap por fases

### FASE 0 — Fundamentación (preservar estado)
- **Objetivo:** consolidar base. **NO cambiar código.**
- **Acciones:** validar 208 tests, documentar estado, identificar puntos de extensión (campos opcionales en MemoryRecord, mapeo device→zona).

**Criterio:** sin regresiones, documentación clara.

### FASE 1 — Enriquecimiento espacial mínimo (conceptual)
- **Objetivo:** añadir metadatos espaciales **opcionales** sin romper API.
- **Cambios conceptuales (no implementar ahora):**
  - Extender `MemoryRecord` con `room_id/device_id/bbox/zone` (opcionales)
  - Mapeo estático `device_id → room_id` (config)
  - Mejorar `location` semántica (normalizar)
- **Compatibilidad:** 100% backward compatible. Tests existentes intactos.

**Criterio:** diseño validado, sin tocar lógica existente.

### FASE 2 — Recall unificado (evidence-first)
- **Objetivo:** introducir `recall(query, context)` determinista por defecto.
- **Idea:** unificar `last_seen/search/summary` bajo recuperación + filtros inferidos (heurística mínima, **sin regex nuevos masivos**).
- **Salida:** `{evidence: [MemoryRecord], meta:{filters, window, plan}}` → luego sintetizar con narrativas más naturales (template-light).
- **Routing:** mantener `MemoryConverse` actual como fallback.

**Criterio:** mismo comportamiento para casos existentes + camino para nuevos casos.

### FASE 3 — Relación temporal+espacial
- **Objetivo:** responder preguntas compuestas.
- **Capacidades:** timeline (orden cronológico), before/after, proximity (mismo room_id ± ventana), cross-device agrupado por zona.
- **Ejemplos:** "hubo movimiento antes de la caída", "¿qué pasó mientras estaba fuera?"

**Criterio:** trazable (evidencias listadas implícitamente por respuesta derivada).

### FASE 4 — Razonamiento acotado (opcional, offline-aware)
- **Objetivo:** solo si aporta valor real.
- **Enfoque:** **plan-execute** (structured output) → generar `RecallPlan` JSON → ejecutar contra memoria determinista → síntesis acotada. **Nunca** generar hechos.
- **Feature flag + fallback 100% determinista.** Solo usar modelo si disponible; QFP obliga determinista.
- **Local primero:** considerar modelo local acotado (si presente) vs remoto. **No requisito hackathon.**

**Criterio:** zero-regression, trazabilidad, offline-safe.

---

## 6. Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| **Sobreingeniería** | Media-Alta | Mantener FASE 0–2 mínimos. No implementar FASE 4 ahora. |
| **Romper 208 tests** | Baja | No cambiar `MemoryIntentClassifier`/resolvers existentes. Añadir capas nuevas (no reemplazar). |
| **Complejidad espacial** | Media | Empezar con **mapping estático** (device_id→room_id). NO digital twin ahora. |
| **Síntesis demasiado libre** | Media | Constrained synthesis + evidence-first + fallback. |
| **Consistencia EN/ES + voz** | Baja (UX) | Ajuste menor TTS (voz EN masculina) + revisar toggle/lang (no core). |
| **Bedrock "honestidad estado"** | Baja | Verificar conexión real (health/metrics) — observación válida. |
| **Hackathon tiempo** | Alta | **NO implementar** roadmap ahora. Solo diseño. Demo actual (GO PARA VIDEO) suficiente. |

---

## 7. Dependencias

- **Internas:** `MemoryRecord`, `VectorMemoryService`, `MemoryBridge`, `MemoryConverse`, `EventHub`.
- **Externas (futuro opcional):** modelo local (structured output) — **no requerido**.
- **Config:** `device→room` mapping (YAML/env mínimo) — futuro.
- **UI:** nada nuevo para hackathon (Voice Dock existente).

---

## 8. Conclusión (honesta)

**Viabilidad hackathon: ALTA (con estado actual).**  
EchoMind ya cumple OBSERVAR→RECORDAR→CONVERSAR con 208 tests verdes. Los ejemplos propuestos ("¿Dónde vio mi mascota?", "¿Qué pasó mientras estaba fuera?") pueden mejorarse **sin** romper arquitectura: camino más directo = unificar recuperación (evidence-first) + síntesis template-light manteniendo rutas deterministas.

**Viabilidad vNext: ALTA si incremental.**  
Evolución hacia **recall-centric** es correcta. Clave: **NO reemplazar**, **añadir capas** (recall/synthesis) con fallback estricto. Mantener determinismo + trazabilidad + offline-first.

**Recomendación inmediata:** **NO implementar nada ahora**. Aceptar roadmap como guía. Para hackathon (17 OCT) **mantener estado actual**. Si se desea pulir conversacionalidad, aplicar **únicamente** fallback heurístico ultra-mínimo (Opción B del sprint anterior) — incluso eso **no es necesario** para demo validada.

**Mensaje central:** EchoMind debe razonar **sobre** recuerdos, no **en lugar** de memoria. La memoria (hechos) debe seguir siendo determinista y trazable; el razonamiento (síntesis) debe ser acotado y evidencia-basado.