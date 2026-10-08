# Sales Coworker — Sales Back Office

Analista comercial para el encargado comercial o jefe de área o zona de Farmaenlace.
Cruza señales de conversaciones de WhatsApp, movimientos de inventario por sucursal,
stock actual y promociones para proponer dónde abastecer y dónde evaluar una promoción.
El encargado revisa la evidencia y aprueba o rechaza dentro de su sucursal o zona;
ninguna acción externa se ejecuta
sin una decisión humana y un conector autorizado.

**Estado:** base local ejecutable con análisis determinista, datos sintéticos y revisión
persistente. Todavía no es un agente con LLM ni una integración real con Farmaenlace.
La interfaz de producto está pendiente; Swagger permite explorar la API.

## Arranque

Requisitos: Python 3.11+ y uv.

```sh
uv sync --locked
COPILOT_MODE=demo uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000/docs y usa **Authorize** con `demo-encargado`.
`demo-encargado` opera Guayaquil Centro; `demo-jefe-zona` opera Centro y Norte.
`demo-encargado-quito` opera Quito. `demo-viewer` solo consulta Centro.
Los permisos se comprueban en el servidor, también al acceder por ID.
Estos tokens son públicos: usar solamente en local.

Se analiza el snapshot al arrancar. Para repetir el análisis en segundo plano:

```sh
COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=30 uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

El ciclo relee el snapshot configurado; no conecta WhatsApp ni refresca sistemas externos.
Los datos incluidos tienen un corte fijo del 8 de octubre de 2026, no son datos en vivo.
`SALES_SNAPSHOT_PATH` permite seleccionar otro JSON **sintético** validado con el mismo
contrato. No se admiten datasets reales en esta demo.

`COPILOT_DB_PATH` selecciona el archivo SQLite; por defecto `.local/sales.sqlite`.
Para una sesión nueva, usa otra ruta. Reiniciar conserva las decisiones.
`.env.example` documenta variables y no se carga automáticamente.

## Recorrido de demo

1. `POST /analysis/run`: cruza las tres fuentes y devuelve evidencia por producto/sucursal.
2. `GET /recommendations`: consulta la bandeja, incluidos los estados anteriores.
3. `GET /recommendations/{id}`: revisa ventana, consultas, ventas, stock y promociones.
4. `POST /recommendations/{id}/decision`: envía `{"decision":"approve"}` o `{"decision":"reject"}`.
5. `GET /recommendations/{id}/events`: comprueba quién tomó la decisión y cuándo.

La cuenta de Centro recibe dos propuestas: reabastecer 500 unidades de Vitamina C
ficticia y evaluar una promoción de jabón. La primera incluye una promoción propuesta
de siete días, condicionada a reponer y revalidar stock. No propone otra campaña de
pañuelos porque ya hay una vigente. El jefe de zona recibe también la propuesta de Norte.
La aprobación queda como `approved`, con `execution_status: not_configured`.
**Aprobar no compra, transfiere, reserva stock ni publica promociones.**
Repetir un análisis idéntico no duplica propuestas; repetir una decisión no duplica eventos.
Una propuesta nueva necesita su propia aprobación cuando cambia la evidencia.

## Qué está preparado

- Contratos validados de productos, sucursales, señales de conversaciones, movimientos,
  stock y promociones; sin teléfonos, contactos ni mensajes reales.
- Comparación de ventanas equivalentes, conversaciones distintas, cobertura de stock
  y vigencia de promociones. Reglas demo explícitas, sin predicción de ventas.
- Abstención ante inventario antiguo; sin base comparable no se afirma crecimiento.
- Propuestas, permisos por sucursal/zona, decisiones persistentes y eventos en SQLite.
- Análisis inicial, ejecución manual y ciclo periódico opcional.
- Pruebas, Dockerfile, CI y dependencias fijadas.

[Pitch para el Checkpoint #1](docs/checkpoint-1.md).
[CONEXT.md](CONEXT.md) contiene el contexto vigente y los siguientes pasos.
[Diseño](docs/design.md), [arquitectura](docs/architecture.md),
[contratos de datos](data/backoffice/README.md) y [conectores pendientes](docs/providers.md).

## Encaje con la infraestructura existente

La capa de recomendaciones complementa SAP, Big Data, Airflow y los modelos existentes.
Los conectores futuros leerán fuentes autorizadas y devolverán acciones aprobadas al
sistema responsable. La demo no modifica ni sustituye esos sistemas y no está conectada a ellos.

## Trabajo que falta para el producto

- Bandeja visual del encargado y explicación conversacional de cada recomendación.
- Conectores autorizados para WhatsApp, inventario y promociones.
- Extracción de intenciones con IA: hoy SKU y sucursal vienen etiquetados en la fixture.
- Ejecutor externo que revalide condiciones y permisos después de aprobar.
- Autenticación real, aislamiento por organización, monitoreo y evaluación del agente.
- Medición de impacto: tiempo de análisis, aceptación de propuestas y roturas de stock.

No se ha demostrado aumento de ventas, fidelización ni disponibilidad garantizada.
El volumen de consultas expresa interés, no demanda convertida ni causalidad de una promoción.

## Verificación

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests examples
uv build
```

Docker opcional:

```sh
docker build -t sales-coworker .
docker volume create sales-coworker-demo
docker run --rm -p 127.0.0.1:8000:8000 -e COPILOT_MODE=demo \
  -e COPILOT_DB_PATH=/app/data/sales.sqlite -v sales-coworker-demo:/app/data sales-coworker
```

## Referencia técnica anterior

El paquete interno conserva el nombre `mostrador` para compatibilidad.
`mostrador.api:create_app` y `data/synthetic/` son la demo anterior de reservas:
no representan el producto actual ni alimentan automáticamente este análisis.
Se conservan sus pruebas y su [arquitectura de reservas](docs/reservations-architecture.md)
como referencia para una futura ejecución supervisada. El comando principal es el de arriba.

## Licencia y materiales

La base conserva su [licencia MIT y copyright](LICENSE).
Ver [procedencia](docs/provenance.md), [contribución](CONTRIBUTING.md) y [seguridad](SECURITY.md).
Los adjuntos del evento permanecen en `.context/`, fuera de Git, Docker y los paquetes.
Declarar la base y herramientas previas según las reglas del hackatón.
