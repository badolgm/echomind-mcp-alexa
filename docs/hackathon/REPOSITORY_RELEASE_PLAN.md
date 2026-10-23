# REPOSITORY RELEASE PLAN

> Sprint: **README PACKAGING**.
>
> `README.md` queda **CONGELADO**: no se reescribe, no se toca narrativa, no se toca arquitectura,
> no se toca contenido de EchoMind V2.
>
> Este plan resuelve **únicamente**: (1) diagramas no trackeados, (2) screenshots, (3) `.local/scripts`,
> (4) estructura `docs/`.
>
> **Sin commits. Sin push. No se mueve ningún archivo todavía.**
>
> HEAD de referencia: `e5559d1`.

---

## 0. Estado verificado (evidencia)

```
git status --short
 M README.md
 M requirements.txt
 M src/domain/models/tools.py
 M src/infrastructure/adapters/camera/http_phone_camera_adapter.py
 M src/main.py
 M src/static/dashboard.html
?? DIAGRAM_FINAL_PACKAGE.md
?? README_FINAL_POLISH_REPORT.md
?? SVG_PACKAGE_FINAL.md
?? dashboard_full.png
?? domain-erd.svg
?? hero.svg
?? memory-reasoning.svg
?? query-router.svg
?? system-architecture.svg
?? voicedock_answer.png
?? voicedock_idle.png
```

| Hecho | Comando | Resultado |
| ----- | ------- | --------- |
| SVG no trackeados | `git ls-files "*.svg"` | **vacío** |
| PNG no trackeadas | `git ls-files "*.png"` | **vacío** |
| `.local/` ignorado | `git check-ignore .local/scripts/run_demo.py` | **la ruta** (ignorado) |
| `docs/` | `Test-Path docs` | **False** |
| `scripts/` | `Test-Path scripts` | **False** |

**Artefactos y tamaños**

| Archivo | Tamaño | Notas |
| ------- | ------ | ----- |
| `hero.svg` | 6.1 KB | diagrama |
| `system-architecture.svg` | 9.9 KB | diagrama |
| `memory-reasoning.svg` | 9.2 KB | diagrama |
| `query-router.svg` | 8.7 KB | diagrama |
| `domain-erd.svg` | 34.8 KB | diagrama (texto denso) |
| `dashboard_full.png` | 261 KB | 1900×1853 · captura Control Center |
| `voicedock_idle.png` | 25.9 KB | 879×208 · Voice Dock idle |
| `voicedock_answer.png` | 44.3 KB | 879×401 · Voice Dock respuesta |

---

## 1. Qué subir

### 1.1 Diagramas (obligatorio)
`README.md` los embebe con `./hero.svg` y similares. Están **sin trackear** → hoy dan 404 en GitHub.

- `hero.svg`
- `system-architecture.svg`
- `memory-reasoning.svg`
- `query-router.svg`
- `domain-erd.svg`

### 1.2 Screenshots (recomendado)
Capturas reales del producto (Control Center y Voice Dock). Dan credibilidad en la evaluación.

- `dashboard_full.png`
- `voicedock_idle.png`
- `voicedock_answer.png`

> Nota: el README congelado **no las referencia todavía**. Se suben ahora para tenerlas en el repo;
> enlazarlas en el README es un cambio futuro (no de este sprint).

### 1.3 Scripts de demo/emulación (obligatorio, ver §3)
Los tres scripts de `.local/scripts/` pasan a un directorio **trackeado**.

- `alexa_mcp_simulator.py` (269 líneas) — emula Alexa+ (sesión, SSE, JSON-RPC, adjuntos).
- `run_demo.py` (204 líneas) — demo end-to-end + QFP, referenciada en `## 13 Project Status` como "demo runner".
- `test_vivotek_conn.py` (71 líneas) — prueba de conectividad de la cámara.

### 1.4 Documentos de este sprint (recomendado)
- `DIAGRAM_FINAL_PACKAGE.md`, `SVG_PACKAGE_FINAL.md`, `README_FINAL_POLISH_REPORT.md`,
  `REPOSITORY_RELEASE_PLAN.md` (este).

---

## 2. Qué NO subir

| Elemento | Motivo |
| -------- | ------ |
| `.local/` (resto) | Scratch local: `Gemini_Generated_Image_*.jpg`, `snapshot_vivotek_test.jpg`, `logs/*.log`, `__pycache__/`, `.local/README.md`. Ya está en `.gitignore` — **dejar así**. |
| `.venv/`, `__pycache__/`, `.pytest_cache/` | Ya ignorados. |
| Credenciales (`*.key`, `.env`, `credentials`) | Ya ignorados. **Nunca commitear.** |
| `snapshot_vivotek_test.jpg` (en `.local/`) | Artefacto de prueba, no producto. |

> Regla: solo sale de `.local/` lo que es **utilidad reproducible** (los 3 scripts). El resto permanece
> ignorado.

---

## 3. `.local/scripts` — decisión

**Determinación: MOVER a un `scripts/` trackeado y subirlos.**

Razones (mejor práctica de hackathon):
1. `README.md` (líneas 387/392/395) los presenta como la forma de **"Drive it like Alexa+"**. Si un juez
   clona el repo y ejecuta esos comandos, **fallan**: `.local/` está ignorado.
2. `run_demo.py` se cita como *demo runner* en `## 13 Project Status` → es parte de la historia del producto.
3. Son autocontenidos y de propósito único (demo/emulación), no scratch.
4. Eliminar las referencias del README **contradiría** la sección Getting Started y el estado del proyecto,
   y quitaría una demo reproducible clave para la evaluación.

**Impacto técnico del movimiento**

| Script | Ajuste necesario al mover |
| ------ | ------------------------- |
| `run_demo.py` | `REPO_ROOT = Path(__file__).resolve().parent.parent.parent` → `...parent.parent` (pasa de `.local/scripts/` a `scripts/`); actualizar el docstring `python .local/scripts/run_demo.py` → `python scripts/run_demo.py` |
| `alexa_mcp_simulator.py` | No usa rutas de repo; revisar solo el encabezado/docstring si menciona la ruta |
| `test_vivotek_conn.py` | `SNAPSHOT_PATH = parents[1] / "snapshot_vivotek_test.jpg"` → apuntará a `scripts/`; ajustar a una ruta de salida local (p. ej. `.local/`) |

> Estos ajustes de código **NO se aplican en este sprint** (fuera de alcance; no se mueve nada todavía).
> Se documentan para que el movimiento posterior no rompa la demo.

**Destino recomendado**

```
scripts/
├── alexa_mcp_simulator.py
├── run_demo.py
└── test_vivotek_conn.py
```

---

## 4. Estructura propuesta (sin mover nada todavía)

```text
echomind-mcp-alexa/
├── README.md                  # congelado, permanece en la raíz
├── LICENSE · requirements.txt · Dockerfile · docker-compose.yml
├── setup.cfg · pytest.ini · conftest.py
├── alexa_skill/
├── src/
├── tests/
├── scripts/                   # ← desde .local/scripts (trackeado)
│   ├── alexa_mcp_simulator.py
│   ├── run_demo.py
│   └── test_vivotek_conn.py
├── docs/
│   ├── diagrams/              # los 5 SVG
│   │   ├── hero.svg
│   │   ├── system-architecture.svg
│   │   ├── memory-reasoning.svg
│   │   ├── query-router.svg
│   │   └── domain-erd.svg
│   ├── screenshots/           # las 3 PNG
│   │   ├── dashboard_full.png
│   │   ├── voicedock_idle.png
│   │   └── voicedock_answer.png
│   ├── reports/               # informes A1…A7D + package docs
│   ├── validation/            # validación, auditorías, checkpoints
│   └── architecture/          # diseño (V2 memory-first, A6, A7C, V1, visión)
```

> Si se adopta `docs/diagrams/`, los `src="./*.svg"` del README (congelado) quedarían obsoletos y
> **requerirían** `./docs/diagrams/*.svg`. Como el README está congelado en este sprint, la adopción
> de `docs/` se decide **junto con** una futura micro-edición de rutas (ver §6, decisión D1).

---

## 5. Qué mover / qué mantener

### Mover (fase posterior, no ahora)
- `.local/scripts/{alexa_mcp_simulator,run_demo,test_vivotek_conn}.py` → `scripts/`
- 5 SVG → `docs/diagrams/` (o dejar en raíz; ver D1)
- 3 PNG → `docs/screenshots/`
- Informes/validación/arquitectura → `docs/reports/`, `docs/validation/`, `docs/architecture/`

### Mantener en la raíz
- `README.md`, `LICENSE`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`,
  `setup.cfg`, `pytest.ini`, `conftest.py`, `alexa_skill/`, `src/`, `tests/`, `.gitignore`.

### Mantener ignorado
- Todo `.local/` salvo los 3 scripts movidos.

---

## 6. Decisiones abiertas (recomendación)

| ID | Decisión | Recomendación |
| -- | -------- | ------------- |
| D1 | ¿SVG en la raíz o en `docs/diagrams/`? | **Dos opciones**, ver abajo. |
| D2 | ¿Screenshots en `docs/screenshots/` (no vistas por README congelado)? | Sí; enlazar en README en un sprint futuro. |

**D1 — Dos caminos válidos:**

- **Opción A (mínima, recomendada para hackathon): dejar los 5 SVG en la raíz.**
  El README congelado ya usa `./hero.svg`, etc. → funciona sin tocar ni una línea del README.
  `scripts/` y `docs/screenshots/` se adoptan igual.
- **Opción B (orden total): mover SVG a `docs/diagrams/`.**
  Obliga a editar las 5 rutas `src=` del README (micro-edición de rutas, no de narrativa).
  Más limpio, pero **contradice "README congelado"** en este sprint.

> Recomendación: **Opción A ahora**; migrar a `docs/diagrams/` solo si se autoriza la micro-edición
> de rutas del README.

---

## 7. Comandos git exactos

> **Ejecutar desde la raíz del repositorio. NO ejecutados en este sprint.** Sin `commit`, sin `push`.
> Los comandos de movimiento usan `git mv` solo cuando el origen ya está trackeado; para `.local/`
> (ignorado) se usa `move` + `git add`.

### 7.1 Subir los 5 diagramas (Opción A: permanecen en la raíz)

```powershell
git add hero.svg system-architecture.svg memory-reasoning.svg query-router.svg domain-erd.svg
git status --short
```

### 7.2 Crear `scripts/` y subir los 3 scripts (desde `.local/`, que está ignorado)

```powershell
New-Item -ItemType Directory -Path "scripts" -Force
Move-Item -LiteralPath ".local/scripts/alexa_mcp_simulator.py" -Destination "scripts/alexa_mcp_simulator.py"
Move-Item -LiteralPath ".local/scripts/run_demo.py"           -Destination "scripts/run_demo.py"
Move-Item -LiteralPath ".local/scripts/test_vivotek_conn.py"  -Destination "scripts/test_vivotek_conn.py"
git add scripts/alexa_mcp_simulator.py scripts/run_demo.py scripts/test_vivotek_conn.py
git status --short
```

> Tras esto, aplicar los ajustes de §3 (`REPO_ROOT`, docstrings, `SNAPSHOT_PATH`) en un cambio de código
> separado y revisado.

### 7.3 Subir las 3 screenshots a `docs/screenshots/`

```powershell
New-Item -ItemType Directory -Path "docs/screenshots" -Force
Move-Item -LiteralPath "dashboard_full.png"  -Destination "docs/screenshots/dashboard_full.png"
Move-Item -LiteralPath "voicedock_idle.png"  -Destination "docs/screenshots/voicedock_idle.png"
Move-Item -LiteralPath "voicedock_answer.png" -Destination "docs/screenshots/voicedock_answer.png"
git add docs/screenshots/dashboard_full.png docs/screenshots/voicedock_idle.png docs/screenshots/voicedock_answer.png
```

### 7.4 (Opción B) Mover SVG a `docs/diagrams/` — solo si se autoriza editar las rutas del README

```powershell
New-Item -ItemType Directory -Path "docs/diagrams" -Force
git mv hero.svg                docs/diagrams/hero.svg
git mv system-architecture.svg docs/diagrams/system-architecture.svg
git mv memory-reasoning.svg    docs/diagrams/memory-reasoning.svg
git mv query-router.svg        docs/diagrams/query-router.svg
git mv domain-erd.svg          docs/diagrams/domain-erd.svg
# Después: editar las 5 líneas <img src="./..."> del README -> "./docs/diagrams/..."
```

### 7.5 Subir los documentos de este sprint (opcional)

```powershell
git add DIAGRAM_FINAL_PACKAGE.md SVG_PACKAGE_FINAL.md README_FINAL_POLISH_REPORT.md REPOSITORY_RELEASE_PLAN.md
```

### 7.6 Verificación previa a cualquier commit (no es un commit)

```powershell
git status --short
git ls-files "*.svg" "*.png"
git check-ignore .local/scripts/run_demo.py
```

---

## 8. Resumen ejecutivo

| # | Acción | Destino | Estado en este sprint |
| - | ------ | ------- | --------------------- |
| 1 | Subir 5 SVG | raíz (Opción A) | comandos listos, **no ejecutados** |
| 2 | Subir 3 PNG | `docs/screenshots/` | comandos listos, **no ejecutados** |
| 3 | Mover 3 scripts | `scripts/` (trackeado) | decisión: **mover y subir**; ajustes de código en fase aparte |
| 4 | Estructura `docs/` | `docs/{diagrams,screenshots,reports,validation,architecture}` | propuesta; **nada movido** |

**Bloqueante de release**: los 5 SVG sin trackear → 404 en GitHub. Es la única acción imprescindible
para que el README congelado se vea completo.

---

*Sin commits. Sin push. Sin archivos movidos. Documento generado en la raíz del repositorio.*
