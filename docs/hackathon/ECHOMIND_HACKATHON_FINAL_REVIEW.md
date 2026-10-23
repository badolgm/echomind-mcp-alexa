# ECHOMIND_HACKATHON_FINAL_REVIEW.md — Hackathon Final Review

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**Estado:** 208 tests PASSED. Todo validado (Android/IP Webcam/Vivotek/Voice Dock/MCP/TTS/Dashboard).

---

## 1. Estado actual

| Componente | Estado | Notas |
|---|---|---|
| Memoria | ✅ | MemoryBridge (episodio coalescing), VectorMemoryService, seed demo |
| Conversación | ✅ | MemoryConverse + MemoryIntentClassifier + resolvers MCP (EN/ES) |
| Voz | ✅ | TTS + STT, bilingüe, selección voz mejorada (con fallback) |
| Percepción | ✅ | Android real LIVE, IP Webcam LIVE, Vivotek LIVE |
| Arquitectura | ✅ | Hexagonal + DDD, MCP Streamable HTTP, determinista |
| Tests | ✅ | 208 PASSED (191 unit + 17 integration) |
| UX | ✅ | Voice Dock, Dashboard, camera switching, PHONE/Vivotek separados |

---

## 2. Fortalezas

- **Determinismo + trazabilidad**: recupera exclusivamente desde `MemoryRecord` (evidence-first). Sin LLM obligatorio.
- **Memoria episódica**: coalescing evita flooding (1 episodio vs N ticks). Correcto.
- **Offline-first / QFP compatible**: ruta determinista intacta. 
- **MCP unificado**: `memory_converse` integrado correctamente.
- **Bilingüe funcional**: backend ES/EN sólido; sync toggle + preferencias voz aplicadas.
- **Robusto**: fallback seguro en TTS/voz, graceful degradation.
- **Pragmático**: 208 tests verdes, sin sobreingeniería.

---

## 3. Debilidades

- **Intent-centric**: routing `classify→intent→resolver` limita formas coloquiales (ej. "última hora de detección de movimiento").
- **Síntesis débil**: `search` devuelve listados; otros usan plantillas. Falta síntesis basada en **conjunto de evidencias**.
- **Memoria espacial mínima**: solo `location` string. Sin `room_id/device_id/bbox/zone`. 
- **Timeline ausente**: no responde "antes/después", correlación temporal compuesta.
- **Voz ES**: menos natural vs EN masculina (disponibilidad en entorno).
- **Vivotek noche**: sensibilidad nocturna pendiente (ajuste conservador).

---

## 4. Brechas reales

| Brecha | Descripción | Impacto demo |
|---|---|---|
| **Recall-centric vs intent-centric** | Clasificación temprana decide ruta única | Respuestas menos naturales para localización/temporales |
| **Evidencia→Síntesis** | No une múltiples evidencias en narrativa coherente | "¿Qué pasó mientras estaba fuera?" → listado vs resumen |
| **Espacial** | Sin enriquecimiento espacial | "¿Dónde ocurrió la caída?" limitado a `living/cam-01` |
| **Cross-cámara** | Vivotek/Android no correlacionados por zona | Contexto unificado débil |

---

## 5. ¿Qué partes se acercan a teach/remember/recall?

| Concepto | Estado | Comentario |
|---|---|---|
| **Remember** | ✅ **Sólido** | `MemoryBridge` transforma eventos → `MemoryRecord`, coalescing por episodio. Consolida hechos. |
| **Recall** | ⚠ **Parcial** | `last_seen/search/summary` recuperan bien. Faltan: unificar bajo `recall(evidence+context)`, síntesis evidence-based, timeline. |
| **Teach** | ⚠ **Mínimo/no presente** | No hay aprendizaje de preferencias/definiciones. Opcional vNext. |

**Conclusión:** `remember` bien cubierto. `recall` funcional pero **no plenamente razonado**. `teach` no necesario ahora.

---

## 6. Capacidades reales subutilizadas

- **`model_analysis` bilingüe** en `MemoryRecord` (ya existe) — puede guiar síntesis sin inventar hechos.
- **Coalescing episodio** — base perfecta para agrupar ("episodio de movimiento") vs ticks.
- **`label_counts` + `top_events` + `count_occurrences`** — permiten componer filtros rápidamente.
- **`current_state`** (disponible en converse) — poco usado para desambiguar.
- **Separación PHONE/Vivotek** — permite correlación futura por zona.

---

## 7. Consultas conversacionales a mejorar

| Consulta | Actual | Deseado (evidence-based) |
|---|---|---|
| **¿Dónde vi mi mascota? / Where was my pet last seen?** | `last_seen(PET)` → responde ubicación/cámara/momento. Correcto funcionalmente. Mejorable en naturalidad. | Mantener evidencias + síntesis natural ("La última vez que vi a tu mascota fue... en patio/cam-X hace..."). Ya casi OK. |
| **¿Qué pasó mientras estaba fuera?** | Tiende a `SUMMARY` (24h) o `SEARCH` → listado genérico. | Recuperar eventos relevantes ventana razonable → ordenar cronológicamente → **resumir coherente** (no lista). Agrupar por zona/episodio. |
| **¿Dónde ocurrió la caída?** | `LAST_SEEN(FALL DETECTED)` funciona. | Enfatizar ubicación + cámara + momento + evidencia. Añadir contexto ("en living, cam..."). |
| **¿Cuándo hubo movimiento por última vez?** | Funciona con `LAST_SEEN(MOTION)`. Casos coloquiales ("última hora detección movimiento") van a SEARCH (visto antes). | Dirigir a `LAST_SEEN(MOTION)` con síntesis enfocada. Ya cubierto parcialmente con fix menor propuesto (fallback heurístico) — **no crítico**. |

---

## 8. Transformar intents → evidence+context+synthesis

**Principio:** *retrieve deterministic, synthesize constrained. Never invent facts.*

### 8.1 Pasos conceptuales (sin implementar)

1. **Understand (minimal)**: usar pregunta + `currentLang` + `current_state`. No reemplazar clasificador, **complementar**.
2. **Build RecallPlan (structured)**: inferir filtros `{labels, since/until, room_id/device_id, location}`. Puede derivarse del intent actual **o** heurísticamente. Mantener determinista por defecto.
3. **Retrieve (deterministic)**: siempre vía `VectorMemoryService` (last_seen/search/filters). **Sin delegar recuperación**.
4. **Relate (spatial/temporal)**: agrupar por zona/episodio, ordenar cronológicamente, detectar proximidad. Usa solo metadatos existentes (`location`, `timestamp`, `detections`, `source`).
5. **Synthesize (constrained)**: describir solo evidencias recuperadas. Ordenar (último primero), conectar mínimamente, evitar generalizaciones no soportadas. Usar `model_analysis` bilingüe cuando útil.
6. **Fallback**: si falla síntesis → usar resolver actual intacto.

### 8.2 Minimal viable path (pre-23 OCT)

**ÚNICO cambio viable minimalista:** fallback ultra-mínimo en `memory_converse` (redirigir SEARCH→LAST_SEEN cuando detecta "última/último/last" + label conocido). **Sin regex masivos, sin IF grandes**. Mejora naturalidad con riesgo ~cero.

**Resto:** mantener como-is para demo. Demasiado alcance para "justo antes" sin tocar arquitectura.

---

## 9. Prioridades

### PRE-23 OCT (Must Have)
| Ítem | Acción | Riesgo |
|---|---|---|
| **Coherencia bilingüe** | Aplicado (toggle+STT sync + preferencias voz) | ✅ Hecho/minimal |
| **Voz preferida EN masculina / ES natural** | Aplicado con fallback seguro | ✅ Hecho/minimal |
| **Honestidad estado Bedrock** | Verificar badge vs `/metrics` (lectura) | **Muy bajo** |
| **Tuning nocturno Vivotek (conservador)** | Ajuste parámetro mínimo, validar sin falsos | **Bajo** |

### NICE (si tiempo)
| Ítem | Acción | Riesgo |
|---|---|---|
| **Fallback recall-centric ultra-mínimo** | Redirigir casos coloquiales SEARCH→LAST_SEEN | **Muy bajo** |

### POST-HACKATHON (vNext)
| Ítem | Acción | Notas |
|---|---|---|
| **Recall unificado (evidence-first)** | `recall()` que devuelve `{evidence, meta}` + síntesis constrained | Clave para visión |
| **Memoria espacial** | Añadir `room_id/device_id/zone` (opcionales, backward compatible) | Sin Digital Twin |
| **Timeline + cross-cámara** | Relacionar por zona + proximidad temporal | Enriquecedor |
| **Razonamiento acotado (plan-execute)** | Solo con structured output + feature-flag + fallback 100% | Opcional, offline-aware |
| **Teach** | Menor prioridad | No necesario |

---

## 10. Recomendación final

**GO para demo profesional.**

**Razones:**
- **Infra sólida:** 208 tests PASSED, Android+Vivotek LIVE, Voice Dock+TTS bilingüe funcional.
- **Visión alineada:** "memoria que razona sobre recuerdos" ya se intuye (remember+recall parciales). Diferenciador vs CCTV claro.
- **Cambios aplicados correctos:** bilingüismo consistente, preferencias voz, sin romper arquitectura.
- **Demo-ready:** casos oficiales EN/ES funcionan, seed demo, flujo completo validado.
- **Evolutivo:** roadmap claro hacia recall-centric sin apresurarse.

**NO-GO a implementar recall-centric completo ahora.** Mantener enfoque: **pulir UX mínimo (Bedrock honesty + tuning nocturno conservador)** → demo profesional. La evolución hacia recall-centric es correcta pero pertenece a vNext.

**Mensaje:** EchoMind hoy ya transmite **Memory-First AI**. Con ajustes mínimos se vuelve demo pulida y fiel a visión `Alexa+ → EchoMind → Memoria → Contexto → Conversación → Acción`.