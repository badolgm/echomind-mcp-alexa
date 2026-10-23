# CONVERSATIONAL_REASONING_REPORT.md — Sprint Conversational Reasoning

**Fecha:** 2026-10-11  
**Rama:** `checkpoint/day1-mobile-memory`  
**HEAD:** `407ca29` (con cambios locales TRAE)  
**Estado:** 208 tests PASSED (unit 191 + integration 17). No se toca código.

---

## 1. Problema objetivo

Pregunta ejemplo: `"Última hora de detección de movimiento"`  
Respuesta esperada: **último evento MOTION** (respuesta enfocada a cuándo/qué fue la última detección de movimiento).  
Respuesta actual (con seed demo): devuelve un listado genérico vía `search` (MemoryConverse) en lugar de la respuesta enfocada de `last_seen`.

---

## 2. Diagnóstico

### 2.1 Clasificador (`src/domain/services/memory_intent.py`)

Casos probados:

| Pregunta | intent detectado | label | hours | Observación |
|---|---|---|---|---|
| `Última hora de detección de movimiento` | **SEARCH** | `None` | `None` | No detecta LAST_SEEN. No extrae `MOTION`. |
| `¿Cuándo viste movimiento?` | **LAST_SEEN** | `MOTION` | `-` | OK |
| `último evento MOTION` | **SEARCH** | `None` | `None` | Falla a pesar de pedir "último evento". |
| `última detección de movimiento` | **SEARCH** | `None` | `None` | "última detección" no en `_LAST_SEEN_RE`. |
| `last motion detection` | **SEARCH** | `None` | `None` | No dispara LAST_SEEN en EN. |
| `when was motion last seen` | **LAST_SEEN** | `MOTION` | `-` | OK |
| `what happened today` | **SUMMARY** | `None` | `24.0` | OK |
| `¿Qué recuerdas de hoy?` | **SUMMARY** | `None` | `24.0` | OK |
| `¿Cuándo viste la reja abierta?` | **LAST_SEEN** | `GATE_OPEN` | `-` | OK |
| `critical events` | **CRITICAL_RISK** | `None` | `-` | OK |

### 2.2 Por qué falla

- `_LAST_SEEN_RE` (ES/EN) incluye `cuándo viste/vio`, `última vez`, `last seen/last time`, `recientemente`, pero **no** incluye: `"última hora"`, `"última detección"`, `"último evento"`, `"last detection"`, `"last event"`.
- `_HOURS_RE` (ES) requiere número explícito (`últimas 2 horas`, `últimas 1 hora`) o `last/past N hours`. `"última hora"` sin número no casa. Además busca `últimas?` (plural opcional) pero el patrón actual no captura correctamente "última hora" como disparador de LAST_SEEN en estas formas coloquiales.
- Cuando no hay número, `_HOURS_RE` devuelve `None` y el clasificador no deriva intención LAST_SEEN por "última + label".
- `MemoryConverse`: si `intent.intent == SEARCH`, redirige a `search` (resolver genérico) → respuesta no enfocada a "última detección".

### 2.3 Ruta MemoryConverse (`memory_resolvers.py:481-516`)

- `LAST_SEEN + label` → `last_seen(label, location, lang)` → respuesta enfocada ✅
- `LAST_SEEN sin label` → `search(query, ...)` (fallback)
- `SEARCH` → `search(query, ...)` → **listado genérico** (caso actual)
- `SUMMARY/COUNT/TOP/HIGH_RISK/CRITICAL/CURRENT` → resolvers específicos

---

## 3. Análisis de intenciones correctas

| Pregunta | intención detectada (actual) | intención correcta | resolver actual | resolver esperado |
|---|---|---|---|---|
| `"Última hora de detección de movimiento"` | **SEARCH** | **LAST_SEEN** + `label=MOTION` | `search` | `memory.last_seen(label="MOTION")` → "La última detección de movimiento ocurrió hace ... en cam-01." |
| `"última detección de movimiento"` | **SEARCH** | **LAST_SEEN** + `label=MOTION` | `search` | `last_seen(MOTION)` |
| `"último evento MOTION"` | **SEARCH** | **LAST_SEEN** + `label=MOTION` | `search` | `last_seen(MOTION)` |
| `"last motion detection"` (EN) | **SEARCH** | **LAST_SEEN** + `label=MOTION` | `search` | `last_seen(MOTION)` |

---

## 4. Ajustes mínimos necesarios

Dos opciones **no invasivas** (no añaden funcionalidad nueva, solo mejoran routing):

### Opción A: Ampliar `_LAST_SEEN_RE` (domain, más directo)

Añadir patrones ES/EN. Sugerido (conservador, case-insensitive):

```python
_LAST_SEEN_RE = re.compile(
  r"recientemente|recently|cu[aá]ndo\s+v(?:iste|io|ió)|"
  r"cu[aá]ndo\s+fue\s+la\s+[úu]ltima|cu[aá]ndo\s+fue\s+el\s+[úu]ltimo|"
  r"[úu]ltima\s+(?:vez|detecci[oó]n|ocurrencia|hora|alerta|evento)|"
  r"[úu]ltimo\s+(?:evento|aviso|registro)|"
  r"when\s+did\s+you\s+(?:last\s+)?see|when\s+did\s+you\s+see|when\s+was|"
  r"when\s+was\s+the\s+last|last\s+seen|last\s+time|last\s+detection|"
  r"last\s+event|last\s+occurrence|last\s+alert|[úu]ltimamente|por\s+[úu]ltim",
  re.I
)
```

Notas: `re.I` reduce duplicados; manejar acentos con `[úu]`. Añadir `detección/detection` y `evento/event`.

### Opción B: Fallback heurístico en `MemoryConverse` (infra, muy seguro)

Si `intent.intent == SEARCH` pero la consulta contiene "última"/"último"/"last" + label conocido → redirigir a `LAST_SEEN`:

```python
# en build_memory_converse_resolver.resolve, tras obtener intent
if intent.intent is MemoryIntentType.SEARCH and not intent.label:
  # extraer label desde query
  qn = intent.query.lower()
  # mapear labels conocidos...
  for lbl,terms in _LABEL_TERMS_MIRROR:  # o reutilizar lógica
    if any(t in qn for t in terms):
      intent = MemoryIntent(MemoryIntentType.LAST_SEEN, query=intent.query, label=lbl, lang=intent.lang)
      break
```

**Recomendado:** **Opción B** (mínima, no toca regex de clasificación, evita efectos colaterales, conserva todos los tests existentes).

---

## 5. Impacto en tests existentes

- `tests/unit/test_memory_intent.py`: 14 passed (todos OK)
- `tests/unit/test_memory_converse.py`: 12 passed (todos OK) 
- `tests/unit/test_memory_resolvers.py`: 11 passed
- **Suite completa:** 208 passed

**Cualquier ajuste debe mantener estos 37 unit tests + 171 restantes en verde.**

---

## 6. Veredicto

**Cambios mínimos justificables. No requieren nuevas funcionalidades.**

| Aspecto | Evaluación | Riesgo |
|---|---|---|
| Añadir patrones a `_LAST_SEEN_RE` | Aditivo, lógico | **Bajo** (posibles falsos positivos mínimos; tests actuales no afectados) |
| Fallback heurístico en `memory_converse` | Muy localizado, condicional | **Muy bajo** (sólo cuando SEARCH sin label y detecta "última"+label) |
| Extracción label si LAST_SEEN sin label | Reutiliza lógica existente | **Bajo** |

**Recomendación:** Implementar **únicamente** uno de estos dos ajustes mínimos (preferiblemente **Opción B**) para resolver los 4 casos identificados sin alterar el comportamiento del clasificador para casos ya cubiertos.

**Entregable:** `CONVERSATIONAL_REASONING_REPORT.md` (este documento). Sin commits. Sin push. Sin cambios nuevos.