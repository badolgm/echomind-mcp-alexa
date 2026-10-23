# ECHOMIND VISION ALIGNMENT

> Sprint: **VISION ALIGNMENT**. Evaluación honesta, sin implementar.
> **NO implementar. NO código. NO commits.**
>
> Referencia comparada: **`https-deeplearning-ai/sc-on-device-ai-memory`**
> ("Qdrant Edge Memory Robot", el proyecto físico del short course *Building AI
> Assistants with On-Device Memory*, DeepLearning.AI × Qdrant, instructor Dylan
> Couzon).
>
> Fuentes: README del proyecto de referencia, `docs/architecture.md`, y el código
> y los documentos de EchoMind V2 (`README.md`, `memory_service.py`,
> `ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md`, `A7C/A7D`).
>
> Pregunta central del sprint, al final del documento.

---

## 0. Preparación: qué es exactamente el proyecto de referencia

No es un motor de memoria de eventos. Es un **robot físico que aprende objetos
enseñados por el usuario** y recuerda dónde y cuándo los vio, todo *on-device*:

```
camera -> detect/track -> crop -> CLIP image vector
voice  -> Whisper -> name -> Nomic text vector
                        |
                  Qdrant Edge shard
                        |
              recognize and recall
```

Sus tres verbos operativos son, literalmente, los del sprint:

- **TEACH** — el usuario sostiene un objeto, pulsa TEACH y dice *"This is my
  chair."* El robot guarda el objeto + su nombre + lugar + hora.
- **REMEMBER** — cuando vuelve a ver el objeto, escribe un *sighting* (`seen`).
- **RECALL** — *"When did you last see my chair?"* → recupera los sightings más
  recientes por tiempo. La respuesta sale de campos del payload (`label`, `ts`,
  `where`, `thumb`); **ningún LLM la redacta**.

Esquema de memoria (un shard Qdrant Edge, tres `kind`):

| kind | vectores | propósito |
| ---- | -------- | --------- |
| `taught` | `image` (CLIP 512) + `text` (Nomic 768) | vista de ejemplo **nombrada por el usuario** |
| `seen` | `image` | avistamiento posterior de un objeto conocido |
| `ignored` | `image` | clutter descartado que debe permanecer oculto |

Clave conceptual: **el detector descarta sus etiquetas** (`YOLOE`); la identidad
de un objeto la fija **el usuario al enseñarlo**, no el modelo. Enseñar es una
operación de memoria, no un reentrenamiento.

---

## 1. Qué problema resuelve el proyecto de referencia

**Problema:** "¿dónde está mi cosa, y cuándo la vi por última vez?" para
**objetos que el usuario define**.

- **Memoria de objetos con identidad enseñada.** El usuario nombra lo que le
  importa ("mi silla", "mi cartera"). El sistema no decide por él qué es
  relevante.
- **Reconocimiento por ejemplos, sin reentrenar.** 2–3 ángulos enseñados bastan;
  reconocer es una búsqueda al vecino más cercano bajo un umbral calibrado.
- **Recuerdo espaciotemporal.** Guarda *dónde* y *cuándo* para cada avistamiento.
- **On-device / sin nube / sin LLM.** Privacidad y operación offline por diseño.
- **Gestión de memoria curada por el humano.** Renombrar, olvidar (`forget`),
  ignorar clutter.

Dominio: **memoria episódica de un objeto concreto, poblada por el usuario.**

---

## 2. Qué problema resuelve EchoMind hoy

**Problema:** dar a **Alexa+** memoria del hogar y responder preguntas en
lenguaje natural, es/en, con evidencia, sobre **lo que el hogar observó**.

- **Vigilancia ambiental autónoma.** `AmbientWatchService` mezcla movimiento de
  cámara con sensores (humo, temperatura, reja/puerta, collar de mascota) y
  emite `camera_alert` en `EventHub`.
- **Ingesta pasiva.** `MemoryBridge` persiste los eventos HIGH/CRITICAL
  coalescidos en `VectorMemoryService` — **sin intervención del usuario**.
- **Recuerdo de eventos estructurado.** `understand() → RecallPlan →
  RecallEngine`: `LAST_SEEN`, `SEARCH`, `RANGE`, `TOP`, `AGGREGATE`,
  `CURRENT_STATE`.
- **Relaciones y contexto.** `Episode` → `Relation` (vocabulario cerrado:
  temporal, espacial, correlación) → `ContextItem` (gradado por saliencia).
- **Dos fuentes de verdad.** `route_query` (A7C) separa *presente*
  (`watch.last_state`) de *pasado* (memoria); A7D da forma a la respuesta
  (`ResponseIntent`).
- **Determinismo y abstención.** Sin LLM ni reloj de pared en el camino de
  memoria; sin evidencia → abstención honesta; degradación espacial explícita.

Dominio: **memoria episódica de eventos del hogar, poblada por el sistema.**

> Nota de linaje: `memory_service.py` ya se declara *"Qdrant Edge inspired"* y
> define el contrato `MemoryVectorStorePort` (collection, Cosine, payload
> filters) como adaptador futuro. **La referencia y EchoMind comparten la misma
> raíz de motor vectorial**, no el mismo modelo de datos.

---

## 3. Dónde coinciden

| Dimensión | Coincidencia |
| --------- | ------------ |
| **Motor de memoria** | Ambos vector store *edge*, embedded, sin servidor, Cosine, metadata/payload. EchoMind se declara explícitamente inspirado en Qdrant Edge. |
| **Filosofía on-device** | Ninguno depende de la nube para recordar. EchoMind: el camino de memoria nunca llama a Bedrock. La referencia: todo local, sin API key. |
| **Recuerdo espaciotemporal** | Ambos responden "dónde / cuándo". EchoMind: `last_seen`, `location`/`zone`/`camera_id`. Referencia: `ts`, `where`, sightings. |
| **Respuesta sin alucinación** | Ambos construyen la respuesta desde hechos almacenados. Referencia: "*no language model generates it*". EchoMind: "every claim comes from a retrieved fact". |
| **Recuerdo como operación de memoria, no del modelo** | Referencia: descarta etiquetas del detector. EchoMind: identidad y relaciones viven en el dominio, no en el LLM. |
| **Degradación explícita** | Referencia: umbral de reconocimiento calibrado. EchoMind: degradación espacial + abstención. Ambos prefieren "no sé" a "adivino". |
| **Analizable / inspeccionable** | Referencia: `MEMORY` para ver/renombrar/olvidar. EchoMind: `evidence` + `trace` auditables por respuesta. |

---

## 4. Dónde divergen

| Dimensión | `sc-on-device-ai-memory` | **EchoMind V2** |
| --------- | ------------------------ | --------------- |
| **Quién puebla la memoria** | **El usuario** (TEACH) | **El sistema** (watchdog → bridge) |
| **Unidad de memoria** | **Objeto/entidad** con identidad enseñada | **Evento/observación** con timestamp |
| **Identidad** | Nombre dado por el humano ("my chair") | Etiqueta del detector (`PERSON`, `FALL DETECTED`) |
| **Vector** | CLIP imagen + Nomic texto (semántico real) | Term-frequency hasheada determinista (256-d) |
| **Reconocimiento de objeto** | Núcleo (`recognize` + umbral) | **No existe** como capacidad |
| **TEACH** | Acción de primera clase | **No existe** |
| **Gestión explícita (renombrar/olvidar/ignorar)** | Sí (`taught`/`seen`/`ignored`) | Parcial: store acotado, sin UI de curado |
| **Interfaz** | Botón físico + cámara + micrófono | **MCP** hacia Alexa+ (voz natural) + dashboard |
| **Alcance temporal** | "Última vez que vi X" | Presente **y** pasado, con router determinista |
| **Razonamiento relacional** | Recuperación; sin grafo de relaciones | **Relaciones tipadas + contexto gradado** (más rico) |
| **Lenguaje** | Inglés (curso) | **Bilingüe es/en** |
| **Generación de respuesta** | Payload directo | Narración/síntesis bilingüe determinista |
| **Hardware** | Robot con Jetson/cámara (opcional) | Servidor + cámaras IP (Vivotek/Android) |

**Síntesis de la divergencia:** la referencia es **más profunda en el eje
objeto/enseñanza**; EchoMind es **mucho más profundo en el eje evento/
razonamiento** (relaciones, contexto, router, bilingüismo, abstención).

---

## 5. ¿EchoMind necesita incorporar TEACH / REMEMBER / RECALL para cumplir la visión original?

**Respuesta honesta: dos de los tres ya están; uno falta y es el que define la
visión.**

- **RECALL — ✅ ya existe.** `memory_recall`, `RecallEngine`, `last_seen`,
  `/api/recall`. EchoMind ya recupera recuerdos; la referencia no añade nada
  conceptualmente nuevo aquí.
- **REMEMBER — ✅ ya existe, con otro disparador.** `MemoryBridge` +
  `VectorMemoryService` persisten observaciones. EchoMind recuerda *lo que
  observó el sistema*; la referencia recuerda *lo que el usuario enseñó*. El
  verbo existe; **la fuente de la memoria es la diferencia**.
- **TEACH — ❌ no existe.** No hay forma de que el usuario **enseñe** un objeto,
  un nombre, una relación o una regla. Esta es la única pieza ausente y, a la
  vez, **la que nombra la visión "Memory-First enseñada por el usuario"**.

**Conclusión sobre la pregunta 5:** EchoMind **no necesita** reimplementar
RECALL ni REMEMBER —ya los tiene, y más ricos—. EchoMind **sí necesita TEACH**
*si y solo si* la visión objetivo es "memoria de objetos/conocimiento enseñado".
TEACH no es un quinto pilar decorativo: es un **cambio de modelo de datos** (de
evento → entidad enseñada).

**Riesgo a declarar:** importar TEACH sin decidir el modelo lleva a un sistema
híbrido incoherente (eventos auto-ingestados + objetos enseñados) sin reglas de
fusión. La pregunta central (§8) debe resolverse **antes** de tocar código.

---

## 6. Qué partes de EchoMind actual ya sirven para TEACH/objeto

Lo siguiente es **reutilizable tal cual** si se decidiera incorporar TEACH (sin
implementarlo ahora):

| Pieza actual | Por qué sirve para una memoria enseñada |
| ------------ | --------------------------------------- |
| `VectorMemoryService` + `embed_text` | Almacén + embedding ya operativos; el contrato `MemoryVectorStorePort` ya contempla payloads y filtros. |
| `MemoryVectorStorePort` | Punto de extensión declarado (Cosine, filters) — cabe un `kind` tipo `taught`. |
| `recall_engine` + `RecallPlan`/`RecallEngine` | `LAST_SEEN`, `SEARCH`, `AGGREGATE` sirven para "¿dónde/cuándo vi X?" sobre objetos enseñados igual que sobre eventos. |
| `memory_timeline` + `Episode` | Agruparía sightings de un objeto enseñado por tiempo. |
| `memory_spatial` + `memory_anchor` | Resolución/donde-degradación ya resuelta para `zone/location/camera`. |
| `relation.py` / `relation_rules.py` | Un objeto enseñado podría entrar como sujeto de relaciones (p. ej. co-ocurrencia con eventos). |
| `context.py` + `context_narrative.py` | Gradado y narración ya bilingües: reutilizables para narrar un recuerdo de objeto. |
| `query_router` (A7C) | Podría recibir un tercer dominio o un matiz `TEACH` sin tocar el resto. |
| `ResponseIntent` (A7D) | Ya tiene `LAST_SEEN_PLACE`, `RELATIONS`, `SPATIAL`: casi todo el render de un objeto enseñado está esbozado. |
| `MemoryBridge` | Precedente de "escritura al store desde otro origen"; un TEACH sería otro origen de escritura. |
| Determinismo + abstención + `trace` | Invariantes que una memoria enseñada también exigiría (sin `confidence` inventada). |

**En una frase:** el *motor* de EchoMind ya soporta TEACH; lo que falta es el
**modelo de entidad enseñada y la superficie de captura**.

---

## 7. Qué partes faltan (para TEACH / memoria de objetos)

| Falta | Descripción |
| ----- | ----------- |
| **Modelo de entidad enseñada** | No existe una entidad "objeto nombrado por el usuario" con identidad, alias y vistas de ejemplo. `MemoryRecord` es un evento, no una entidad. |
| **Superficie TEACH** | Ningún tool/acción para que el usuario enseñe: crear entidad, nombrarla, adjuntar ejemplos, confirmar. |
| **Reconocimiento visual por ejemplos** | No hay matching de un crop/objeto observado contra ejemplos enseñados (ni umbral calibrado). Hoy `detections` son etiquetas del detector. |
| **Embedding semántico real** | `embed_text` es term-frequency determinista (256-d), no un modelo CLIP/Nomic. Suficiente para eventos; flojo para identidad de objeto. |
| **Curado de memoria** | No hay renombrar/olvidar/ignorar dirigido por el usuario con trazabilidad. |
| **Reglas de fusión evento-objeto** | Si conviven, falta política: ¿un objeto enseñado se relaciona con eventos? ¿se narra junto? |
| **Gobernanza** | Consentimiento, privacidad de lo enseñado, límites del store por entidad. |
| **Calibración** | Un umbral de reconocimiento necesita dataset de validación — EchoMind no tiene hoy un banco de ejemplos visuales. |

---

## 8. Pregunta central

> **¿EchoMind debe seguir siendo un motor de memoria de eventos o evolucionar
> hacia una memoria de objetos y conocimiento enseñado por el usuario?**

**Evaluación honesta.**

**No es "o" excluyente en motor; sí lo es en modelo de datos.** El *motor*
(vector store edge, recall plan→engine, timeline, spatial, relaciones, contexto,
router, síntesis bilingüe determinista) es **agnóstico** al tipo de memoria: ya
sirve eventos y serviría objetos. La decisión real no es reescribir EchoMind,
sino **si se añade un segundo modelo de datos (entidad enseñada)** junto al de
eventos.

Tres posiciones honestas:

1. **Mantener solo eventos (no hacer nada).** Coherente, ya completo y de alto
   valor (safety, bilingüe, abstención, relaciones). Coste cero. Riesgo: no
   responde a la visión "enseñada por el usuario" ni a "¿dónde está mi cosa?",
   que es exactamente la pregunta que la referencia hace *su* producto.
2. **Solo objetos enseñados (pivotar).** Fiel al espíritu de la referencia, pero
   **desecharía** lo que hace único a EchoMind (razonamiento relacional,
   vigilancia proactiva, Alexa+, bilingüe). Mala relación coste/beneficio.
3. **Híbrido explícito: eventos (sistema) + entidades enseñadas (usuario) sobre
   un motor compartido.** Es la evolución natural y la que **responde a la
   visión original sin tirar nada**. Requiere, eso sí: (a) un modelo de entidad
   enseñada, (b) una superficie TEACH, (c) reglas de fusión evento↔objeto, y
   (d) gobernanza. Es la opción con más valor y más coste declarado.

**Recomendación:** **opción 3, pero por fases y solo si la visión de producto
exige "conocimiento enseñado".** El motor actual (permitir a EchoMind ser
también TEACH) es la base correcta; el trabajo ausente está acotado y es
identificable (≈§7). Si la visión se queda en "el hogar observa, recuerda y
razona", entonces **EchoMind ya la cumple y TEACH no es necesario** — y decirlo
honestamente también es una respuesta válida.

**Veredicto corto:** EchoMind **puede** evolucionar a memoria enseñada sin
rehacerse, porque su motor ya es de propósito general. **Debe** hacerlo solo si
la visión objetivo incluye conocimiento enseñado; en ese caso, TEACH es la pieza
obligatoria y la que justifica la evolución. No es un motor de eventos
*limitado*: es un motor de memoria aún **sin el verbo TEACH**.

---

## 9. Tabla resumen final

| Pregunta | Respuesta honesta |
| -------- | ----------------- |
| Problema de la referencia | Memoria de **objetos** con identidad **enseñada por el usuario**, offline. |
| Problema de EchoMind | Memoria de **eventos del hogar** para **Alexa+**, offline, con razonamiento. |
| Coinciden en | Motor vector edge, on-device, sin LLM en memoria, espaciotemporal, sin alucinación. |
| Divergen en | **Quién puebla** (usuario vs sistema) y **unidad** (objeto vs evento). |
| TEACH | **Falta.** |
| REMEMBER | **Existe** (otro disparador). |
| RECALL | **Existe** (más rico: relaciones, contexto, router). |
| Ya sirve para ello | Todo el motor: store, plan/engine, timeline, spatial, relaciones, contexto, síntesis, router. |
| Falta | Modelo de entidad enseñada, superficie TEACH, reconocimiento por ejemplos, embedding semántico, curado, fusión evento-objeto, gobernanza. |
| Motor de eventos o memoria enseñada | **Motor agnóstico**: puede ser ambas. Evolucionar a híbrido (eventos + entidades enseñadas) **si** la visión exige conocimiento enseñado. |

---

*Evaluación sin código, sin commits. Documento generado en la raíz del repositorio.*
