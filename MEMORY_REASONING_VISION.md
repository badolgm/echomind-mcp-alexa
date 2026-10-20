# MEMORY_REASONING_VISION.md — Sprint Conversational Reasoning (Visión Evolutiva)

**Fecha:** 2026-10-11  
**Ámbito:** Análisis técnico (sin implementación, sin cambios de código, sin arquitectura nueva). Referencia conceptual: `teach/remember/recall` (sc-on-device-ai-memory), sin copiarla.

---

## 1. ¿Qué limita actualmente el razonamiento?

El `MemoryConverse` actual resuelve por **routing determinista** (clasificación de intención → resolver especializado). Limitaciones clave:

1. **Jerarquía "clasifica → ejecuta"** (pipeline rígido). La pregunta se reduce a un `MemoryIntentType` único antes de acceder a la memoria. Esto obliga a encajar formas coloquiales en enums fijos.
2. **Acoplamiento temprano a estructura**. El clasificador extrae `label`, `hours`, `risk`, `location` como campos obligados para decidir el camino. Preguntas vagas o compuestas pierden matices ("última hora de detección de movimiento" no encaja bien → cae a SEARCH).
3. **Semántica binaria por tipo**. `LAST_SEEN` busca un único label canónico; `SEARCH` hace búsqueda por texto libre. No existe un estadio intermedio: **inferir qué recordar, por qué y con qué alcance** a partir de la pregunta + contexto.
4. **Poca composición**. No puede razonar sobre relaciones ("¿hubo movimiento antes o después de la caída?") porque cada ruta devuelve una narrativa especializada (última detección, resumen, conteo...) aislada.
5. **Dependencia de plantillas**. Aunque las narrativas son deterministas (sin LLM), el **flujo de decisión** es mayoritariamente reglas + plantillas. El razonamiento (deducción, filtrado temporal, generalización) no se modela como "operaciones sobre memoria + contexto", sino como "dispatch por intención".
6. **Contexto live subutilizado**. `current_state` se usa solo en `CURRENT_STATE` (y parcialmente en resumen). No participa como evidencia para interpretar ambigüedad ("¿qué ocurre ahora?" vs "¿qué pasó?") junto al histórico.
7. **El "query" pasa directo a búsqueda** cuando no encaja intención. `SEARCH` resuelve por similitud/recuperación pero **no sintetiza una respuesta enfocada** (devuelve listados). Ahí aparece la diferencia entre *recuperar* y *responder razonadamente*.

---

## 2. ¿Qué partes son reglas?

Dominio puramente determinista (reglas explícitas):

- **`MemoryIntentClassifier`**: reglas de patrones (keywords, hints ES/EN), extracción de campos, heurísticas de idioma. Totalmente basado en reglas.
- **Mapeos de etiquetas** (`_LABEL_TERMS`, descriptores ES/EN): taxonomía fija + sinonimia.
- **Rutas de dispatch** (`MemoryConverse.resolve`): árbol if/elif por `MemoryIntentType`. Reglas de decisión.
- **Narrativas estructuradas** (`_events_narrative`, `_current_state_answer`, `_relative_time`, descripciones): plantillas con relleno de campos.
- **Validaciones/normalizaciones** (`lang`, límites, hours por defecto): reglas.

**Conclusión:** Clasificación + enrutado + formateo = **capa de reglas** (determinista, trazable).

---

## 3. ¿Qué partes son memoria?

La capa de almacenamiento/recuperación:

- **`VectorMemoryService`**: `store_memory`, `last_seen`, `search_memory`, `label_counts`, `count_events`, `recent_high_risk_events`, `recent_critical_events`, `top_events`, `count_occurrences`. Operaciones puras sobre registros (`MemoryRecord`) + índices (vector/hash). **Esto es memoria (datos + índices + operaciones de consulta)**.
- **`MemoryBridge`**: transforma eventos (detecciones) en `MemoryRecord`, aplica coalescing/episodios, persiste vía `VectorMemoryService`. Memoria episódica/ambiental.
- **`MemoryRecord`**: representación estructurada del recuerdo (timestamp, location, risk, detections, model_analysis, scores...). **Unidades de recuerdo**.
- **Seed/demo memory**: corpus determinista para validación.

**Memoria = lo que se recuerda (hechos), no cómo se interpreta la pregunta.**

---

## 4. ¿Qué partes podrían delegarse al modelo?

**Sin romper determinismo/trazabilidad**, la delegación debería ser **selectiva y acotada** (boundary claro). Áreas candidatas (conceptuales, no propuesto implementar):

1. **Interpretación semántica abierta** (desambiguación). En lugar de forzar enum: dada pregunta ambigua ("última hora de detección..."), el modelo podría proponer un `RecallPlan` estructurado (tipo: `last_seen`, target: `MOTION`, window: `1h`, location: opcional) con esquema estricto (JSON validado). **Solo interpretación, nunca generación libre de hechos**.
2. **Síntesis narrativa a partir de resultados**. Actualmente `search` devuelve listados. Podría delegarse la **síntesis** (ordenar, resumir, conectar hechos recuperados) manteniendo **retrieval determinista** (memoria fija). Principio: *retrieve deterministically, synthesize constrained*.
3. **Razonamiento temporal/compositivo ligero**. Ej.: "¿hubo movimiento antes de la caída?" → requiere ordenar eventos, comparar timestamps. Puede delegarse como **plan de consulta** (qué queries ejecutar sobre memoria) vs respuesta final. Mejor delegar **planificación** (structured tool calls) que narrativa libre.
4. **Normalización de lenguaje natural** ("teach/remember/recall"). Inspiración conceptual:
   - **Teach**: aprender preferencias/definiciones (poca relevancia aquí)
   - **Remember**: consolidar/etiquetar recuerdos (ya hace MemoryBridge)
   - **Recall**: recuperar + razonar sobre recuerdos. Diferencia clave: *recall* no es "clasificar intención" sino **construir una respuesta basada en evidencia recuperada + contexto**.
5. **Manejo de ambigüedad multietiqueta** ("¿qué pasó con persona y reja?") → componer filtros sobre memoria (no forzar label único).

**Regla de delegación segura:** delegar **interpretación/planificación/síntesis acotada**; **nunca** delegar recuperación cruda o permitir alucinación de eventos no presentes en `VectorMemoryService`. Respuestas deben citar/derivarse de recuerdos existentes.

---

## 5. ¿Cómo mantener determinismo y trazabilidad?

Principios para evolución sin perder garantías actuales (208 tests, QFP, offline):

1. **Separación estrita Retrieve vs Reason**. 
   - `MemoryService` (ports/adapters existentes): **siempre determinista** (consultas estructuradas). No tocar.
   - Capa reasoning: opcional, con **salida estructurada** (JSON schema) validada. Si falla parsing → fallback a ruta determinista actual.
2. **Determinismo por defecto, razonamiento opcional**. Mantener `MemoryConverse` determinista como **camino feliz/verificado**. Evolucionar añadiendo un `Reasoner` con **feature flag** (o solo conceptual). Nunca reemplazar por completo sin fallback.
3. **Evidence-first**. Toda afirmación debe poder trazarse a `MemoryRecord`(s) recuperados (IDs/timestamps/labels). Respuesta razonada debe listar evidencia recuperada (o derivar exclusivamente de ella). Evitar inferencias no soportadas por memoria.
4. **Constrained generation**. Si se delega al modelo: `temperature=0`, `max_tokens` bajo, **response_format=JSON** (tool/structured output), sin sistema prompt abierto. Solo campos permitidos. Validación pydantic estricta.
5. **Plan-execute (structured reasoning)**. Inspirado en "recall": en lugar de generar respuesta narrativa libre, el modelo genera un **plan de recuperación** (`steps: [last_seen(label=MOTION), search(...)]`, filtros, orden) → ejecuta contra memoria **determinista** → sintetiza con plantilla acotada. Esto mantiene trazabilidad (plan + resultados + síntesis).
6. **No romper gates**. Mantener tests existentes (clasificación + resolvers + converse) verdes. Añadir tests de trazabilidad (evidences presentes).
7. **Offline-first / QFP compatible**. Si modelo no disponible (QFP), forzar ruta determinista 100%. El razonamiento no debe ser requisito para demo (GO PARA VIDEO actual).

---

## 6. ¿Cómo acercarnos a una Alexa que razona sobre recuerdos (sin plantillas)?

Pasar de **"responder según tipo"** a **"responder según evidencia + pregunta + contexto"**:

### 6.1 Cambio conceptual: Recall-centric (no intent-centric)

- **Intent-centric** (actual): `classify(query) → intent → resolver`. Pregunta → categoría.
- **Recall-centric** (evolutivo): `understand(query, context) → recall_plan → retrieve(memory) → synthesize(answer, evidence)`. Pregunta + contexto → **qué recuperar y cómo razonar**.

Diferencia: el razonamiento ocurre **después** de (o durante) la recuperación, no **antes** para elegir ruta única.

### 6.2 Principios (teach/remember/recall)

- **Remember**: consolidar episodios (MemoryBridge ya cubre: coalescing, episodio). Bien posicionado.
- **Recall**: no es búsqueda keyword, es **reconstrucción contextual** ("¿qué pasó alrededor de X?"). Requiere recuperar conjunto relevante + ordenar temporalmente + conectar.
- **Teach**: opcional (preferencias). No necesario ahora.

Enfoque: evolucionar `MemoryConverse` hacia **recall**: construir respuesta desde **conjunto de recuerdos recuperados + estado actual + ventana temporal inferida**, con síntesis mínima guiada (no plantillas rígidas por tipo).

### 6.3 Aproximación incremental (sin romper arquitectura)

1. **Preservar capa determinista**. Mantener `MemoryIntentClassifier` + resolvers. Úselos como **heurísticas rápidas** o **fallback**.
2. **Añadir capa de recuperación unificada**. Un único `recall(query, context)` que devuelve `{evidence: [MemoryRecord], plan: {...}, confidence: ...}` (determinista por defecto: puede usar búsqueda + filtros inferidos). Esto unifica SEARCH/LAST_SEEN.
3. **Síntesis basada en evidencia (template-light)**. Generar narrativa describiendo **hechos recuperados** (qué, cuándo, dónde, riesgo) con conectores mínimos, **sin inventar eventos ausentes**. Ej.: agrupar por episodio/label, ordenar cronológicamente, destacar último/reciente/crítico.
4. **Inferir alcance (ventana) dinámicamente**. En lugar de `hours` fijo por tipo, inferir ventana desde pregunta ("última hora" → 1h, "hoy" → 24h, "recientemente" → 6–24h) **sin regex rígidos** (podría hacerse por palabras clave mínimas o por plan estructurado). Pero mantener fuera de alcance implementar ahora.
5. **Razonamiento composicional**. Permitir múltiples recuperaciones ligeras y **combinar** (último MOTION + último FALL) antes de sintetizar. Esto supera "un label/un tipo".

### 6.4 Equilibrio deseado

- **Determinismo**: recuperación + rutas base (garantizado, tests verdes)
- **Trazabilidad**: respuesta derivada exclusivamente de `evidence` (listado recuperado)
- **Naturalidad**: síntesis menos rígida, más conversacional, sin abandonar plantillas preescritas
- **Alexa que razona sobre recuerdos**: no "clasifica y rellena plantilla", sino **recupera evidencia relevante → organiza → responde con base en hechos recordados**. Ahí reside la evolución hacia razonamiento sobre memoria.

---

## Conclusión

El límite actual no es la memoria (buena, estructurada) ni los resolvers, sino el **punto de decisión temprano (intent-centric)**. Evolucionar hacia **recall-centric + evidence-first + síntesis acotada** permite razonamiento sobre recuerdos sin convertirlo en LLM libre, manteniendo determinismo y trazabilidad. El enfoque `teach/remember/recall` apunta a eso: **recall** = recuperar + razonar sobre lo recordado (evidencia), no clasificar preguntas.