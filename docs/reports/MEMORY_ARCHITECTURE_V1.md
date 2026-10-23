# MEMORY_ARCHITECTURE_V1.md

> Sprint Memoria V1 — capa de memoria vectorial local inspirada en **Qdrant Edge**
> para **EchoMind MCP Alexa**.
> Scope: diseño + `memory_service.py` + tests aislados. **Sin** commits, push ni Docker.

## 1. Contexto

El guardián autónomo (watchdog + visión + EventHub + Dashboard) emite eventos
`camera_alert` en tiempo real. Para que Alexa pueda responder preguntas
*históricas* ("¿hubo movimiento ayer en el patio?", "¿cuándo se abrió la reja
por última vez?", "¿el abuelo necesitó ayuda hoy?"), el sistema necesita una
**memoria persistente consultable**.

Inspirado en Qdrant Edge (vector store embebible, local, sin servidor), esta
V1 implementa un **store vectorial en memoria** con embeddings deterministas
(hash de términos) que reproduzca el contrato de Qdrant sin dependencias.

## 2. Contrato canónico: el evento `camera_alert`

El EventHub publica eventos con esta forma (misma taxonomía del watchdog y del
resolver de visión):

```json
{
  "kind": "camera_alert",
  "tool": "ambient_watchdog",
  "risk": "HIGH",
  "location": "patio",
  "source": "live",
  "detections": [
    {"label": "PET_ESCAPING", "confidence": 0.85},
    {"label": "GATE_OPEN", "confidence": 0.9}
  ],
  "motion_score": 0.72,
  "announcement": "Atención: Detecciones: la reja está abierta, la mascota intenta escapar. Actúa ya...",
  "ts": 1700000000.0
}
```

### Mapeo evento → `MemoryRecord`

| evento `camera_alert` | `MemoryRecord`      |
|-----------------------|---------------------|
| `ts`                  | `timestamp`         |
| `location`            | `location`          |
| `source` / `tool`     | `source`            |
| `detections`          | `detections`        |
| `risk`                | `risk`              |
| `announcement` + análisis del modelo | `model_analysis` |
| nuevo UUID             | `id`                |

`MemoryRecord` (campos canónicos):

```python
@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    timestamp: float
    location: str
    source: str
    detections: tuple[dict[str, object], ...]
    risk: str
    model_analysis: str
```

## 3. Almacenamiento (V1 — local en memoria)

- `VectorMemoryService` mantiene dos índices:
  - `_records: dict[id -> MemoryRecord]` (la fuente de verdad),
  - `_vectors: dict[id -> embedding]` (vectores L2-normalizados).
- **Embedding determinista** `embed_text()`: tokeniza en términos
  `[a-z0-9]+`, agrupa por `sha256(term)`, produce un vector de frecuencia de
  256 dimensiones y lo normaliza. Sin modelo, sin red, reproducible entre
  procesos (crucial: `hash()` de Python no es estable entre procesos).
- Similitud = producto punto (coseno sobre vectores normalizados).
- Límite de capacidad configurable (`max_records`); al llenarse se lanza
  `MemoryError` (el productor decide evictar vía `forget_memory`).
- Las métricas/detecciones alimentan el *query* del punto; el texto
  semántico de búsqueda (análisis del modelo + etiquetas + ubicación) define
  el vector.

## 4. Recuperación

API pública (contrato de capabilities):

| Capability          | Firma                                                     | Uso |
|---------------------|-----------------------------------------------------------|-----|
| `store_memory`      | `store(record: MemoryRecord) -> MemoryRecord`              | persistir un evento |
| `search_memory`     | `search(query, limit, min_score, location?, risk?)`        | top-k semántico |
| `last_seen`         | `last_seen(location?, source?)`                            | última observación |
| `forget_memory`     | `forget(record_id) -> bool`                                | borrar / TTL |

Filtros por `location` y `risk` replican los **payload filters** de Qdrant
(equality sobre payload, aplicados antes del ranking por score).

## 5. Consultas Alexa (flujo)

```
Alexa: "¿Cuándo se abrió la reja por última vez?"
   │
   ▼  intent classify → memory_search ("la reja quedó abierta")
   ▼  search_memory(..., location=None, risk=HIGH)
   ▼  top-k → se formatea la respuesta con el top record:
        "La reja se detectó abierta hace 2h en el patio (riesgo alto)."
```

Variantes guiadas por el label del intent:
- `memory_last_seen` → `last_seen(location="patio")`.
- `memory_search` → `search_memory(query)`.
- `memory_forget`/TTL → `forget_memory(id)`.

Todas las respuestas se originan en memoria local → latencia < 1 ms, y el
flujo funciona aun con la nube apagada (Quota Fallback Protocol).

## 6. Integración futura con Qdrant (diseño, sin implementar)

Contrato definido en `MemoryVectorStorePort`:

| Qdrant Edge          | Contrato                    |
|----------------------|-----------------------------|
| point_id             | `MemoryRecord.id`           |
| vector               | `embed_text(record)`        |
| payload              | campos de `MemoryRecord` salvo `id` |
| distancia            | `Cosine`                    |
| filtros              | equality payload: `location`, `risk`, `source` |
| top-k                | `limit` (score descendente) |

Darío de migración (cuando se implemente `QdrantMemoryStore`):
1. Crear colección `echo_memories` (`Cosine`, dim 256).
2. `upsert(point_id, vector, payload)` en `store_memory`.
3. `query(vector, limit, filters)` en `search_memory` (el `min_score` se
   traduce al filtro `score ≥ min_score` de Qdrant).
4. `delete(point_id)` en `forget_memory`.
5. `VectorMemoryService` queda como **fallback** local: misma API, cero
   infraestructura.

## 7. Decisiones y límites (V1)

- **No** se tocan `sensor_bus.py`, `ambient_watch_service.py`,
  `tool_resolvers.py` ni `dashboard.html`.
- **No** se modifican los tests existentes; solo se añade
  `tests/unit/test_memory_service.py` (aislado).
- Embeddings de bolsa de términos: suficiente para categorías canónicas y
  textos cortos; un embedder externo (Bedrock embeddings) mejoraría semántica
  sin cambiar la API.
- Persistencia duradera real (disco/S3) queda fuera de V1: la memoria vive
  en proceso; `forget_memory`/TTL podrán purgar por antigüedad.

## 8. Archivos del sprint

```
Memory_ARCHITECTURE_V1.md                        (documento de arquitectura)
src/infrastructure/services/memory_service.py    (MemoryRecord + VectorMemoryService + Port)
tests/unit/test_memory_service.py                (tests aislados)
```