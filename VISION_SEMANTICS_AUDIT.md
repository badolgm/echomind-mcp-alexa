# VISION_SEMANTICS_AUDIT.md

## Título
SPRINT ECHOMIND V2 — VISION SEMANTICS AUDIT

## Objetivo
Determinar qué puede reconocer EchoMind hoy (percepción) vs qué no puede, identificando etiquetas existentes/ausentes, origen de las etiquetas, límites actuales y brechas para responder a preguntas sobre objetos concretos ("¿Viste mi cargador?", "¿Viste mis llaves?", "¿Dónde está mi celular?").

## Alcance
Análisis de solo lectura (NO implementación, NO código modificado, NO commits). Se analiza:
1. Etiquetas reconocibles hoy (mapas de etiquetas en el código)
2. Origen del pipeline de etiquetas (fuentes de detección)
3. Qué etiquetas NO existen
4. Límites actuales
5. Consultas imposibles hoy
6. Requisitos para evolucionar
7. Relación con sc-on-device-ai-memory

## 1. Capacidades visuales actuales (mapa de etiquetas)

### 1.1 Clasificador de intenciones (memory_intent._LABEL_TERMS)
Ubicación: `src/domain/services/memory_intent.py`

Etiquetas canónicas y términos de búsqueda:
- **PERSON_ELDERLY**: persona mayor, personas mayores, anciano, anciana, abuelo, abuela, elderly, senior, grandfather, grandmother
- **GATE_OPEN**: reja, portón, porton, cancela, gate, front gate
- **DOOR_OPEN**: puerta, door, front door
- **PET**: mascota, mascotas, perro, perros, gato, gatos, animal, pet, pets, dog, dogs, cat, cats
- **PERSON**: persona, personas, hombre, mujer, gente, person, people, someone, human
- **MOTION**: movimiento, motion, movement
- **SMOKE**: humo, smoke
- **FIRE**: fuego, incendio, fire
- **FALL DETECTED**: caída, caida, fall, fall detected

Total: **9 etiquetas canónicas**.

### 1.2 Descriptores conversacionales (memory_converse)
Ubicación: `src/infrastructure/adapters/mcp/memory_resolvers.py`

**_DESCRIPTORS_ES/EN** incluyen: PERSON, PERSON_ELDERLY, PET, PET_ESCAPING, GATE_OPEN, DOOR_OPEN, MOTION, SMOKE, FIRE, PACKAGE, INTRUDER, FALL DETECTED (12). PET_ESCAPING, PACKAGE, INTRUDER no están en _LABEL_TERMS del clasificador determinista.

### 1.3 Watchdog/ambient watch
Ubicación: `src/infrastructure/services/ambient_watch_service.py`

**_LABEL_ES** emitidas: SMOKE, FIRE, TEMP_RISING, GATE_OPEN, DOOR_OPEN, PET_ESCAPING, MOTION. _ALERT_TRIGGERS: GATE_OPEN, PET_ESCAPING, MOTION.

### 1.4 Síntesis de respuestas
Ubicación: `src/domain/services/recall_synthesis.py`

Mapeo label->noun (ES/EN): PET, PERSON, PERSON_ELDERLY, GATE_OPEN, DOOR_OPEN, SMOKE, FIRE, FALL DETECTED, MOTION.

## 2. Pipeline que produce etiquetas (origen de percepción)

| Canal | Componente | Origen | Etiquetas emitidas |
|---|---|---|---|
| Watchdog | ambient_watch_service.py | Motion delta + sensores simulados (heurístico/determinista). | SMOKE, FIRE, TEMP_RISING, GATE_OPEN, DOOR_OPEN, PET_ESCAPING, MOTION |
| Eventos camera_alert | memory_bridge.py | Consume EventHub `camera_alert`. Persiste detections arbitrarias si HIGH/CRITICAL. | Arbitrario (lo que llegue) |
| Adaptadores cámara | vivotek_adapter.py, http_phone_camera_adapter.py | Exponen endpoints /detections (interfaz genérica). | Arbitrario según fuente |
| Memoria | memory_service.py | Solo consulta/persiste. No genera etiquetas. | N/A |

Conclusión: mayoritariamente heurístico/simulado. El vocabulario para **comprensión estructurada** está acotado; el vocabulario para **almacenamiento** es flexible.

## 3. Etiquetas que NO existen

Para "¿Viste mi cargador?", "¿Viste mis llaves?", "¿Dónde está mi celular?":

| Objeto | Candidatas | Presente | Estado |
|---|---|---|---|
| Cargador/cable | CHARGER, CABLE, CHARGING_CABLE | NO | Ausente |
| Llaves | KEYS, KEY, KEYCHAIN | NO | Ausente |
| Celular/móvil | PHONE, MOBILE, CELLPHONE, SMARTPHONE | NO | Ausente |
| Ratón/teclado/monitor | MOUSE, KEYBOARD, MONITOR, LAPTOP, COMPUTER | NO | Ausente |
| Reloj/gafas/bolso | WATCH, GLASSES, BAG, BACKPACK | NO | Ausente |

## 4. Límites actuales

| Límite | Explicación |
|---|---|
| Vocabulario cerrado | ~9 etiquetas canónicas reconocidas por clasificador determinista. |
| Semántica vs texto libre | Sin etiqueta conocida → SEARCH (embeddings). Explica respuestas irrelevantes basadas en similitud. |
| Sin detector genérico | No hay YOLO/COCO/ONNX/TFLite evidente. Watchdog es heurístico (motion delta). |
| Percepción simulada | Mayoría de etiquetas provienen de lógica determinista o eventos. |
| Desacoplamiento detección/comprensión | Se pueden almacenar etiquetas nuevas, pero clasificador no las mapea. |
| Temporalidad "ahora" | Requiere snapshot vivo; sin provider → abstención honesta. |

## 5. Consultas imposibles hoy

| Consulta | Razón | Brecha |
|---|---|---|
| "¿Viste mi cargador?" | Sin CHARGER, sin fuente de detección, caen a SEARCH irrelevante. | Vision + Sensor/Data |
| "¿Viste mis llaves?" | Sin KEYS. | Vision + Sensor/Data |
| "¿Dónde está mi celular?" | Sin PHONE. | Vision + Sensor/Data |
| "¿Viste un cargador en el salón?" | Sin vocabulario/filtrado por etiqueta. | Vision |

## 6. Requisitos para evolucionar

| Nivel | Necesidad | Detalles |
|---|---|---|
| 1. Fuente de detección | Detector de objetos con clases relevantes | YOLOv8/YOLOE/RT-DETR u otro on-device generando CHARGER/KEYS/PHONE normalizados. |
| 2. Normalización | Mapeo detector→canónico | Etiquetas estables consistentes con esquema actual. |
| 3. Extender vocabulario | Ampliar _LABEL_TERMS + descriptores | Términos ES/EN para activar LAST_SEEN/SUMMARY estructurados. |
| 4. Persistencia | Emitir camera_alert con nuevas detections | MemoryBridge ya flexible; requiere fuente. |
| 5. Synthesis/UX | Añadir descriptores naturales | Patrón ya existente. |

Crítico: sin fuente de detecciones no hay registros aunque se amplíe vocabulario.

## 7. Relación con sc-on-device-ai-memory

Inspiración conceptual (teach/remember/recall), sin copia. Coincidencias: vector edge, on-device, evidencia-first, espaciotemporal. Diferencia: recall determinista sobre memoria episódica observada por sensores. Para razonamiento sobre recuerdos, relevante es recall-centric + evidencia-first (docs existentes). Añadir percepción extendida afecta "remember" (qué se almacena), no el núcleo de "recall".

## 8. Conclusión

**Puede observar hoy:** PERSON, PERSON_ELDERLY, PET (perro/gato/mascota), MOTION, SMOKE, FIRE, GATE_OPEN, DOOR_OPEN, FALL DETECTED, y variantes en descriptores (PET_ESCAPING, PACKAGE, INTRUDER). Mayoritariamente heurístico/simulado.

**No puede observar todavía:** objetos personales/genéricos (cargador, llaves, teléfono/celular, ratón, teclado, monitor, mochila, etc.). No hay detector con esas clases ni mapeo completo en clasificador.

**Brecha real:** Percepción (vision semantics) + vocabulario de etiquetas. Solución requiere fuente de detección con clases extendidas + extensión coherente de vocabulario canónico. Ampliar vocabulario sin fuente de detecciones es insuficiente.
