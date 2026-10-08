# Sales Coworker — Sales Back Office

Analista comercial para el encargado comercial o jefe de área o zona de Farmaenlace.
Cruza señales de conversaciones de WhatsApp, movimientos de inventario por sucursal,
stock actual y promociones para proponer dónde abastecer y dónde evaluar una promoción.
El encargado revisa la evidencia y aprueba o rechaza dentro de su sucursal o zona;
ninguna acción externa se ejecuta
sin una decisión humana y un conector autorizado.

**Estado:** bandeja visual ejecutable, fuentes sintéticas completas, interpretación con
Amazon Bedrock (opcional), cálculos deterministas y revisión humana persistente.
No está conectado a datos ni operaciones reales de Farmaenlace.

## Arranque

Requisitos: Python 3.11+ y uv.

```sh
uv sync --locked
COPILOT_MODE=demo uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000. La bandeja permite elegir un perfil demo.
Swagger está en `/docs`; usa **Authorize** con `demo-encargado`.
`demo-encargado` opera Guayaquil Centro; `demo-jefe-zona` opera Centro y Norte.
`demo-encargado-quito` opera Quito. `demo-viewer` solo consulta Centro.
Los permisos se comprueban en el servidor, también al acceder por ID.
Estos tokens son públicos: usar solamente en local.

Sin configuración adicional se usa `SALES_AI_MODE=offline`: simulación local explícita,
no IA. Para interpretar las conversaciones con AWS:

```sh
AWS_PROFILE=sales-hackathon AWS_REGION=us-east-1 SALES_AI_MODE=bedrock \
COPILOT_MODE=demo uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

El perfil temporal debe existir fuera del proyecto. Modelo predeterminado:
`amazon.nova-lite-v1:0`, configurable mediante `SALES_BEDROCK_MODEL`.
Si AWS falla no se sustituye silenciosamente por resultados locales. Una instancia,
un worker, llamadas serializadas con separación mínima de 1,05 segundos y sin reintentos SDK.

Pulsa **Analizar fuentes** para el primer análisis. Para detectar posteriormente nuevas
conversaciones sintéticas en segundo plano:

```sh
COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=30 uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

El ciclo analiza las fuentes de la bandeja cuando cambian, después del primer análisis manual.
No conecta WhatsApp ni refresca sistemas externos.
Los datos incluidos tienen un corte fijo del 8 de octubre de 2026, no son datos en vivo.
`SALES_SNAPSHOT_PATH` configura únicamente la API histórica `/analysis/run`, no `/workspace`.
No cargar datasets reales en esta demo: `synthetic:true` es una declaración del remitente,
no un detector ni anonimizador de información personal.

`COPILOT_DB_PATH` selecciona el archivo SQLite; por defecto `.local/sales.sqlite`.
La bandeja usa el archivo derivado `<COPILOT_DB_PATH>.workspace.sqlite`, separado de la
API histórica. Para una sesión nueva, usa otra ruta. Reiniciar conserva fuentes y decisiones.
`.env.example` documenta variables y no se carga automáticamente.

## Recorrido de demo

1. **Analizar fuentes**: interpreta 40 conversaciones y consulta documentos comerciales.
2. **Simular 6 consultas**: añade interés por Vitamina C en Guayaquil Centro, una sola vez.
3. **Analizar fuentes**: sube de dos a ocho consultas recientes, frente a dos anteriores.
4. Selecciona Vitamina C de Centro: 180 disponibles (18%), objetivo 680, reposición de 500.
5. Revisa conversaciones, movimientos y documentos citados; la propuesta añade una
   promoción de siete días condicionada a reponer/revalidar stock y definir condiciones.
6. **Aprobar intención** o **Rechazar propuesta**, confirma y revisa el historial de eventos.

API para el compañero: `GET /workspace`, `POST /workspace/analyze`,
`POST /workspace/demo/burst`, `POST /workspace/conversations`,
`POST /workspace/recommendations/{id}/decision` y
`GET /workspace/recommendations/{id}/events`. [Contrato y plan](docs/superpowers/plans/2026-10-08-context-bedrock.md).
En **Explorar fuentes** están los mensajes, documentos, movimientos e inventario del perfil.

La cuenta de Centro recibe dos propuestas: reabastecer 500 unidades de Vitamina C
ficticia y evaluar una promoción de jabón. Tras la simulación, la primera incluye una
promoción de siete días condicionada a reponer y revalidar stock. No propone otra campaña de
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
- Bedrock interpreta texto, identifica producto/sucursal y selecciona documentos; el servidor
  valida referencias y calcula cantidades. Casos ambiguos no suman señales comerciales.
- Seis documentos ficticios con vigencia, sucursal, productos y condiciones tipadas.
- Citas textuales, faltantes y aprobación requerida. Caché persistente e invalidación por contexto.
- Bandeja visual accesible, ejecución manual y ciclo periódico opcional.
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

- Conectores autorizados para WhatsApp, inventario y promociones.
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
node --test tests/ui/app.test.cjs
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

Pregunta lista para el mentor (aún no enviada): «¿Habrá datasets oficiales autorizados de
consultas, ventas/inventario y condiciones comerciales? ¿Qué campos, sucursales y corte
temporal incluirán? Continuamos con fuentes sintéticas sin depender de esa entrega».
