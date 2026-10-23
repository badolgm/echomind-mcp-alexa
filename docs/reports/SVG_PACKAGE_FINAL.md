# SVG PACKAGE FINAL — EchoMind V2

> Paquete de los 5 diagramas de arquitectura de EchoMind V2.
> Especificación única: `DIAGRAM_FINAL_PACKAGE.md`.
> Sin código, sin tests, sin commits, sin push.
> Referencia de estado: HEAD `e5559d1`.

---

## 1. Lista de SVG generados

| # | Archivo | viewBox | Nodos `<text>` | Tamaño | Contenido |
|---|---------|---------|----------------|--------|-----------|
| 1 | `hero.svg` | `0 0 1280 720` | 32 | 6.1 KB | Vista de 60 s: Alexa+ → MCP `/mcp` → Query Router → Current State / Memory Recall; ingesta continua + Bedrock opcional (punteado). |
| 2 | `system-architecture.svg` | `0 0 1400 980` | 43 | 9.9 KB | Hexagonal por capas: entradas, adapters, infra services, dominio puro, puertos, salidas; dos flujos (datos / consulta). |
| 3 | `memory-reasoning.svg` | `0 0 1400 900` | 59 | 9.2 KB | Pipeline de 7 etapas: entender → plan → retrieve → relate → narrate → synthesize → resultado; garantías y módulos. |
| 4 | `query-router.svg` | `0 0 1400 940` | 57 | 8.7 KB | A7C: tabla de precedencia → CURRENT_STATE vs RECALL, `RouteDecision`, y el arreglo `¿La reja está cerrada?`. |
| 5 | `domain-erd.svg` | `0 0 1400 1000` | 99 | 13.6 KB | ERD: MemoryRecord, Evidence, Episode, TimelineGap, Relation, RelationRule, ContextItem, AnchorRef, RecallPlan + invariantes. |

Todos los archivos están en la raíz del repositorio.

---

## 2. Validación

- **XML bien formado**: los 5 parsean con `System.Xml.XmlDocument` sin error.
- **`viewBox` presente**: sí en los 5 (valores en la tabla anterior); cada SVG es escalable sin depender de `width`/`height` fijos.
- **Texto legible**: recuento de nodos `<text>` entre 32 y 103; sin texto embebido como `<image>` ni fuentes externas. Las familias usadas (`Segoe UI, Arial, sans-serif` y `Consolas, Cascadia Mono, monospace`) son fuentes del sistema, por lo que el render no depende de recursos remotos.
- **Sin recursos externos**: sin `<script>`, sin `<foreignObject>`, sin `xlink:href`, sin imágenes remotas. Render determinista en GitHub README.
- **Fidelidad a la especificación**: cada entidad, relación y módulo proviene de `DIAGRAM_FINAL_PACKAGE.md` (que a su vez proviene del código). No hay entidades ni relaciones inventadas.
- **Alcance respetado**: `test-growth.svg` y `quota-fallback.svg` excluidos (diagramas métricos, no de arquitectura).

---

## 3. Resolución recomendada

Para GitHub README, renderizar en ancho completo con título de sección:

- **Hero** (1280×720, ~16:9): ancho completo; funciona también como imagen de cabecera del README.
- **System-architecture** (1400×980): ancho completo; es el diagrama denso principal.
- **Memory-reasoning** (1400×900), **Query-router** (1400×940): ancho completo en secciones sucesivas.
- **Domain-ERD** (1400×1000): ancho completo; layout reorganizado para lectura sin zoom al 200% — TEMPORAL/SPATIAL/CORRELATION separados en sub-bloques de color, RecallPlan en franja ancha (3 filas), AnchorRef reforzado, y relaciones sin cruces.

Regla práctica: mantener los 5 al mismo ancho de contenedor (100%) y dejar que el `viewBox` escale la altura. No fijar `width`/`height` en el embed para no perder nitidez.

---

## 4. Orden para README

Narrativa de 60 s: primero el qué (panorama), luego el cómo (capas), después el razonamiento, la decisión y el modelo de datos.

1. `hero.svg` — qué es EchoMind V2 y sus dos fuentes de verdad.
2. `system-architecture.svg` — cómo está construido (hexagonal, adapters vs dominio).
3. `memory-reasoning.svg` — cómo razona sobre la memoria (pipeline).
4. `query-router.svg` — cómo decide entre estado actual e historia (A7C).
5. `domain-erd.svg` — sobre qué entidades se sostiene (modelo de dominio).

Veredicto del paquete: cumple precisión arquitectónica, legibilidad en README y calidad visual profesional; sin SVG decorativos, sin marketing y sin simplificaciones.
