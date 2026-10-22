# KNOWN_LIMITATIONS.md

## Limitaciones conocidas (aceptadas para hackathon)

### Percepción / Visión
- **Sin detección de objetos cotidianos**: No reconoce cargador, llaves, celular, mouse, teclado, monitor. Solo etiquetas eventos: PERSON, PET, MOTION, SMOKE, FIRE, GATE_OPEN, DOOR_OPEN, FALL DETECTED.
- **Sin inferencia visual de aperturas**: GATE_OPEN/DOOR_OPEN dependen de SensorBus, no se infieren desde imagen.
- **Vivotek basado en movimiento + sensores**: Motion detection por frame-delta (heurístico). Requiere frames consecutivos.

### Alertas / Memoria
- **DOOR_OPEN no dispara alerta**: NO está en `_ALERT_TRIGGERS`. Solo genera detección si proviene de sensores, pero no publica `camera_alert`.
- **Dependencia de sensores**: Sin SensorBus físico/configurado, GATE_OPEN/DOOR_OPEN no se generan.
- **Primeros ticks**: Sin frame previo, motion_score puede ser 0.0 hasta tener comparación.

### Arquitectura / Alcance
- **Sin VLM remoto**: Filosofía on-device/QFP. No usa LLM para recordar.
- **Sin object detection integrado**: Planificado pero no implementado (fuera de alcance para freeze).
- **Triggers limitados**: Solo GATE_OPEN, PET_ESCAPING, MOTION disparan alertas.

## Notas
Estas son limitaciones de diseño/congelamiento, no bugs. El enfoque está en **memoria episódica trazable**, no en reconocimiento genérico de objetos.
