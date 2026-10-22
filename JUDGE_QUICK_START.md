# JUDGE_QUICK_START.md

## EchoMind en 5 minutos

### ¿Qué es?
EchoMind es una **memoria episódica evidencia-first** para el hogar. Recuerda hechos observados por cámaras/sensores y responde reconstruyendo, relacionando, ordenando y narrando con base en evidencia auditable.

### Diferenciador clave
- **No es chatbot**: No memoriza conversación, recuerda **eventos** persistidos
- **Evidencia-first**: Cada respuesta muestra `evidence` + `trace`
- **Dos caminos**: `CURRENT_STATE` (snapshot vivo) vs `RECALL` (histórico)
- **Determinista**: Mayoría sin LLM para recordar; auditable
- **Honesto**: Se abstiene si no hay evidencia

### Arquitectura en pocas palabras
```
Sensores/Cámaras → Watchdog → EventHub → MemoryBridge → VectorMemoryService
Pregunta → Query Router → (CURRENT_STATE | RECALL Engine) → Respuesta + evidence + trace
```

### Demo rápido (3 preguntas)
1. *"¿La reja está cerrada?"* → Estado vivo (Query Router)
2. *"¿Qué ocurrió antes de la caída?"* → Timeline + Relations + evidencia
3. *"¿Qué cámaras observaron el mismo evento?"* → Trazabilidad

### Documentación clave
- `README.md` - Visión general
- `ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md` - Arquitectura memoria
- `A7C_QUERY_ROUTER_ARCHITECTURE.md` - Router
- `A7D_IMPLEMENTATION_REPORT.md` - Response Intent Adapter

### Tests
700 tests PASS
