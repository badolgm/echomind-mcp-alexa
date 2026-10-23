# ENGLISH_VOICE_RESTORATION_REPORT.md

**Fecha:** 2026-10-11
**Rama:** `checkpoint/day1-mobile-memory`
**Alcance:** `src/static/dashboard.html` → `speakAlexa()` únicamente.
**Estado tests:** 208 PASSED
**Restricciones respetadas:** sin commits, sin push, sin cambios de arquitectura, sin tocar el sistema operativo, sin instalar paquetes.

---

## 0. Resumen ejecutivo

- EN no suena en inglés **por dos causas separadas**:
  1. **Código (corregido):** `speakAlexa()` usaba `match || voices[0]` y por tanto ataba la voz española `voices[0]` (Helena) al texto inglés y **sobrescribía** `utter.lang` a `es-ES`.
  2. **Entorno (bloqueante real):** este equipo **no tiene ninguna voz inglesa instalada** para Chrome/Edge. Chrome solo expone 3 voces, todas `es-ES`.
- La corrección de código aplicada ya **no fuerza español en EN**, pero en este equipo **no puede sonar en inglés** porque no existe voz inglesa. Se documenta aquí + propuesta mínima a nivel de aplicación (sin tocar Windows todavía).

---

## 1. Voces que devuelve **Chrome** realmente (`speechSynthesis.getVoices()`)

Medido en vivo con Chrome 155.0.8059.80, headful, sobre `http://127.0.0.1:8000/dashboard`.
Probado en 3 configuraciones: **perfil copiado**, **perfil nuevo (fresh)** y **perfil nuevo con `--lang=en-US`**. Resultado idéntico en las tres:

| voice.name | voice.lang | localService | default |
|---|---|---|---|
| `Microsoft Helena - Spanish (Spain)` | `es-ES` | `true` | **true** |
| `Microsoft Laura - Spanish (Spain)` | `es-ES` | `true` | false |
| `Microsoft Pablo - Spanish (Spain)` | `es-ES` | `true` | false |

- **Total: 3 voces. 0 voces `en-*`.**
- `navigator.onLine = true`; espera de 12 s; `onvoiceschanged` **nunca** disparó (0 eventos). No aparecen voces de red de Google.
- `--lang=en-US` **no cambia** el listado.
- Edge (155.0.4283.45) devuelve **exactamente las mismas 3 voces es-ES**.

**Conclusión:** el navegador no ve ninguna voz inglesa en este equipo.

---

## 2. Voces que devuelve **Windows**

### 2.1 SAPI5 (registro `HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens`)

| Nombre | Cultura | Género |
|---|---|---|
| `Microsoft Zira Desktop - English (United States)` | `en-US` | **Female** |
| `Microsoft Helena Desktop - Spanish (Spain)` | `es-ES` | Female |

(`System.Speech.Synthesis.SpeechSynthesizer` 32-bit devuelve las mismas 2.)

### 2.2 OneCore (registro `HKLM\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens`)

| Token | Voz |
|---|---|
| `MSTTS_V110_esES_HelenaM` | Helena (es-ES) |
| `MSTTS_V110_esES_LauraM` | Laura (es-ES) |
| `MSTTS_V110_esES_PabloM` | Pablo (es-ES) |

- **No hay tokens `MSTTS_V110_enUS_*`.** Búsqueda `enUS` en OneCore → 0 coincidencias.
- `C:\Windows\Speech_OneCore\Engines\TTS\en-US\` existe pero contiene **solo** `MSTTSLocEnUS.dat` (datos de locale), **sin archivos de voz**. `C:\Windows\Speech_OneCore\Engines\TTS\es-ES\` sí contiene datos de voz (Helena/Laura/Pablo).

### 2.3 Observación clave

Chrome/Edge (Chromium) exponen las voces **OneCore**, **no** las SAPI5. Por eso Chrome muestra Helena/Laura/Pablo (OneCore es-ES) e **ignora** `Microsoft Zira` (SAPI5 en-US). La carpeta OneCore `en-US` carece de datos de voz, así que no hay nada que exponer en inglés.

**Contexto del equipo:** Windows 11 Education 10.0.26300, **UI language `es-MX`, culture `es-CO`**. Windows instala por defecto las voces del idioma de visualización, lo que explica que solo existan voces `es-ES`.

---

## 3. Qué voz está usando **EchoMind en EN**

- **Antes del fix (código previo, el que producía el síntoma):**
  `var voice = match || voices[0] || null;` → sin voz `en`, `match = null` → `voice = voices[0]` = **`Microsoft Helena - Spanish (Spain)` (es-ES)**, y además `utter.lang = voice.lang = "es-ES"`.
  **Resultado:** texto en inglés leído con voz y fonética **españolas** → "el texto responde en inglés, el caption en inglés, pero la voz suena en español". **Esta es la causa raíz del síntoma.**

- **Después del fix (aplicado):**
  En EN, se buscan solo voces `en-*`. Como no existen → `voice = null` → se conserva `utter.lang = "en-US"` y **no** se ata voz española.
  Verificado en vivo (sonda `speak_probe.js`): la locución EN dispara `start` y termina **sin error** (Chrome no queda en silencio), pero el motor cae a la voz por defecto = **Helena (es-ES)** porque es la única disponible. Es decir: **el fix elimina el error de código, pero en este equipo EN sigue sonando con acento español** por ausencia de voz inglesa.

---

## 4. Qué voz está usando **EchoMind en ES**

- **Antes y después:** `langMatches` (`es`) → preferencia `helena|pablo|laura|...` → **`Microsoft Helena - Spanish (Spain)` (es-ES)**.
- **Sin cambios:** ES sigue usando Helena (correcto y natural para este entorno).

| Idioma | Voz seleccionada (post-fix) | ¿Correcta? |
|---|---|---|
| **ES** | `Microsoft Helena - Spanish (Spain)` (`es-ES`) | ✅ Sí |
| **EN** | *(ninguna)* + `lang="en-US"` → Chrome fallback a Helena | ⚠️ Código correcto, pero el entorno no tiene voz EN |

---

## 5. Diferencia entre **entorno de pruebas** y **entorno demo**

| Aspecto | Entorno de pruebas (hoy) | Entorno demo (objetivo) |
|---|---|---|
| Máquina / binario | Windows 11 `es-MX` + Chrome 155 | **Mismo equipo/binario** |
| Perfil Chrome | copiado / fresh / `--lang=en-US` | perfil real del usuario |
| Voces expuestas | 3 `es-ES` | **3 `es-ES`** (idéntico, mismo OS/binario) |
| Voces Windows SAPI5 | Zira en-US (no expuesta), Helena es-ES | igual |
| Voces Windows OneCore | 3 `es-ES`; `en-US` sin datos | igual |

**Hallazgo:** pruebas y demo, sobre el **mismo equipo**, exponen **las mismas 3 voces**; no hay diferencia de voces entre ambos. Por tanto la voz masculina inglesa que se usó "anteriormente" **no proviene de este estado actual del entorno**: es consistente con una **voz en-US de Windows (Microsoft David, masculina)** que requiere el paquete de voz inglés (hoy ausente), o bien con una máquina/instalación distinta usada antes para grabar.

> Inferencia (marcada como tal): la voz masculina inglesa "más natural" observada antes corresponde muy probablemente a **Microsoft David (en-US)**, que aparece cuando el paquete de voz inglés (OneCore) está instalado. Hoy no está.

---

## 6. Causa raíz (definitiva)

1. **Bug de selección (código):** `match || voices[0]` ataba una voz de **idioma distinto** al solicitado y **sobreescribía** `utter.lang`. → EN hablado con voz ES.
2. **Limitación de entorno (bloqueante):** **no existe ninguna voz `en-*`** accesible por Chrome/Edge en este equipo; la única voz inglesa del sistema (SAPI5 Zira) no la expone Chromium, y la voz OneCore en-US no está instalada.

---

## 7. Corrección mínima aplicada (código, sin arquitectura)

Archivo: `src/static/dashboard.html` → `speakAlexa()`.

- Se construye `langMatches` = solo voces cuyo `lang` empieza por el prefijo del idioma objetivo.
- **EN:** si hay voces `en-*`, se prefiere una **masculina** por nombre (`male|david|mark|guy|george|paul|mike|richard|thomas|james|daniel|alex|matthew|joey|brian|fred|russell`); si no hay ninguna inglesa, **no se ata voz** y se mantiene `utter.lang = "en-US"`.
- **ES:** preferencia (`helena|pablo|laura|maría|…`) sin cambios.
- **Regla clave:** nunca atar una voz de idioma distinto al pedido (elimina el fallback a `voices[0]`).

**Efecto:** correcto a nivel de código; ES intacto; EN deja de forzar español. En este equipo EN aún suena español por falta de voz instalada (limitación de entorno, no de código).

---

## 8. Propuesta mínima (a nivel de aplicación, **sin tocar Windows**)

Para que la experiencia sea **honesta y predecible** sin instalaciones:

1. **Mantener la selección segura de idioma** (ya aplicada).
2. **Detección de capacidad en runtime (propuesta):** tras `refreshSpeechVoices()`, calcular `hasVoiceFor(lang)`. En `speakAlexa()`, si el idioma objetivo no tiene voz:
   - no atar voz incorrecta (hecho),
   - y mostrar un **hint no bloqueante** en `#voice-status` (p. ej. `"EN voice not available in this browser"`) para avisar al operador en demo. Sin dependencias, sin arquitectura.
3. **Chequeo pre-demo (manual, sin instalar):** abrir el dashboard y listar voces; si no hay `en-*`, habilitar la voz inglesa en el navegador/SO **antes** de grabar (paso posterior, no ahora).
4. **No** se proponen dependencias nuevas (WebAssembly TTS, Polly, etc.): fuera de alcance y de la restricción "sin nuevas funcionalidades".

---

## 9. Evidencia / comandos

- `speechSynthesis.getVoices()` (Chrome 155, copiado/fresh/`--lang=en-US`): 3 voces `es-ES` (Helena/Laura/Pablo).
- `System.Speech` + registro SAPI5: Zira (en-US) + Helena (es-ES).
- OneCore tokens: solo `MSTTS_V110_esES_*`; `enUS` → 0 coincidencias; `Engines\TTS\en-US` sin datos de voz.
- Sonda de locución: EN sin voz + `lang=en-US` → `start`, sin `error` (Chrome usa fallback Helena).
- `pytest -q` → **208 passed**.

---

## 10. Resultado

| Criterio | Estado |
|---|---|
| Causa raíz del síntoma EN→español | ✅ Identificada |
| Fix de código mínimo (sin arquitectura) | ✅ Aplicado |
| ES intacto (Helena) | ✅ |
| Sin tocar Windows / sin instalar paquetes | ✅ |
| Tests | ✅ 208 PASSED |
| EN audible en inglés en este equipo | ⚠️ No posible sin voz en-US (limitación de entorno, documentada) |

**Recomendación:** conservar el fix aplicado; para demo bilingüe real, habilitar previamente una voz inglesa (paso de entorno, fuera de este sprint). Propuesta de aplicación mínima: detección runtime + hint de estado (sección 8).
