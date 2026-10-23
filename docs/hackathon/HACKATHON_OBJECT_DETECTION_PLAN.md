# HACKATHON_OBJECT_DETECTION_PLAN.md

## Objetivo
Encontrar el camino MÁS CORTO para que EchoMind reconozca objetos reales (cargador, llaves, celular, mouse, teclado) y pueda responder con evidencia persistida. Sin arquitectura nueva, sin roadmap estratégico, sin docs extensos. Solución ejecutable.

## Estado actual (crítico)
- EchoMind recuerda bien (recall/timeline/relations/context). 
- No reconoce objetos cotidianos. Preguntas devuelven MOTION/PERSON/PET o irrelevantes.
- Existe pipeline para recibir detecciones: `camera_alert` → `MemoryBridge` → `MemoryRecord.detections` (flexible) → `VectorMemoryService` → `RecallEngine`.
- Único productor de `camera_alert`: `AmbientWatchService` (heurístico). Sin detector de objetos.
- Clasificador determinista limitado a ~9 etiquetas; ampliar vocabulario es trivial si llegan detecciones.

## 1. ¿Qué detector concreto podemos integrar en el menor tiempo posible?

| Opción | On-device | Velocidad integración | Pesos | CPU/GPU | Precisión objetos cotidianos | Notas |
|---|---|---|---|---|---|---|
| **YOLOv8n (Ultralytics)** | Sí (PyTorch/ONNX) | **Más rápido** | ~6MB | Funciona en CPU, mejor con GPU | Bueno (COCO: cell phone, keyboard, mouse, laptop, tv/monitor). Keys/charger no son clases COCO directas. | Más maduro, API simple, fácil emitir labels. |
| **YOLO11n (Ultralytics)** | Sí | Similar a v8 | ~5-6MB | Similar | Ligeramente mejor | Muy rápido integrar. |
| **YOLOE** | Sí | Más lento integrar | Mayor/descarga dinámica | Más pesado | Mejor para vocabulario abierto ("charger", "keys") | Ideal pero más complejo para hackathon. |
| **RT-DETR** | Sí | Más lento | Variable | Variable | Bueno | Menor ecosistema para hackathon. |

**Recomendación única:** **YOLOv8n** (o YOLO11n). Priorizar clases COCO cubiertas: `cell phone`→`PHONE`, `keyboard`→`KEYBOARD`, `mouse`→`MOUSE`, `laptop`/`tv`→`MONITOR`. Para KEYS/CHARGER aceptar limitación inicial o usar YOLOE después.

## 2. ¿Cuál requiere menos cambios sobre la arquitectura actual?

**GANADOR:** Añadir **servicio independiente + wiring opcional**. 

- **NO** modificar `AmbientWatchService`
- **NO** modificar adaptadores cámara (usan contrato existente)
- **SÍ** crear `ObjectDetectionService` nuevo
- **SÍ** ampliar vocabulario en `memory_intent.py` (aditivo)
- **SÍ** cablear en `main.py` (opcional)

## 3. ¿Cómo emitir CHARGER, PHONE, KEYS, MOUSE, KEYBOARD, MONITOR como detections reales?

### Mapeo COCO → EchoMind
| COCO class | EchoMind label | Estado |
|---|---|---|
| `cell phone` | `PHONE` | Cubierto |
| `mouse` | `MOUSE` | Cubierto |
| `keyboard` | `KEYBOARD` | Cubierto |
| `laptop` | `MONITOR`/`LAPTOP` | Cubierto |
| `tv` | `MONITOR` | Cubierto |
| `keys`/`charger` | `KEYS`/`CHARGER` | **No cubierto por COCO** (requiere YOLOE o heurística) |

### Emisión
Publicar `camera_alert` vía `EventHub` con:
```json
{
  "kind": "camera_alert",
  "tool": "object_detector",
  "status": "HIGH",
  "risk": "HIGH",
  "location": "camera",
  "source": "live",
  "detections": [{"label": "PHONE", "confidence": 0.8}],
  "announcement": "...",
  "model_analysis": "...",
  "ts": now
}
```

**MemoryBridge** lo consumirá sin cambios. Coalescing funciona por (location, labels).

## 4. ¿Cómo reutilizar MemoryBridge, MemoryRecord, RecallEngine sin modificarlos?
- **MemoryBridge**: Filtra HIGH/CRITICAL, acepta detecciones arbitrarias, coalesce. **Sin cambios.**
- **MemoryRecord**: `detections` flexible. **Sin cambios.**
- **VectorMemoryService**: Almacena. **Sin cambios.**
- **RecallEngine/Planner/Synthesis**: Funcionan si etiqueta reconocida. **Ampliar `_LABEL_TERMS`** en `memory_intent.py` (aditivo) para habilitar LAST_SEEN/filtrado estructurado.
- **Descriptores/synthesis**: Opcionales.

## 5. MVP mínimo para impresionar al jurado
**Alcance mínimo:** PHONE, MOUSE, KEYBOARD, MONITOR/LAPTOP → funcional en 1-2h.

### Pasos exactos (ejecutables)
1. **Instalar deps**: `.\.venv\Scripts\pip install ultralytics opencv-python-headless`
2. **Crear servicio**: `src/infrastructure/services/object_detection_service.py`
   - Consumir `CameraFrameSource.get_frame()`
   - Cargar YOLOv8n (auto-descarga `yolov8n.pt`)
   - Inferir, filtrar confianza >= 0.5
   - Mapear COCO→labels
   - Publicar `camera_alert` HIGH vía EventHub (throttling cada ~10s o cada N ticks)
3. **Ampliar vocabulario**: `src/domain/services/memory_intent.py` → añadir PHONE/MOUSE/KEYBOARD/MONITOR con sinónimos ES/EN
4. **Cablear**: `src/main.py` instanciar `ObjectDetectionService` (opcional, sin romper existente)
5. **Probar**: "¿Viste mi mouse/celular/teclado?" → debe usar LAST_SEEN con evidencia

## Recomendación única
**YOLOv8n + servicio independiente + ampliar _LABEL_TERMS.**

- **Coste:** ~6MB modelo + deps mínimas, CPU viable
- **Riesgo:** Bajo (100% aditivo, no toca recall/memoria/700 tests)
- **Complejidad:** Baja-Media
- **Impacto:** Alto (resuelve casos reales mostrados)

**Veredicto:** Ruta más rápida y robusta. Empezar por PHONE/MOUSE/KEYBOARD/MONITOR. KEYS/CHARGER quedan fuera de alcance COCO pero el patrón queda listo para añadir después. Eso es suficiente para demo hackathon.
