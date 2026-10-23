# PROJECT_VISION_ALIGNMENT.md — Alineación estratégica oficial

> **Documento de corrección de visión.** Fuente de verdad narrativa del proyecto, junto con
> `AI_BOOT_MASTER.md`. Rama `checkpoint/day1-mobile-memory` · commit validado `093a8ad` ·
> **203 tests PASSED** · flake8 limpio · black limpio.
>
> **Sin cambios de código · sin commits · sin push · sin cambios de arquitectura.**
> Solo alineación estratégica.

---

## Motivo de esta corrección

Parte de la documentación y algunas conversaciones estaban desviando el proyecto hacia una
identidad equivocada: un **sistema de cámaras**, un **dashboard de monitoreo**, un
**"robot Qdrant"** o una **plataforma CCTV**. Eso **no** corresponde al objetivo del hackathon.

Este documento fija la visión oficial y corrige la narrativa en toda la documentación.

**La frase que manda:** *EchoMind no es una cámara. EchoMind es **Alexa+** que puede
**OBSERVAR → RECORDAR → COMPRENDER → CONVERSAR → RESPONDER**.*

**Narrativa oficial (pirámide):**

```
Alexa+
   ↓
EchoMind          (agente cognitivo para Alexa+)
   ↓
Memoria
   ↓
Contexto
   ↓
Conversación
   ↓
Acción
```

**EchoMind es un agente cognitivo para Alexa+.** La **cámara NO es el producto**. La **Vivotek NO es
el producto**. **Android NO es el producto**. Todos ellos son **sensores o dispositivos del
ecosistema de Alexa**.

---

## 1. Qué NO es EchoMind

| ❌ No es | Por qué la confusión es un error |
| --- | --- |
| Una cámara | La cámara es un **sensor**. La Vivotek/Android no son el producto. |
| Una Vivotek / Ring / Blink | Son hardware de terceros que pueden actuar como **fuentes de señal**. |
| Un dashboard | El dashboard es la **consola operativa y de demostración**, no el sistema. |
| Un robot Qdrant | Inspirado en un concepto externo, pero **no** somos ese robot (ver §10). |
| Una plataforma CCTV | No es videovigilancia pasiva; es **memoria y conversación** sobre Alexa+. |
| Un visor de vídeo / NVR | No hay grabación masiva ni streaming continuo; hay **observaciones recordadas**. |

Si una frase de la documentación hace que la cámara o el dashboard parezcan **el producto**,
está desalineada y debe corregirse.

---

## 2. Qué SÍ es EchoMind

EchoMind es **Alexa+ con memoria ambiental**: un agente que observa el entorno, lo recuerda, lo
comprende, conversa sobre él y responde — de forma proactiva y bilingüe, incluso sin la nube.

**Cadena oficial de verbos:**

```
OBSERVAR      (sensor: cámara / teléfono / dispositivos / sensores)
   ↓
RECORDAR      (memoria histórica local: VectorMemoryService)
   ↓
COMPRENDER    (MemoryBridge consolida recuerdos; MemoryIntentClassifier interpreta)
   ↓
CONVERSAR     (MemoryConverse: pregunta/respuesta ES/EN, sin LLM obligatorio)
   ↓
RESPONDER     (Alexa+ habla; MCP integra las capacidades agenticas)
```

El valor no está en "ver", sino en **recordar y conversar** lo visto. La visión es el **input**;
la memoria y la conversación son el **producto**.

---

## 3. Protagonista real del sistema

**ALEXA.** Siempre.

- La cámara **no** es protagonista.
- El dashboard **no** es protagonista.
- Android **no** es protagonista.
- Los dispositivos **no** son protagonistas.

Son **medios** al servicio de Alexa. En cualquier narrativa (README, vídeo, Devpost, demo), la
primera frase y el sujeto activo son **Alexa**.

### 3.1 Rol de cada componente

| Componente | Rol | Categoría |
| --- | --- | --- |
| **Alexa** | **Agente principal** | Producto |
| **VectorMemoryService** | Memoria histórica | Capacidad |
| **MemoryBridge** | Consolidación de recuerdos | Capacidad |
| **MemoryConverse** | Conversación contextual | Capacidad |
| **MCP** | Integración agentica | Integración |
| **Vivotek** | Sensor visual | Entrada (sensor) |
| **Android** | Sensor visual alternativo | Entrada (sensor) |
| **Echo Hub / Echo Show** | Interfaz del ecosistema | Interfaz |
| **Dashboard** | Consola operativa y de demostración | Superficie |

---

## 4. Papel de Alexa

- Alexa es el **agente principal** y la **voz del sistema**: escucha, consulta la memoria,
  comprende el contexto y responde.
- Alexa se integra por **MCP (Streamable HTTP)** y el **skill manifest** (`alexa_skill/skill.json`):
  descubre tools, las invoca y recibe resultados tipados.
- Alexa **no depende** de la cámara ni del dashboard para recordar: si el sensor falla,
  **Alexa sigue recordando y conversando** (memoria local + QFP).
- Los **Echo Hub / Echo Show** son su **interfaz física** en el hogar.

**Regla de redacción:** Alexa es el sujeto. "Alexa observa / recuerda / responde" — nunca
"la cámara muestra que Alexa…".

---

## 5. Papel de la memoria

- **`VectorMemoryService`** es la **memoria histórica**: persiste observaciones como vectores
  (embeddings hash 256-D, deterministas, sin nube).
- **`MemoryBridge`** es la **consolidación**: convierte eventos (`camera_alert`) en **recuerdos**.
- **`MemoryConverse`** es la **conversación contextual**: interpreta la pregunta (ES/EN) y responde
  desde la memoria, sin LLM obligatorio.
- La memoria es el **diferenciador real** y el **protagonista técnico**. La cámara solo **alimenta**
  la memoria; vacía o llena, la memoria es lo que hace especial a Alexa.

**Consecuencia de visión:** aunque **no haya cámara** o el sensor devuelva el frame de fallback,
el sistema **sigue siendo demostrable** (memoria sembrada + conversación). La memoria **no** muere
con la cámara.

---

## 6. Papel de las cámaras

Las cámaras (Vivotek FD8367, Android/IP Webcam, o cualquier fuente) son **sensores visuales**, el
primer eslabón de la cadena. Su trabajo termina en alimentar observaciones:

```
Sensor visual  →  observación  →  (RECORDAR)  →  comprensión  →  conversación  →  Alexa responde
```

- **No** son el producto, **no** son el foco del vídeo, **no** son el titular del README.
- Se mencionan en la arquitectura como **"Vision sensor (input)"**.
- Regla de fallback: si la cámara no está disponible, la demo **continúa** (memoria + conversación);
  nunca se presenta como "la demo muere".

---

## 7. Papel de los dispositivos Alexa

Los dispositivos (Echo Show, Echo Hub, Ring, Blink, Smart Switches, etc.) aparecen **solamente**
bajo la etiqueta:

> **Alexa Ecosystem Devices**

- **No** son el producto.
- **No** son el foco principal.
- Son el **ecosistema** donde Alexa vive y actúa; el dashboard puede listarlos como catálogo, pero
  la narrativa no gira en torno a ellos.

---

## 8. Roadmap oficial

| Fecha | Hito |
| --- | --- |
| **11 OCT** | Consolidación |
| **12 OCT** | Validación Android real |
| **13 OCT** | Validación de conversación |
| **14 OCT** | Ensayos |
| **15 OCT** | Hardening |
| **16 OCT** | Congelación funcional |
| **17 OCT 15:00** | Inicio de grabación de vídeo |

**Regla dura:** a partir de la **congelación funcional (16 OCT)** no se añaden funcionalidades; solo
corrección de bugs P0. La grabación arranca el **17 OCT a las 15:00**.

---

## 9. Visión futura — Facility Digital Twin (POST HACKATHON · NO IMPLEMENTAR)

> **Estado: visión registrada, no implementada.** No introduce código, dependencias ni
> funcionalidades. Requiere aprobación explícita del owner y una fase propia posterior al
> hackathon.

Concepto: un **gemelo digital de la instalación** que proyecte la memoria espacial sobre un plano
para que **Alexa sea contextual por ubicación**.

**Cadena conceptual:**

```
Plano PNG/SVG
      ↓
Ubicación de dispositivos Alexa   (Echo Hub / Show…)
      ↓
Ubicación de sensores             (cámaras / sensores de entrada)
      ↓
Memoria espacial                  (VectorMemoryService: eventos con ubicación)
      ↓
Alexa contextual                  ("¿qué pasó en la cocina?" / "ve a la reja")
```

Reutiliza lo ya construido (memoria con ubicación + eventos en vivo) **sin** nuevas dependencias.
**Prohibido implementar** en esta fase.

---

## 10. Referencia externa — Qdrant Edge Memory Robot (inspiración, no copia)

Repositorio de referencia: `https://github.com/https-deeplearning-ai/sc-on-device-ai-memory`
("Qdrant Edge Memory Robot").

**Qué es ese proyecto:** un **robot físico de escritorio** (Jetson opcional) con cámara, micrófono y
detector de objetos; usa **YOLOE** (detección), **CLIP** (embedding de imagen), **Whisper** (voz) y
**Qdrant Edge** (vector store). Su flujo es: *TEACH* ("this is my chair") → reconoce → *MEMORY*
(repasar/olvidar) → *ASK* ("when did you last see my chair?"). Corre on-device, sin nube.

**Qué NO hacemos:**

- ❌ No copiamos ese robot ni su arquitectura (Jetson, YOLOE, CLIP, Whisper, Qdrant Edge).
- ❌ No introducimos CLIP, Whisper ni Qdrant real (prohibido, ver §No Hacer en `AI_BOOT_MASTER.md`).
- ❌ No clonamos su interfaz ni su modelo de hardware.

**Qué SÍ tomamos (inspiración conceptual):**

- ✅ La idea de **TEACH → REMEMBER → RECALL**: enseñar/aprender, recordar y recuperar por pregunta.
- ✅ El patrón de memoria que responde **"¿cuándo viste … por última vez?"**.
- ✅ La convicción de que la memoria es el valor, **no** la cámara.

**Cómo lo aplicamos a Alexa+:**

| Robot Qdrant (referencia) | EchoMind (nuestro) |
| --- | --- |
| Dispositivo físico con pantalla/botones | **Alexa+** como agente principal (voz) |
| Cámara on-device + YOLOE | Sensor visual (Vivotek / Android) → observación |
| CLIP (imagen) + Nomic (texto) | Embeddings hash deterministas (256-D), sin nube |
| Qdrant Edge shard | `VectorMemoryService` local (+ contrato `MemoryVectorStorePort`) |
| Whisper (STT local) | Web Speech API del navegador (STT/TTS); sin Whisper |
| *TEACH / MEMORY / ASK* | **OBSERVAR → RECORDAR → COMPRENDER → CONVERSAR → RESPONDER** vía **MCP** |

**Conclusión:** inspiración en **teach / remember / recall**, aplicada a **Alexa+** y sobre
arquitectura hexagonal + MCP. **No** somos el robot.

---

## Resumen en una frase (usar en TODA narrativa)

> **EchoMind gives Alexa+ a memory: it observes, remembers, understands, converses and responds —
> in English and Spanish, even without the cloud. The camera is just one of its senses.**

> _EchoMind le da a Alexa+ una memoria: observa, recuerda, comprende, conversa y responde, incluso
> sin la nube. La cámara es solo uno de sus sentidos._
