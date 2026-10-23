# ENGLISH_VOICE_RESTORATION_PLAN.md

**Fecha:** 2026-10-11
**Rama:** `checkpoint/day1-mobile-memory`
**Alcance:** Plan de decisión (NO implementación, NO cambios de arquitectura, NO commits/push).
**Estado:** 208 tests PASSED (sin cambios de código en este sprint).

---

## 1. Causa raíz definitiva

Dos causas **independientes**:

1. **Código (ya corregido en sprint anterior):** `speakAlexa()` ataba `match || voices[0]` (voz española) al texto EN y sobrescribía `utter.lang`. → EN hablado con voz ES. Ya corregido: EN nunca ata una voz de otro idioma.
2. **Entorno (bloqueante real, no es EchoMind):** **Chrome/Edge/Brave no disponen de ninguna voz inglesa** porque:
   - Chromium en Windows obtiene las voces del **registro `Speech_OneCore`** primero, y si enumera alguna, **usa solo esas y nunca cae a SAPI5**. Fuente: `content/browser/speech/tts_win.cc` → `GetVoiceTokens()`:
     ```cpp
     if (S_OK == SpEnumTokens(kSPCategoryOneCoreVoices, NULL, NULL, &(*out_tokens))) { /* usa OneCore */ }
     else if (S_OK != SpEnumTokens(SPCAT_VOICES, ...)) { return false; }
     ```
     (referencia: bugzilla.mozilla.org 1544143; chromium.googlesource.com tts_win.cc)
   - En este equipo **NO hay voces OneCore `en-*` instaladas** (solo `es-ES`). La única voz inglesa del sistema es **SAPI5 `Microsoft Zira Desktop` (en-US, female)**, que funciona a nivel OS pero **Chromium ignora**.

---

## 2. Inventario de voces (evidencia en vivo)

### 2.1 `speechSynthesis.getVoices()` — navegador (Chrome 155 / Edge 155 / Brave 155)

Probado: perfil copiado, perfil nuevo, `--lang=en-US`, espera 12 s, online. **Idéntico en los 3 navegadores:**

| voice.name | voice.lang | localService |
|---|---|---|
| `Microsoft Helena - Spanish (Spain)` | `es-ES` | true |
| `Microsoft Laura - Spanish (Spain)` | `es-ES` | true |
| `Microsoft Pablo - Spanish (Spain)` | `es-ES` | true |

**Total 3, todas `es-ES`. 0 voces `en-*`. Sin voces de red (Google). `onvoiceschanged` nunca disparó.**

### 2.2 Windows — SAPI5 (`HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens`)

| Nombre | Cultura | Género | Voz funcional |
|---|---|---|---|
| `Microsoft Zira Desktop - English (United States)` | `en-US` | **Female** | ✅ Sí (`Speak` OK) |
| `Microsoft Helena Desktop - Spanish (Spain)` | `es-ES` | Female | ✅ |

> Datos de Zira presentes: `C:\Windows\Speech\Engines\TTS\en-US\M1033ZIR.APM/.INI/.Keyboard.NUS`.

### 2.3 Windows — OneCore (`HKLM\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens`)

| Token | Voz | Cultura |
|---|---|---|
| `MSTTS_V110_esES_HelenaM` | Helena | es-ES |
| `MSTTS_V110_esES_LauraM` | Laura | es-ES |
| `MSTTS_V110_esES_PabloM` | Pablo | es-ES |

- **NO hay tokens `MSTTS_V110_enUS_*`** (búsqueda `enUS` = 0 coincidencias).
- `C:\Windows\Speech_OneCore\Engines\TTS\en-US\` contiene **solo** `MSTTSLocEnUS.dat` (locale), **sin datos de voz**.
- WinSxS `amd64_microsoft-windows-texttospeech-en-us_...` contiene solo `M1033ZIR.*` (Zira), **sin David/Mark**.
- Lenguajes de usuario instalados: `es-CO`, `es-419`, `es-ES` (**ningún `en-*`**). UI `es-MX`.

### 2.4 Cuáles son visibles para Chrome

**Solo las 3 OneCore `es-ES`.** Las SAPI5 (Zira en-US) **no** son visibles para navegadores Chromium.

---

## 3. Qué voz inglesa masculina se utilizaba anteriormente

**No puede determinarse con certeza** a partir de artefactos: nunca hubo una voz concreta en el código (git history no referencia ninguna; `speakAlexa` original solo hacía `find(en-*)`). Candidatos (por probabilidad):

| Candidato | Tipo | ¿Masculina? | ¿Disponible hoy aquí? |
|---|---|---|---|
| **Microsoft David** (en-US) | OneCore nativa | ✅ Sí | ❌ No instalada |
| **Microsoft Mark** (en-US) | OneCore nativa | ✅ Sí | ❌ No instalada |
| **Google UK English Male** | red (Chrome) | ✅ Sí | ❌ No aparece |
| **Microsoft Guy (Online, Natural)** (Edge) | neural nube | ✅ Sí | ❌ No expuesta a `speechSynthesis` |

**Nota:** la descripción "más natural y más cercana a Alexa" apunta a una voz **neural/nube**, no a la concatenativa nativa. Si esa era la voz, restaurarla vía OS no la reproduce exactamente (ver opciones).

---

## 4. Opciones reales

### Opción A — Instalar English (US) Text-to-Speech (recomendada, nativa)

Instalar el FOD oficial de TTS:
```powershell
# PowerShell ELEVADO
Add-WindowsCapability -Online -Name "Language.Basic~~~en-US~0.0.1.0"
Add-WindowsCapability -Online -Name "Language.TextToSpeech~~~en-US~0.0.1.0"
# (opcional, sólo reconocimiento de voz): Language.Speech~~~en-US~0.0.1.0
```
Luego **reiniciar los navegadores**. Verificar: `Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"` y `getVoices()` debe listar `Microsoft David`/`Microsoft Mark` (masculinas) y `Microsoft Zira`.

- **Ventajas:** oficial y soportado; aporta **voces masculinas nativas** David/Mark; funciona offline; Chrome/Edge/Brave las verán automáticamente (OneCore); sin tocar código.
- **Riesgos:** requiere **admin**; necesita Windows Update / ISO de features (o un origen FOD); puede mostrar **0 MB** en Configuración (reportado en Windows 11) aunque funcione; reinicio de navegadores; David/Mark **no** son neurales (calidad "concatenativa", no "Alexa-like").
- **Fiabilidad de la voz:** media (nativa), ✅ masculina.

### Opción B — Exponer una voz ya instalada (registro), sin descargar

Copiar el token SAPI5 de Zira a OneCore para que Chromium lo vea:
```
Copiar  HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_EN-US_ZIRA_11.0
    a   HKLM\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\TTS_MS_EN-US_ZIRA_11.0
```
(patrón confirmado en Thorium y en scripts de la comunidad). Requiere **admin**.

- **Ventajas:** **sin descargas**; habilita la única voz inglesa ya instalada (Zira); cambios mínimos.
- **Riesgos:** modificación manual del registro (respaldo previo); **Zira es FEMENINA** → **no cumple "voz masculina"**; no hay datos de David/Mark en el equipo para copiar; sin soporte oficial.
- **Fiabilidad:** ✅ funciona, ❌ **no masculina**.

### Opción C — Voz inglesa "de navegador"

- Chrome/Brave: usan OneCore → **mismo límite que A/B**; no aportan voz propia.
- Voces de red de Google (`Google UK English Male`): **no aparecieron** en 3 perfiles ni con red activa → no fiables en este entorno.
- Edge: las voces **neurales "Online (Natural)"** (p. ej. `Microsoft Guy`) **no se exponen** a `speechSynthesis` (solo a Lectura en voz alta). Edge con UI inglesa **siguió mostrando solo 3 voces es-ES**.
- **Conclusión:** C **no es viable** como fuente independiente de voz masculina aquí.

### Opción D — Alternativas soportadas

| Alternativa | Masculina | Naturalidad | Coste |
|---|---|---|---|
| **Amazon Polly (backend, vía infra AWS/Bedrock ya usada)** | ✅ (Matthew/Joey/Stephen/Brian) | ★★★ Máxima (es el motor de Alexa) | Cambio de backend/arquitectura (**aplazado**) |
| Extensión Chrome `chrome.tts` (motor TTS alternativo) | variable | variable | setup de extensión; dependencia |
| Demostrar en **otra máquina** con FOD en-US instalado | ✅ | según voz | depende de hardware |
| **NaturalVoiceSAPIAdapter** (voces Azure→SAPI) | ✅ | alta | 3rd-party; Chromium ignora SAPI igualmente |

- **Nota clave:** si la voz recordada era "casi Alexa", **Polly** es la respuesta definitiva (Amazon), pero implica cambio de arquitectura → **no ahora**.

---

## 5. Recomendación final

- **Para una voz inglesa MASCULINA nativa, rápida y soportada:** **Opción A** (`Language.TextToSpeech~~~en-US~0.0.1.0`) → David/Mark/Zira. Es la ruta **más segura y oficial**.
- **Si el objetivo es "lo más parecido a Alexa" (neural):** **Opción D — Amazon Polly** (mismo motor de Alexa), como trabajo **post-congelación** (backend).
- **Opción B** solo como recurso inmediato si no se puede instalar nada, asumiendo que **Zira es femenina** (no cumple el requisito masculino).
- **Opción C**: descartada.

> Elegir entre A y D depende de la expectativa de "masculina": **nativa aceptable (A)** vs **neural Alexa-like (D)**.

---

## 6. Conclusión: ¿cómo obtener una voz inglesa masculina real para la demo?

**Ruta recomendada (nativa, mínima, sin código):**
1. Instalar en el equipo de demo (PowerShell **elevado**): `Language.Basic~~~en-US~0.0.1.0` + `Language.TextToSpeech~~~en-US~0.0.1.0`.
2. Reiniciar Chrome/Edge.
3. Verificar: `speechSynthesis.getVoices()` muestra `Microsoft David`/`Microsoft Mark` (en-US, masculinas).
4. EchoMind ya prefiere voces masculinas EN por nombre (`david|mark|…`) → la usará automáticamente, sin cambios de código.

**Si se exige calidad "casi Alexa":** implementar **Amazon Polly** (backend) post-congelación, como única vía de naturalidad máxima y fiel a Alexa.

**Mientras no se instale nada:** el sistema es bilingüe en STT/query/caption/alertas; el TTS de EN no puede sonar en inglés por ausencia de voz `en-*` (limitación del entorno, no de EchoMind).

---

## 7. Evidencia (comandos)

- `speechSynthesis.getVoices()` (Chrome/Edge/Brave, 4 configs, 12 s): 3 voces `es-ES`.
- SAPI5: `Microsoft Zira Desktop` (en-US) + `Microsoft Helena Desktop` (es-ES); `Speak` con Zira = OK.
- OneCore: solo `MSTTS_V110_esES_*`; `enUS` = 0; `Engines\TTS\en-US` sin datos de voz.
- WinSxS `texttospeech-en-us`: solo `M1033ZIR.*` (sin David/Mark).
- Chromium `tts_win.cc` `GetVoiceTokens`: OneCore-first (referencias citadas).
- Microsoft FOD: `Language.TextToSpeech~~~<lang>` = TTS; `Language.Speech~~~<lang>` = reconocimiento.
- `pytest -q` → **208 passed**.

---

## 8. Estado / límites de este sprint

- **No** se modificó el sistema operativo ni el registro.
- **No** se instalaron paquetes.
- **No** se tocó Memory / MCP / Dashboard / Android / Vivotek / Motion / arquitectura.
- **No** commits / no push.
- Entregable: este plan. Decisión pendiente del usuario (A vs D; o B como parche femenino).
