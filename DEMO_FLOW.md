# DEMO_FLOW.md

## Objetivo
Guía de demostración para mostrar EchoMind en evaluación. Seguir orden para máximo impacto.

## Preparación
- Asegurar sistema corriendo (servidor MCP/API + watchdog + cámaras configuradas)
- Tener memoria con al menos algún evento (MOTION/PERSON) o generar con cambios
- Tener acceso a respuestas con evidence/trace visibles

## Flujo de demo

### A. "¿La reja está cerrada?" 
- **Ruta**: Query Router → CURRENT_STATE (GATE, polarity closed)
- **Mostrar**: Respuesta directa con estado vivo
- **Mensaje**: "Separación entre estado actual vs memoria histórica"

### B. "¿Qué ocurre ahora?"
- **Ruta**: CURRENT_STATE OVERVIEW
- **Mostrar**: Detecciones, riesgo, estado cámaras/sensores
- **Mensaje**: "Snapshot unificado del hogar"

### C. "¿Qué ocurrió antes de la caída?"
- **Ruta**: RECALL → BEFORE
- **Mostrar**: Timeline, relations, evidence[], trace[]
- **Mensaje**: "Reconstruye lo que pasó antes, con evidencia"

### D. "¿Qué ocurrió después de la caída?"
- **Ruta**: RECALL → AFTER
- **Mostrar**: Secuencia temporal, episodios relacionados
- **Mensaje**: "Direccionalidad temporal"

### E. "¿Qué pasó mientras estaba fuera?"
- **Ruta**: RECALL → RANGE/TIMELINE
- **Mostrar**: Ventana temporal inferida, contexto narrado
- **Mensaje**: "Comprende 'mientras estaba fuera' sin regex rígido"

### F. "¿Qué eventos están relacionados?"
- **Ruta**: RECALL → RELATIONS
- **Mostrar**: Relaciones (EPISODE/THATLES TRIMESTRE SPATIAL/CORRELATION/TIMELINE/BEFORE_AFTER), episodios
- **Mensaje**: "Conecta eventos en el tiempo/espacio"

### G. "¿Qué cámaras observaron el mismo evento?"
- **Ruta**: RECALL → CAMERAS
- **Mostrar**: Por cámara/fuente, evidencia agrupada
- **Mensaje**: "Trazabilidad por origen"

## Tips
- Siempre mostrar **evidence + trace**. Ahí está el diferenciador.
- Si hay abstención, mostrarla como "honestidad" no como fallo.
- Enfatizar: **evidencia-first, sin inventar, determinista**.
- No entrar en detalles de implementación; mostrar resultados.
