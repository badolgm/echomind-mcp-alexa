# DEMO_INTELLIGENCE_ALIGNMENT.md — Demo Intelligence Alignment

**Fecha:** 2026-10-11  
**Estado:** Análisis sin implementación/cambios/código. Base: 208 tests PASSED.  
**Objetivo:** Cerrar brechas entre visión EchoMind y experiencia real de demo (antes 23 OCT).

---

## 1. Observaciones validadas → Brechas

| Observación | Brecha | Impacto en demo |
|---|---|---|
| Voz EN masculina superior | Voz ES femenina menos natural/robótica | Primera impresión bilingüe desequilibrada |
| ES/EN inconsistente | Toggle/lang no siempre coherente entre STT/TTS/answer | Rompe flujo conversacional bilingüe |
| Bedrock muestra ACTIVE (verificar honestidad) | Transparencia de estado (provider real vs fallback) | Credibilidad técnica (demo AWS-aware) |
| Vivotek pierde detección útil noche | Sensibilidad/umbral nocturno | Casos reales (vision nocturna) menos sólidos |
| MemoryConverse intent-centric > recall-centric | Routing rígido vs respuesta natural basada en evidencia | "¿Dónde vio mi mascota?" menos natural vs visión Memory-First |

---

## 2. Qué mejora la demo final

### 2.1 Experiencia de voz (bilingüe)
- **Prioritario demo:** Selección de voces preferidas (EN: masculina más natural; ES: alternativa más natural si disponible en Chrome/SAPI) con **fallback determinista** (mantener lógica actual sin romper). Solo preferencia, no cambia arquitectura.
- **Consistencia EN/ES:** asegurar `currentLang` propagado uniformemente (input → classify → resolver → caption → TTS). Evitar desincronización entre botón LANG, reconocimiento STT y respuesta.
- **Menor prioridad:** Afinar rate/pitch sutilmente (sin añadir features).

### 2.2 Narrativa Memory-First
- Para preguntas de localización/temporales, favorecer respuestas **enfocadas en recuerdo** (última observación + ubicación + momento + evidencia) vs listado genérico. Esto alinea con recall-centric **sin** cambiar árboles IF/THEN masivos (ver 3.1).

### 2.3 Credibilidad/Transparencia
- Verificación honesta de estado Bedrock (ACTIVE vs degraded/fallback real) — **visual/telemetría**, sin nueva arquitectura. Mostrar estado real cuando corresponda (transparencia técnica).

### 2.4 Robustez percepción noche (Vivotek)
- Ajuste **mínimo y conservador** de umbrales nocturnos (sensibilidad/motion) para mejorar detecciones útiles sin aumentar falsos drásticamente. **Solo tuning de parámetros**, sin CLIP/Whisper/nuevas features. Verificar con tests (208).

---

## 3. Qué aporta valor real antes del 23 OCT

### Must Have (críticos para demo pulida)

1. **Coherencia bilingüe EN/ES** (toggle + STT + respuesta + TTS). Verificar flujo end-to-end con casos oficiales (EN/ES). Bajo riesgo, alto impacto.
2. **Selección de voz preferida (mínima)**: preferir voz EN masculina disponible + alternativa ES más natural si existe (fallback seguro). Sin romper `speechSynthesis` existente.
3. **Honestidad de estado Bedrock**: validar que badge/metrics reflejan estado real (no solo visual). Pequeña verificación (no implementación nueva).
4. **Tuning nocturno Vivotek (conservador)**: parámetro mínimo para mejorar noche sin falsos excesivos. Validar con comportamiento estable.

### Nice To Have (mejora conversacional)

1. **Micro-mejora recall-centric**: fallback ultra-mínimo (Opción B report anterior) para casos coloquiales ("última detección de movimiento") → respuesta enfocada (last_seen) vs listado. **Sin regex extensos, sin IF nuevos grandes**. Bajo riesgo, mejora naturalidad.
2. **Consistencia caption/TTS idioma**: garantizar misma `lang` siempre (evitar que respuesta EN use voz ES por fallback no deseado). Usa lógica de fallback existente (voz disponible) pero prioriza coherencia.

---

## 4. Qué debe aplazarse a vNext

**Post Hackathon (vNext):**

- **Recall-centric completo** (RecallPlan + evidence-first + synthesize constrained): requiere capa nueva, aunque conceptual ya definido. Alto valor, riesgo/tiempo innecesario antes demo.
- **Memoria espacial** (room_id/device_id/bbox/zone, cross-camera correlation, timeline before/after): extiende modelo de datos (backward-compatible pero no necesario para demo oficial).
- **Razonamiento acotado con modelo (plan-execute structured)**: añade dependencia opcional, feature-flag + fallback. Fuera de alcance hackathon.
- **Digital Twin / plano / marcar punto exacto:** explícitamente NO hacer (Facility Digital Twin fuera de alcance).
- **CLIP/Whisper/investigate_incident/Qdrant real:** ya excluidos.

---

## 5. Cómo garantizar experiencia bilingüe coherente

- **Fuente única de idioma:** `currentLang` (UI) → usar siempre para `classify(query, lang)`, `/api/converse` (`lang`), STT (`recognition.lang`), TTS (`speakAlexa(..., currentLang, ...)`).
- **Propagación completa:** al cambiar LANG (toggle), actualizar placeholder + STT lang + asegurar próximas respuestas usan ese lang. Verificar pills/Ask/Mic.
- **Caption + voz alineados:** respuesta del resolver con `intent.lang` (o lang solicitado) → caption y TTS mismo idioma. Evitar mismatch caption EN/voz ES salvo fallback justificado (y preferir coherencia).
- **Fallback controlado:** si no hay voz del idioma, priorizar **voz disponible coherente con respuesta** + log implícito (no romper experiencia). Mantener determinismo.
- **Test bilingüe mínimo:** validar Qs oficiales EN/ES (What happened today?, Critical events?, ¿Qué recuerdas hoy?, ¿Cuándo viste reja abierta?) con caption+TTS coherentes.

---

## 6. Cómo presentar EchoMind como Memory-First AI

- **Narrativa pirámide:** `Alexa+ → EchoMind (agente cognitivo) → Memoria → Contexto → Conversación → Acción`. Protagonista **Alexa+**. Cámara = **sensor**, no producto.
- **Enfatizar diferenciador:** *observa → recuerda → comprende → conversa → responde* (memoria ambiental). No "detección de cámaras", sino **memoria espacial multimodal** que razona sobre recuerdos.
- **Respuestas evidence-first:** mostrar respuestas enfocadas (última observación + cuándo/dónde + evidencia) vs listados genéricos. Esto transmite "recuerda y razona", no "busca logs".
- **UI messaging:** Voice Dock "Alexa Conversational Memory Dock", énfasis en "Memory", "Conversational Memory", no "Alerts/Detections".
- **Demo flow:** empezar con Seed Memory → preguntar sobre **historia/recuerdos** ("What do you remember?", "¿Qué recuerdas de hoy?") antes que alertas → demostrar que responde sobre **pasado** (memoria) no solo presente.
- **Evitar terminología CCTV:** reemplazar mentalmente "eventos detectados" por "recuerdos observados/registrados". Caption ya refleja memoria (summary/last_seen).

---

## 7. Priorización + Riesgos

### Prioridades

| Prioridad | Ítem | Tiempo estimado | Riesgo |
|---|---|---|---|
| **P0 (Must Have)** | Coherencia bilingüe EN/ES (toggle/STT/TTS/caption) | ~30–60 min | **Bajo** |
| **P0** | Voz preferida (EN masculina + ES natural con fallback) | ~15–30 min | **Bajo** |
| **P0** | Honestidad estado Bedrock (verificación real) | ~15 min | **Bajo** |
| **P0** | Tuning nocturno Vivotek (conservador) | ~30 min | **Bajo–Medio** (ajustar umbrales, validar sin falsos) |
| **P1 (Nice)** | Micro-fallback recall-centric (última detección/evento) | ~15 min | **Muy Bajo** |
| **P1** | Alineación caption/TTS idioma | ~10 min | **Muy Bajo** |

### Riesgos

| Riesgo | Mitigación |
|---|---|
| Tuning noche aumenta falsos | **Conservador + incremental**, validar con escena estática, no romper tests 208. |
| Cambio voces afecta timing/audibilidad | Usar solo voces disponibles (fallback existente), no forzar voz inexistente. |
| Bedrock verification cambia UI | Solo lectura/estado, sin lógica nueva. |
| Over-tuning conversacional (regex/IF) | **NO** hacer. Usar fallback ultra-mínimo (Opción B) o evitar por completo. |

---

## 8. Recomendación (antes 23 OCT)

**Aprobar Must Have + P1 selectivo. Aplazar resto a vNext.**

- **Demo impact directo:** voz + coherencia bilingüe + transparencia estado.
- **Alineación visión:** micro-mejora recall-centric refuerza "Memory-First AI" sin cambiar arquitectura.
- **Seguro:** mantiene 208 tests verdes, sin nuevas features, sin romper determinismo/QFP.

**Conclusión:** Cerrar brechas críticas de UX conversacional con cambios **mínimos, conservadores y trazables**. Mantener EchoMind fiel a su identidad: **memoria espacial multimodal que razona sobre recuerdos**, no sistema de detección de cámaras.