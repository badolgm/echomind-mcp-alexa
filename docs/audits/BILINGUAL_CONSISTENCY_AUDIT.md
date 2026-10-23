# BILINGUAL_CONSISTENCY_AUDIT.md — Bilingual Consistency Audit

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**Estado:** 208 tests PASSED  
**Alcance:** Auditoría de flujo EN/ES completo (Dashboard → STT → /api/converse → MemoryConverse → caption → TTS). Sin implementación.

---

## 1. Flujo real EN/ES

Ruta actual:

1. **Dashboard UI**: `currentLang` inicial `"en"` (line 662). Botón `LANG: EN/ES` (184). Placeholder cambia al togglear (1086–1091).
2. **STT (mic)**: `toggleVoiceRecognition()` asigna `recognition.lang = currentLang === "en" ? "en-US" : "es-ES"` (1030) justo antes de `start()`. `recognition` creado una vez (986–991).
3. **Entrada usuario**: Ask (1072–1080), pills (1096–1102), mic (onresult 999–1005) → todos llaman `executeConverse(query)` sin re-escribir `lang`.
4. **API call**: `executeConverse` hace `fetch('/api/converse', {body: JSON.stringify({query: query.trim(), lang: currentLang})})` (1052–1057).
5. **Backend**: `/api/converse` (main.py) pasa `payload.lang` al resolver. `MemoryIntentClassifier.classify(text, lang)` usa `lang` explícito si válido (`en/es`) → `chosen_lang = lang` (domain/memory_intent.py). `MemoryConverse` usa `intent.lang` para todos los resolvers (summary/search/last_seen/history/current). Respuesta narrativa ya bilingüe.
6. **UI respuesta**: caption (`voice-caption-text`) muestra `answer` (1065–1069). Llama `speakAlexa(answer, currentLang, "dock")` (1070).
7. **TTS**: `speakAlexa` usa `targetLang = lang || currentLang || "en"` (684). Selecciona voz por prefijo idioma (686–690: `v.lang startsWith(prefix)` donde prefix = first 2 chars). Si voz encontrada → `utter.voice = voice; utter.lang = voice.lang` (694–697). Si no → fallback `en-US/es-ES` (698–699). Flags `isDockSpeaking` solo afectan alert vs dock (700–704), no idioma.

---

## 2. Puntos de ruptura detectados

| # | Punto | Observación | Riesgo | Notas |
|---|---|---|---|---|
| 1 | **Inicialización lang** | `currentLang = "en"` por defecto (662). Si usuario llega con ES esperado, requiere toggle. | **Bajo** | Comportamiento esperado. |
| 2 | **STT lang solo al start** | `recognition.lang` se asigna **solo** dentro de `toggleVoiceRecognition()` (1030) cuando se inicia mic. Si usuario cambia `currentLang` **después** de haber iniciado mic anteriormente (o entre sesiones), `recognition.lang` **no se actualiza** hasta próximo `start()`. | **Medio** | Cambio de LANG con mic ya "listo" pero no reiniciado → siguiente `start()` usa valor correcto. Si se cambia LANG mientras **no** reconociendo, próximo inicio sí toma nuevo valor. Observado: inconsistencia si se cambia rápidamente. |
| 3 | **Propagación a API** | `executeConverse` envía `lang: currentLang` siempre (1055). Correcto. | **Ninguno** | Bien propagado. |
| 4 | **Respuesta backend bilingüe** | `MemoryConverse` + resolvers usan `intent.lang`. Con `lang` explícito pasa correctamente ES/EN. Tests confirman (summary ES/EN, last_seen ES/EN). | **Ninguno** | Correcto. |
| 5 | **Caption vs TTS** | Ambos usan `currentLang`/respuesta. Caption muestra `answer` tal cual backend devuelve (con `intent.lang`). `speakAlexa` recibe `(answer, currentLang, "dock")`. Si backend respondió en ES pero `currentLang` cambió? Backend usa `intent.lang` (derivado del request/lang). Request envía `currentLang` actual. Generalmente coherente. | **Bajo** | Potencial desincronización solo si `currentLang` cambia entre request y speak? No ocurre secuencialmente. |
| 6 | **Selección voz TTS** | Búsqueda por prefijo `prefix = targetLang.slice(0,2)` (686) → match `v.lang startsWith(prefix)`. Si encuentra → fuerza `utter.lang = voice.lang` (696). **Si no encuentra → usa `en-US/es-ES` hardcoded** (698). | **Medio** | En Chrome muchas voces aparecen `es-ES` pero pueden faltar coincidencia exacta por variantes. Fallback correcto. |
| 7 | **Voces disponibles** | Sistema reportó solo voces `es-ES` (Helena/Laura/Pablo) en perfil copiado; **no** apareció voz EN masculina (`en-US` Zira/Microsoft David/etc). Resultado: EN → match falla → usa `en-US` pero **sin voz** → fallback a `voices[0]` (Helena, ES) asignado (690: `match || voices[0]`). Ahí está el origen: "voz inglesa masculina excelente" no existe en ese entorno → usa voz ES disponible. | **Alto (observado)** | Explica "la voz inglesa masculina es claramente superior" (deseado) vs "ES femenina suena más robótica" (disponible). También explica por qué "voz no siempre cambia correctamente" (se cae a voz ES). |
| 8 | **isDockSpeaking / alert lock** | Bloquea alert si dock hablando (680). No afecta idioma. Correcto. | **Ninguno** | Sin impacto bilingüe. |

---

## 3. Archivos implicados

| Archivo | Líneas relevantes | Rol |
|---|---|---|
| `src/static/dashboard.html` | 662 (`currentLang`), 1030 (`recognition.lang`), 1052–1070 (`executeConverse`), 1082–1091 (`langBtn` toggle), 673–708 (`speakAlexa`) | UI bilingüe: estado lang, STT, API call, TTS/voz |
| `src/main.py` | `/api/converse` (194–205 aprox) | Propaga `lang` a resolver |
| `src/domain/services/memory_intent.py` | `classify(text, lang)` (195–210) | Elige idioma (respeta explícito) |
| `src/infrastructure/adapters/mcp/memory_resolvers.py` | `build_memory_converse_resolver` + resolvers (SUMMARY/LAST_SEEN/etc) | Narrativas ES/EN coherentes con `intent.lang` |

---

## 4. Cambios mínimos recomendados

**Sin nuevas funcionalidades. Solo correcciones mínimas, conservadoras.**

| # | Cambio | Justificación | Riesgo |
|---|---|---|---|
| **A. Sincronizar STT lang al cambiar toggle** | En `langBtn.click` (1082–1091), si `recognition` existe → actualizar `recognition.lang = currentLang==='en'?'en-US':'es-ES'`. | Evita desincronización si usuario cambia LANG sin reiniciar mic. | **Muy bajo** |
| **B. Forzar coherencia caption/TTS con respuesta** | Opcional: pasar `lang` efectivo (p.ej. derivado de respuesta o `intent.lang`) a `speakAlexa`. Actualmente pasa `currentLang`. Como backend ya usa `intent.lang` correcto, rara vez necesario. | Evita casos edge si `currentLang` cambia entre request/speak (improbable). | **Muy bajo** |
| **C. Mejorar selección de voz (priorizar preferencias)** | En `speakAlexa`, añadir **preferencia mínima**: para EN priorizar voces con `name` que contenga `male`/`David`/`Mark`/`George`/`Zira`? O buscar heurísticamente. Para ES, evitar voces excesivamente "robóticas" si hay alternativas (`Helena` vs otras). | Aborda observación "voz EN masculina excelente" vs "ES femenina robótica". **Mantener fallback** (match por lang → voices[0]). | **Bajo** (solo ordenamiento) |
| **D. Cachear/actualizar voces con `onvoiceschanged` robusto** | Ya existe `refreshSpeechVoices()` + `onvoiceschanged`. Podría forzar refresh al primer speak tras carga (ya hecho). | Robusto. Sin cambio necesario. | **Ninguno** |
| **E. Verificación Bedrock "honestidad estado"** (UI/metrics)** | Revisar `provider` status en `/metrics` vs UI badge. No tocar backend. Solo auditoría/ajuste visual si necesario. | Transparencia demo. **No funcional**. | **Muy bajo** |

**Recomendado:** **A + C** (mínimos). **B/E** opcionales.

---

## 5. Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| **Romper 208 tests** | **Muy baja** | Solo cambios JS UI (dashboard.html), sin tocar backend/domain/tests. |
| **Forzar voz inexistente** | **Baja** | Siempre mantener `match || voices[0] || null` + fallback `en-US/es-ES`. Nunca hardcodear voz no disponible. |
| **STT cambio brusco** | **Muy baja** | Actualizar `recognition.lang` solo cuando existe; no reiniciar mic automáticamente (evitar interrupciones). |
| **Regresión audibilidad** | **Baja** | Validar headful con perfil real (igual que validación anterior). |

---

## 6. Validación esperada (post-corrección)

**Checklist manual (Chrome real, perfil usuario):**

1. **Toggle EN→ES→EN**: LANG cambia, placeholder correcto. Mic start usa `es-ES`/`en-US`.
2. **Mic EN**: STT reconoce EN → caption EN → TTS EN (voz preferida o fallback coherente). Sin salto a ES.
3. **Mic ES**: STT ES → caption ES → TTS ES. Coherente.
4. **Ask (texto) EN/ES**: mismo resultado. Pills idem.
5. **Cambio LANG entre consultas**: sin afectar respuesta anterior. Nueva consulta usa nuevo lang.
6. **Voces detectadas**: listar `speechSynthesis.getVoices()` (headful) → confirmar disponibilidad EN masculina/ES.
7. **Bedrock estado**: comparar badge UI vs `/metrics` provider status (honestidad).

**Automatizable:** usar `final_audibility.js` ajustado (ya existe) para trazar lang+voice+caption.

---

## 7. Veredicto

**GO para corrección mínima antes del 23 OCT**

**Razón:** Los puntos A+C son **correcciones reales** de inconsistencias observadas (STT sync + preferencia de voz). No añaden funcionalidades, mantienen determinismo, **0 riesgo esperado** sobre backend/tests (208 green). Restante son observaciones/documentadas.

**NO-GO para cambios mayores:** recall-centric completo, memoria espacial, reasoning acotado → aplazar a vNext (correcto según roadmap previo).