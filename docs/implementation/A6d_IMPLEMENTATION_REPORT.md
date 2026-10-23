# A6d — Motor de Relaciones · Informe de Implementación

**Fecha:** 2026-10-18
**HEAD:** `b963c5f` — sin commits, sin push.
**Resultado:** ✅ **473 tests PASS** · **flake8: 0** · **black: 89 ficheros sin cambios** · **impacto en V1: cero**

---

## 1. Objetivo

Implementar el motor de reglas del Grafo de Relaciones (§5.4 de
`A6_CONTEXTUAL_REASONING_ARCHITECTURE.md`): generar objetos `Relation` a partir
de los episodios recuperados, con trazabilidad completa y **cero efecto en la
respuesta final**.

Requisito duro de la fase: *la salida debe permanecer idéntica; las relaciones
pueden aparecer solo en la traza*.

---

## 2. Qué se entregó

### 2.1 `src/domain/services/relation_rules.py` (nuevo, ~200 líneas)

Una tabla de reglas + un motor de pares. Las reglas son **datos** en lugar de
`elif` en cadena: añadir una relación nueva es añadir una fila, no tocar el
motor.

| `id` | `kind` | Dispara cuando… | `facts` |
|---|---|---|---|
| `temporal.precedes` | `temporal_precedes` | `A.end <= B.start` y separación ≤ adjacencia | `seconds` |
| `temporal.transition` | `temporal_transition` | preceden + etiquetas distintas + misma zona | `from_labels`, `to_labels`, `seconds` |
| `correlation.same_label` | `correlation_same_label` | etiquetas en común | `shared` |
| `correlation.same_risk` | `correlation_same_risk` | mismo nivel de riesgo | `risk` |
| `correlation.overlapping` | `correlation_overlapping` | solape temporal ≥ 0 | `overlap_seconds` |
| `spatial.same_zone` | `spatial_same_zone` | misma zona | `zone` |

- `RelationRule` y `Relation` son `frozen=True, slots=True`.
- `kind` de cada regla pertenece por construcción a `KNOWN_RELATION_KINDS`
  (`relation.py`, A6a) — verificado por test.

**Identidad del episodio:** `episode.record_ids[0]`; si no existe,
`f"ep@{start:.3f}"`. Determinista.

### 2.2 Integración en `src/infrastructure/services/recall_engine.py`

Único fichero V1 modificado en toda la fase.

- `RecallEngine.__init__` acepta un nuevo keyword `max_relations`
  (`DEFAULT_MAX_RELATIONS = 64`).
- `_relate()` llama a un nuevo `_derive_relations()` **solo cuando
  `plan.relations` no está vacío**:

  ```json
  {
    "op": "relate",
    "relation": "derived",
    "count": 13,
    "relations": [ { "kind": "temporal_precedes", "subject": "mem-1",
                     "object": "mem-2", "rule": "temporal.precedes",
                     "facts": { "seconds": 1000.0 },
                     "degraded": false, "fallback": null }, ... ]
  }
  ```

- `render_utterance` y todas las ramas existentes quedan **intactas**.

### 2.3 `tests/unit/test_relation_rules.py` (nuevo, 40 tests)

Reglas puras, determinismo, cap, proveniencia y cableado del motor.

---

## 3. Contrato cumplido

| Criterio | Resultado |
|---|---|
| Relaciones solo en la traza | ✅ `utterance` idéntica con y sin relaciones (test explícito) |
| Plan sin relaciones → sin entrada nueva | ✅ `test_a_plan_without_relations_adds_no_derived_entry` |
| Traza JSON-segura | ✅ `test_derived_relations_are_json_safe` |
| Cap respetado por el motor | ✅ `test_the_engine_honours_a_custom_relation_cap` |
| Determinismo | ✅ orden por `(kind, subject, object)`; orden de entrada irrelevante |

**Demostración real** (fixture A2, 4 registros, `now=10000`):

```
count: 13
  temporal_precedes   mem-1->mem-2   seconds=1000.0
  temporal_precedes   mem-1->mem-3   seconds=4000.0
  correlation_same_label  mem-1->mem-2  shared=('PET',)
  correlation_same_risk   mem-1->mem-2  risk=HIGH
  spatial_same_zone   mem-1->mem-2   degraded=True zone=patio
  ...
utterance: PET en patio, hace 2 horas. ...
```

La utterance es exactamente la del motor previo a A6d.

---

## 4. Limitaciones declaradas (sin parchear, sin fingir)

1. **`spatial.same_camera` diferido.** `Episode` no lleva `camera_id` (ni
   `source`); emitir una regla que siempre adivinara sería peor que el
   silencio. `memory_timeline.py` **no se modificó**. Requiere que `Episode`
   transporte la cámara → fase posterior.

2. **`temporal.gap` diferido.** Los silencios ya están cubiertos por el campo
   `gaps` de la relación `TIMELINE` (A2). Duplicarlo sería ruido.

3. **`spatial.same_zone` degradado en datos legacy.** `resolve_zone` sobre un
   `Episode` cae honestamente a `location`, y cada relación lo marca
   `degraded=True, fallback="location"` en lugar de fingir precisión.

4. **`Episode` no se enriqueció** con `zone`/`camera_id`. La limpieza de la fase
   A5 se preserva; la zona se resuelve en punto de uso.

---

## 5. Decisiones de diseño

- **Índice por `id`, no por `kind`.** El motor construye relaciones a partir del
  identificador de la regla (`temporal.precedes`), mientras que `Relation.kind`
  es la forma `temporal_precedes`. Un primer intento indexó por `kind` y lanzó
  `KeyError` en 9 tests; corregido a `_RULE_BY_ID` con el parámetro renombrado
  `rule_id` para que el error sea imposible de reproducir por confusión.

- **Sin campo `confidence` en `Relation`** (decisión heredada de A6a, ahora
  con consumo real). `Evidence.confidence` es confianza de *detección*; una
  relación usa `degraded`/`fallback`. En un sistema de seguridad mezclar los
  dos significados es una trampa.

- **Lenguaje causal prohibido en vocabulario** (`relation.py`, A6a). Las reglas
  usan `precedes`/`transition`/`overlapping`, jamás `causes`.

- **Una sola entrada `derived` por plan**, no una por regla. Mantiene la traza
  legible y el coste constante.

---

## 6. Prueba de impacto cero

Se capturó la huella SHA-256 de **87 ficheros** `.py` de `src` + `tests` antes
de tocar nada (`A6D_BASELINE.sha256`).

```
changed/missing: 1
CHANGED: .\src\infrastructure\services\recall_engine.py

protegidos: memory_converse / intent / bridge / service / timeline / tools / main
            → INTACTOS
missing: 0
```

**Un único fichero V1 modificado**, exactamente el que debía. El baseline se
eliminó tras la verificación (ver §8).

El test previo `tests/unit/test_recall_engine.py:163`, que fija la lista
`ops_executed` exacta para planes **sin** relaciones, permanece en verde: la
entrada `derived` solo se añade a partir de la primera relación pedida.

---

## 7. Gates finales

| Gate | Comando | Resultado |
|---|---|---|
| Tests | `pytest -q` | **473 passed** (433 → 473; +40) en ~10.5 s |
| Lint | `flake8 src tests` | **0** |
| Formato | `black --check src tests --line-length 88` | **89 ficheros sin cambios** |
| Commits | `git log --oneline -1` | `b963c5f` (sin cambios) |

Solo se formatearon los tres ficheros tocados en A6d, y `black --diff` se revisó
antes en `recall_engine.py` para confirmar que recaía únicamente dentro del
método nuevo.

---

## 8. Archivos

**Nuevos**
- `src/domain/services/relation_rules.py` — tabla de reglas + `relate_episodes`
- `tests/unit/test_relation_rules.py` — 40 tests

**Modificados (1)**
- `src/infrastructure/services/recall_engine.py` — import, `max_relations`,
  `_derive_relations`

**No tocados** (verificado por hash): `memory_resolvers.py`, `memory_intent.py`,
`memory_bridge.py`, `memory_service.py`, `memory_timeline.py`, `relation.py`,
`memory_anchor.py`, `memory_spatial.py`, `recall_plan.py`, Dashboard, Android,
Vivotek.

**Eliminados:** `A6D_BASELINE.sha256`, `_a6d_demo.py`.

---

## 9. Siguiente fase sugerida

**A6e — Exclusión del ancla.** En A6c se documentó que el episodio ancla sigue
apareciendo en los resultados de `before`/`after` porque `episodes_before` es
inclusivo por diseño de A2. Corresponde filtrarlo en el punto de decisión.

Después, **A6f** puede consumir el grafo `derived` (ya en la traza) para la
narración contextual — sobre un cimiento que hoy existe sin alterar una sola
palabra del discurso.
