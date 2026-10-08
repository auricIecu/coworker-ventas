# Mostrador Implementation Plan

Plan histórico ya ejecutado. El alcance vigente es [Sales Back Office](../../design.md).

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task in the existing isolated workspace.

**Goal:** Entregar una base abierta y ejecutable para un copiloto de mostrador con proveedores reemplazables.

**Architecture:** Dominio y casos de uso independientes de FastAPI y proveedores. Cuatro puertos: comercio, workflow/auditoría, identidad e interpretación. SQLite y búsqueda determinista implementan una demo sin credenciales.

**Tech Stack:** Python >=3.11, FastAPI, SQLite estándar, pytest, uv.

**Spec:** `docs/design.md`

## Global Constraints

No copiar código, datos, prompts, recursos ni conectores existentes. Cantidades
enteras, dinero en centavos, aprobación humana, control de versiones, idempotencia
y estados inciertos sin retry. Una organización por instalación; ninguna
integración real ni UI de producto en esta entrega. `.context` nunca se publica.

## Task 1: Workflow independiente

Files: `src/mostrador/domain.py`, `ports.py`, `service.py`, `adapters/sqlite.py`,
`adapters/demo.py`, `tests/test_workflow.py`.

Interfaces: `Commerce.search/quote/reserve`, `WorkflowStore.create/get/claim/finish/events`,
`Identity.authenticate`, `Assistant.interpret`. La composición recibe instancias;
la aplicación no decide cuál proveedor implementa cada puerto.

- [x] Crear pruebas del comportamiento comercial: propuesta sin descuento de stock,
  aprobación única, rechazo sin escritura comercial, conflicto tras cambio de stock,
  permisos, expiración, bloqueo de reintento incierto y concurrencia.
- [x] Ejecutar `uv run pytest tests/test_workflow.py -q` y observar fallos por funciones ausentes.
- [x] Implementar objetos inmutables, puertos y casos de uso. La reserva SQLite usa:
  `UPDATE offers SET available = available - ?, version = version + 1 WHERE sku = ? AND branch_id = ? AND version = ? AND available >= ?`.
- [x] Verificar resultados e inventario con las mismas pruebas.

## Task 2: API y composición

Files: `src/mostrador/api.py`, `bootstrap.py`, `tests/test_api.py`.

- [x] Probar rechazo de identidad ausente, campos extra/roles inyectados y cantidades
  inválidas; probar consulta, propuesta, aprobación y eventos por HTTP.
- [x] Implementar `create_app()` con inyección del bundle `Adapters` y configuración
  de entorno; un factory externo es un módulo local de confianza, no input HTTP.
- [x] Verificar con `uv run pytest tests/test_api.py -q`.

## Task 3: Portabilidad y entrega pública

Files: `README.md` (incluye demo), `docs/architecture.md`, `docs/providers.md`,
`docs/provenance.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `Dockerfile`,
`.env.example`, `.github/workflows/ci.yml`, `examples/local_factory.py`.

- [x] Documentar arranque, límites, contrato frontend/OpenAPI y sustitución de puertos.
- [x] Incluir factory local ejecutable que pruebe el punto de extensión sin un vendor.
- [x] Bloquear arranque external sin factory y con adaptadores demo.
- [x] Fijar dependencias con `uv lock`; comprobar `uv sync --locked`.
- [x] Ejecutar `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check src tests examples`.
- [x] Arrancar la API y ejecutar por HTTP una reserva con token demo; revisar archivos
  y archivos publicables. No modificar visibilidad remota como parte del scaffolding.

## Verificación local — 2026-10-07

- Python 3.12: 40 pruebas pasan; lint y formato pasan.
- `uv sync --locked` y `uv build` completados. Contenido de wheel/sdist inspeccionado;
  no incluye `.context`, material de terceros, bases ni credenciales.
- Servidor real en loopback: consulta → propuesta → aprobación → reenvío → eventos, OK.
- Una advertencia upstream de deprecación de `httpx` en Starlette TestClient; sin fallos.
- Dockerfile y CI incluidos, pero no ejecutados: daemon Docker no disponible;
  workflow remoto y matriz Python 3.11 pendientes de la primera ejecución de CI.
- Sin push ni cambio de visibilidad; el remoto existente permanece privado.
