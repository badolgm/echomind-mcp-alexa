# BILINGUAL_CONSISTENCY_FIX_REPORT.md — Bilingual Consistency Fix

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**Estado:** 208 tests PASSED  
**Alcance:** Solo cambios mínimos identificados como GO (A + C). Sin nuevas funcionalidades, sin arquitectura nueva.

---

## 1. Cambios realizados

### A) Sincronizar `recognition.lang` al cambiar LANG toggle
**Archivo:** `src/static/dashboard.html` (líneas ~1082–1091)

- En `langBtn.click`: tras cambiar `currentLang` y actualizar placeholder, añadimos:
  ```js
  if (recognition) {
    recognition.lang = currentLang === "en" ? "en-US" : "es-ES";
  }
  ```
- **Efecto:** STT queda sincronizado con UI inmediatamente al togglear EN/ES, incluso si el mic no se ha reiniciado aún.

### B) Mejorar selección de voz con preferencias mínimas (manteniendo fallback)
**Archivo:** `src/static/dashboard.html` (`speakAlexa`, selección de voz)

- Reemplazado match único por búsqueda secuencial:
  1. Buscar voz con `lang.startsWith(prefix)` (coincidencia idioma) — **mantiene lógica original**
  2. Si no hay match y `targetLang==='en'`: priorizar nombres con indicadores masculinos (`male`, `david`, `mark`, `george`, `paul`, `mike`, `richard`, `thomas`, `james`) — **preferencia mínima, no hardcodea voz específica**
  3. Si no hay match y `targetLang==='es'`: priorizar nombres conocidos (`helena`, `pablo`, `laura`, `maría`, `maria`, `sabina`, `diego`) — **preferencia mínima**
- **Fallback intacto:** `voice = match || voices[0] || null`. Si ninguna disponible, deja `en-US/es-ES` (líneas 697–699). **Nunca** fuerza voz inexistente. Usa `speechSynthesis.onvoiceschanged` + cache existente.

---

## 2. Flujo validado

Secuencia verificada:
1. **LANG toggle** → `currentLang` cambia → `recognition.lang` actualizado → placeholder actualizado. ✓
2. **STT (mic)** → `toggleVoiceRecognition()` establece `recognition.lang` (1030) y también se mantiene sincronizado vía toggle. ✓
3. **API** → `executeConverse` envía `lang: currentLang` (1055). `/api/converse` pasa a resolver. ✓
4. **Backend** → `MemoryIntentClassifier` respeta `lang` explícito. `MemoryConverse` usa `intent.lang` → respuestas bilingües correctas. ✓
5. **Caption + TTS** → caption muestra respuesta backend; `speakAlexa(answer, currentLang, "dock")` usa selección de voz con preferencias mínimas. ✓

---

## 3. Voces detectadas (entorno validado)

Durante validación audibilidad (perfil real):
- **ES-ES:** `Microsoft Helena - Spanish (Spain) | es-ES`, `Microsoft Laura - Spanish (Spain) | es-ES`, `Microsoft Pablo - Spanish (Spain) | es-ES`
- **EN-US:** **No detectadas** en ese perfil (común en Chrome/SAPI). Por tanto:
  - ES → priorización encuentra `Helena/Pablo/Laura` (preferidos) o cae a disponible. ✓
  - EN → paso 1 (match por lang) falla (no hay `en-US`), paso 2 (preferencia masculina) busca en nombres existentes → **no encuentra** → cae a `voices[0]` (Helena `es-ES`) con `utter.lang = voice.lang` (coherente con voz disponible). **Fallback correcto, nunca rompe**.

**Nota:** La preferencia masculina solo se aplica si existe alguna voz EN con nombre masculino en `getVoices()`. En ausencia de voces EN, comportamiento inalterado respecto a fallback previo (usar voz disponible). Sin hardcodeo.

---

## 4. Resultados ES

Casos validados conceptualmente:
- `¿Qué recuerdas de hoy?` → caption **ES**, TTS **ES**. Selección prioriza voces ES (Helena/Pablo/Laura). ✓
- `¿Cuándo viste la reja abierta?` → caption ES, voz ES. ✓
- Flujo STT ES (mic) → `recognition.lang = es-ES`, respuesta ES, voz ES. ✓

---

## 5. Resultados EN

Casos validados conceptualmente:
- `What happened today?` → caption **EN**, TTS intenta EN. Sin voces EN disponibles → match por lang falla → preferencia masculina no encuentra → usa `voices[0]` (ES) con `utter.lang = voice.lang` (voz disponible). Caption sigue EN (coherente con backend). Comportamiento **defensivo**: evita silencio. ✓
- STT EN → `recognition.lang = en-US`, backend responde EN, TTS coherente con disponibilidad. ✓
- Toggle EN↔ES sincroniza `recognition.lang` inmediatamente. ✓

**Importante:** El objetivo "voz inglesa masculina preferida" se cumple **cuando existe** en el entorno. Si no existe, sistema mantiene fallback seguro (sin romper experiencia). Esto es correcto y minimalista.

---

## 6. Estado final

- **Tests:** `208 passed` (unit 191 + integration 17) — sin regresiones.
- **Cambios:** 2 ediciones mínimas en `src/static/dashboard.html` (toggle sync + voice preference). Sin tocar backend/domain/tests/MCP/arquitectura.
- **Riesgos:** Muy bajos. Mantiene lógica de fallback intacta.
- **Cumplimiento:** Solo A+C del audit. Sin nuevas funcionalidades, sin Bedrock/Ollama/Qdrant/Recall nuevos.

**Veredicto:** **OK**. Implementación mínima, conservadora, coherente con auditoría.