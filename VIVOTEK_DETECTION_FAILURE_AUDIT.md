# VIVOTEK_DETECTION_FAILURE_AUDIT.md

## Objetivo
Auditar por qué la cámara Vivotek FD8367 entrega imagen pero **no genera detecciones útiles** (no detecta reja/puerta abiertas, no genera eventos, dashboard permanece LOW/Sin detecciones activas) a pesar de cambios visuales.

## Alcance
Análisis puramente de solo lectura. Sin implementación, sin cambios de código, sin commits ni push.

## 1. Cómo entra el frame Vivotek
- **Adaptador**: `src/infrastructure/adapters/iot/vivotek_adapter.py` → `VivotekCameraAdapter`
  - `get_frame()` usa caché (`cache_ttl=1.5s`). Si hay frame cacheado válido, lo devuelve directamente.
  - Llama a `_fetch_live()` que hace `GET {scheme}://{host}:{port}{snapshot_path}` (por defecto `http://192.168.40.10:80/cgi-bin/viewer/video.jpg`)
  - Si HTTP OK con contenido imagen → `CameraFrame(data=content, content_type=image/*, source="live", captured_at=now)`
  - Si falla/timeout → `_fallback()` sirve frame PNG determinista `source="fallback"`, `content_type="image/png"`, registra `last_error`
- **Rutas**: `mount_camera_routes()` expone `/api/cam/vivotek/snapshot` y `/api/cam/vivotek/detections`. El watchdog usa el objeto `CameraFrameSource` directamente (duck-typed).
- **Evidencia tests**: `test_get_frame_returns_live_frame_from_camera` confirma que con transporte live se obtiene `source="live"`. `test_get_frame_falls_back_to_clean_frame_when_camera_down` confirma fallback a PNG.

**Conclusión**: El frame puede entrar como `live`, pero el hecho de obtener `live` **NO garantiza** que se generen detecciones.

## 2. Cómo se calcula motion_score
- **Componente**: `src/infrastructure/services/ambient_watch_service.py` → `AmbientWatchService.tick()`
  - Obtiene frame: `frame = await self._camera.get_frame()`
  - Si `frame.source == "live"`: `motion = frame_delta_ratio(self._prev_payload, frame.data)`
  - Almacena `self._prev_payload = frame.data` (se guarda SIEMPRE el payload actual para comparar con siguiente tick)
  - Aplica confirmación por rachas: `if motion >= self._motion_threshold: self._motion_streak += 1 else: self._motion_streak = 0`
  - `confirmed_motion = motion if self._motion_streak >= MOTION_CONFIRMATION_FRAMES else 0.0` (MOTION_CONFIRMATION_FRAMES = 1)
  - Pasa `confirmed_motion` a `predict_ambient_state()`

**motion_score** en el estado: `watch.last_state["motion_score"] = round(motion, 4)` (usa el `motion` bruto del tick, no necesariamente el confirmado).

## 3. Cómo se calcula frame_delta_ratio
- **Función**: `frame_delta_ratio(first: bytes, second: bytes)`
  - Si `not first or not second`: `0.0`
  - Intenta decodificar con PIL: convierte a escala de grises, redimensiona a `(48,48)`, compara píxeles byte-a-byte con umbral `MOTION_PIXEL_DIFF_THRESHOLD = 20`
    - Cuenta pixels con `abs(pixels_a[index] - pixels_b[index]) >= MOTION_PIXEL_DIFF_THRESHOLD`
    - Retorna `changed / checked`
  - Si falla PIL/decodificación: fallback por muestreo (`samples=4096`) sobre `_image_payload()` con umbral `abs(...) >= 4`
- **_image_payload()**: 
  - Para JPEG (`\xff\xd8`): recorta desde `SOS (\xff\xda)` hacia adelante (ignora cabecera EXIF/headers)
  - Para PNG (`\x89PNG`): recorta desde `IDAT` (ignora IHDR/metadata)

**Umbrales**:
- `MOTION_THRESHOLD = 0.20` (20% debe cambiar para considerarse motion)
- `MOTION_PIXEL_DIFF_THRESHOLD = 20`
- `MOTION_CONFIRMATION_FRAMES = 1`

## 4. Qué condiciones activan GATE_OPEN, DOOR_OPEN, PET_ESCAPING, MOTION

### En `predict_ambient_state(reading, prev=None, motion_score=0.0)`
**Sensores (SensorBus)**:
- `reading.gate_open` → `escalate("MEDIUM")`, señal `"perimeter open"`, `detections["GATE_OPEN"] = 0.9`
- `reading.door_open` → `escalate("MEDIUM")`, señal `"door open"`, `detections["DOOR_OPEN"] = 0.88`
- **Correlación**: `if reading.gate_open and reading.pet_proximity >= 0.5`: `escalate("HIGH")`, señal `"pet escape risk"`, `detections["PET_ESCAPING"] = 0.85`

**Movimiento (visión)**:
- `if motion_score >= MOTION_THRESHOLD`: `detections["MOTION"] = round(min(0.4 + motion_score, 0.85), 2)`

### En `AmbientWatchService.tick()`
- `_ALERT_TRIGGERS = frozenset({"GATE_OPEN", "PET_ESCAPING", "MOTION"})`
- `_WATCH_ALERT_LEVELS = ("HIGH", "CRITICAL")`
- `camera_alert` solo se publica si `prediction.risk_level in _WATCH_ALERT_LEVELS AND triggered` donde `triggered = any(label in _ALERT_TRIGGERS for item in detections)`

**CRÍTICO**: `DOOR_OPEN` **NO está en `_ALERT_TRIGGERS`**. Tampoco `SMOKE`/`FIRE`/`TEMP_RISING`. Solo `GATE_OPEN`, `PET_ESCAPING`, `MOTION` pueden disparar `camera_alert`.

## 5. Dependencias con SensorBus
- `src/infrastructure/services/sensor_bus.py`: `SimulatedSensorBus.read(now)` devuelve baseline estático/determinista
  - `gate_open=False`, `door_open=False`, `pet_proximity=0.12`, `pet_moving=False`, `smoke_density=0.02`, `temperature_c=22.4`
- **Comentario**: *"Live movement is therefore decided exclusively by the camera: `frame_delta_ratio >= MOTION_THRESHOLD` on the Vivotek snapshot is the only real-time HIGH driver."*

**Dependencia**: `GATE_OPEN`, `DOOR_OPEN`, `PET_ESCAPING` dependen **exclusivamente** de `SensorBus`. **MOTION** depende **exclusivamente** de visión.

## 6. ¿Puede una Vivotek sin sensores físicos producir GATE_OPEN/DOOR_OPEN?
**NO, de forma determinista.**

- **GATE_OPEN**: Requiere `SensorReading.gate_open = True`. SensorBus simulado siempre False.
- **DOOR_OPEN**: Requiere `SensorReading.door_open = True`. Sin sensores, imposible.
- **PET_ESCAPING**: Requiere gate_open → imposible sin sensores.
- **MOTION**: **Sí** si hay movimiento suficiente entre frames consecutivos y `source="live"`.

## 7. ¿Qué espera el código?
- Frames consecutivos para comparación (`prev_payload` inicial vacío → primer tick da motion 0.0)
- `CameraFrameSource` con `get_frame()`, `record_detections()`
- `SensorBus` con `read(now)`
- `EventHub` para publicar `camera_alert`
- Para alerta útil: riesgo HIGH/CRITICAL + trigger en `_ALERT_TRIGGERS`

## 8. Evidencia
### Funcionando
- `test_watch_tick_records_detections_and_publishes_alert`: frames cambiantes generan MOTION → HIGH → camera_alert publicado
- `test_predict_gate_open_with_pet_flags_escape`: lógica sensor+correlación funciona
- `test_frame_delta_ratio_identifies_changing_scene`: cálculo delta funciona

### No funcionando en práctica
- Sin movimiento suficiente o escena estática → `motion_score < MOTION_THRESHOLD` → sin trigger → sin `camera_alert` → dashboard LOW
- Sin sensores → `GATE_OPEN`/`DOOR_OPEN` nunca generados
- `DOOR_OPEN` no está en triggers → aunque se generara con sensores, no dispara `camera_alert`
- Primer tick sin frame previo → motion 0.0

## Causa raíz
1. **Separación sensor vs visión**: GATE_OPEN/DOOR_OPEN son exclusivamente sensoriales. Sin sensores físicos/estado, imposibles.
2. **Triggers incompletos**: `DOOR_OPEN` ausente de `_ALERT_TRIGGERS` → no genera `camera_alert` útil.
3. **Movimiento requiere delta**: necesita 2 frames consecutivos y cambio >= 20%. Escena estática o primer tick → sin MOTION.
4. **Sin inferencia visual**: no hay detector para inferir apertura desde imagen.

## Limitaciones actuales
- Sin visión para puertas/rejas
- Triggers no cubren DOOR_OPEN
- Dependencia obligatoria de SensorBus para esos eventos
- Motion threshold puede ser restrictivo
- Primeros ticks no detectan movimiento

## Impacto en demo
- Abrir reja/puerta visualmente no genera evento si no hay sensores
- Solo movimiento real detectado por delta genera alertas
- Android puede funcionar por configuración distinta, pero con Vivotek + SensorBus simulado el comportamiento es por diseño

## Corrección mínima recomendada (SIN IMPLEMENTAR)
1. **Añadir `DOOR_OPEN` a `_ALERT_TRIGGERS`** en `ambient_watch_service.py`
2. **Considerar inferencia visual opcional** para GATE_OPEN/DOOR_OPEN
3. **Mejorar debug/estado**: exponer motivo por el que no se dispara alerta
4. **Validar sensores**: confirmar estado real de SensorBus
5. **Ajuste de umbrales** (cauteloso): solo si necesario

## Conclusión
La Vivotek entrega video correctamente, pero el pipeline de alertas NO está diseñado para inferir aperturas desde imagen. GATE_OPEN/DOOR_OPEN dependen de SensorBus. MOTION depende de frame-delta con umbrales. Además `DOOR_OPEN` no está en triggers. Estos son límites de diseño, no bugs de entrega de frames.
