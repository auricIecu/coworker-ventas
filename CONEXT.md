# Contexto para continuar — Sales Coworker / Sales Back Office

Actualizado: 8 de octubre de 2026. Este es el contexto vigente del proyecto.
El usuario redefinió el producto como un analista comercial proactivo para primera línea.
La antigua demo de mostrador queda solo como referencia técnica.

## Usuario y problema

El usuario es el encargado comercial o jefe de área/zona de Farmaenlace, responsable
operativo de primera línea; no el estratega corporativo ni el cliente final.
Decide qué productos abastecer, en qué sucursales y qué promociones evaluar.
La hipótesis es que las señales dispersas entre conversaciones, inventario y promociones
llegan tarde a esas decisiones. Debe validarse con usuarios y métricas.

## Propuesta

«Convertimos la avalancha de datos operativos de Farmaenlace en decisiones concretas
para el encargado de primera línea, antes de perder el stock y la venta».

La presentación del reto menciona 172 mil transacciones diarias, 17.000 productos,
1.422 puntos de venta y diez años de historial comercial. Son cifras de contexto de
la organización, no volumen procesado ni validado por esta demo.
La capa complementa SAP, Big Data, Airflow y modelos predictivos existentes; no los sustituye.

El sistema analiza en segundo plano y propone. El humano decide.
Autonomía de observación y análisis no significa autonomía de ejecución.

Fuentes necesarias:

1. Conversaciones de WhatsApp: intención de consulta, SKU, sucursal o ciudad, fecha y
   un ID pseudónimo de conversación; las menciones repetidas no son clientes nuevos.
2. Movimientos de inventario: ventas, recepciones y ajustes, con unidades y tiempo.
3. Catálogo, stock actual y promociones: producto exacto, sucursal, objetivo de stock,
   hora de observación y vigencia de cada promoción.

Una conversación no demuestra una venta futura. Una promoción no resuelve por sí sola
la falta de stock. Priorizar abastecimiento si la disponibilidad es insuficiente;
evaluar promociones con disponibilidad y condiciones comerciales verificadas.

## Estado implementado

- API local FastAPI en `src/mostrador/backoffice_api.py`.
- Contrato de snapshot y análisis determinista en `src/mostrador/backoffice.py`.
- Bandeja, aprobación/rechazo y eventos SQLite en `src/mostrador/backoffice_store.py`.
- Fixture sintética empaquetada en `src/mostrador/data/backoffice_demo.json`.
- Análisis al arrancar, bajo demanda y periódico opcional.
- Evidencia por propuesta: IDs de fuentes, ventanas, conversaciones distintas, ventas,
  stock, cobertura y promociones vigentes.
- Permisos demo por sucursal/zona y rol; reenvíos y decisiones concurrentes sin duplicados.
- Propuestas válidas para aprobación durante 15 minutos; una nueva evidencia impide
  aprobar propuestas anteriores aún pendientes. Un nuevo análisis marca pendientes antiguas
  como `superseded`.
- La aprobación solo registra intención. `execution_status=not_configured` siempre.

Incremento fuentes + Bedrock implementado:

- `sales_context.py` y `data/sales/`: 40 conversaciones, seis consultas añadibles,
  cuatro productos, tres sucursales, ventas/recepciones/ajustes y seis documentos ficticios.
- `bedrock.py`: Converse con Nova Lite por defecto, 1 RPS máximo por instancia,
  caché persistente y errores seguros; modo offline explícito sin fallback silencioso.
- `sales_workspace.py`: texto a señales validadas, documentos por vigencia/SKU/sucursal,
  condiciones aplicadas en código, citas originales, faltantes y revisiones requeridas.
- `sales_routes.py`: contrato `/workspace` y frontend en `static/` servido desde `/`.
- Simular consultas → reanalizar → revisar evidencia → aprobar/rechazar, sin ejecutar.
- Reanalizar correctamente renueva propuestas pendientes vencidas con evento `revalidated`;
  nunca reabre decisiones ya tomadas. Cambiar fuentes bloquea aprobar evidencia anterior.

La nueva bandeja extrae el producto desde texto sintético; la sucursal procede de metadata
autorizada. Ante ambigüedad se abstiene; conversaciones sin sucursal no se exponen a perfiles
de sucursal. La API histórica `/analysis/run` conserva señales preetiquetadas por compatibilidad.
No hay escucha de WhatsApp ni infraestructura empresarial conectada. El corte histórico
no se convierte en tiempo real por repetir el análisis.

## Arranque

```sh
uv sync --locked
COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=30 uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

Bandeja: http://127.0.0.1:8000. Swagger: `/docs`. Tokens públicos: `demo-encargado` y `demo-viewer`
para Centro; `demo-jefe-zona` para Centro/Norte; `demo-encargado-quito` para Quito.
Base: `.local/sales.sqlite`. Usar otra ruta con `COPILOT_DB_PATH` para una sesión nueva.
`SALES_SCAN_INTERVAL_SECONDS=0` desactiva el ciclo periódico; el análisis inicial se mantiene.
La bandeja guarda datos en `<COPILOT_DB_PATH>.workspace.sqlite`.
Por defecto `SALES_AI_MODE=offline`; para IA añadir `SALES_AI_MODE=bedrock`,
`AWS_PROFILE=sales-hackathon`, `AWS_REGION=us-east-1` con credenciales fuera del repositorio.
Solo se permite contenido sintético, incluso usando Bedrock. No hay filtro automático de PII.
El ciclo periódico de la bandeja comienza tras el primer análisis manual y actúa al cambiar fuentes.

## Historia de demo

En Guayaquil Centro, una sucursal ficticia:

- Vitamina C: ocho conversaciones frente a dos, 560 unidades vendidas en siete días,
  180 disponibles de un nivel de referencia de 1.000 (18%). El objetivo de reposición
  demo es 680: propone 500 unidades y evaluar una promoción de siete días solamente
  después de reponer/revalidar stock. No prescribe ni recomienda consumo del producto.
- Jabón: seis conversaciones frente a dos, stock suficiente y sin promoción.
  Propone evaluar una promoción; no inventa descuento, presupuesto ni retorno.
- Pañuelos: interés creciente, stock suficiente y promoción vigente. No duplica campaña.

Norte y Quito añaden casos separados para comprobar el alcance por sucursal/zona.
El encargado revisa evidencia y aprueba/rechaza. No se simula una compra real exitosa ni
se afirma que una aprobación publicó una campaña. Las cantidades sugeridas son heurísticas
de demo, sin mínimos de proveedor, plazos de entrega ni optimización logística.

El pitch utilizable está en [docs/checkpoint-1.md](docs/checkpoint-1.md).

## Arquitectura y próximos incrementos

Leer [diseño](docs/design.md), [arquitectura](docs/architecture.md),
[datos](data/backoffice/README.md) y [proveedores](docs/providers.md).

1. UI y extracción Bedrock implementadas; completar evaluación con escenarios reservados.
2. Validar condiciones comerciales y heurísticas con el mentor/usuario operativo.
3. Conectar las tres fuentes autorizadas y registrar cobertura, frescura y procedencia.
4. Evaluar detección contra escenarios reservados al evaluador.
5. Diseñar ejecución: payload exacto aprobado, condiciones, vencimiento, permisos,
   idempotencia y estados inciertos. No despachar automáticamente una propuesta vieja.
6. Medir beneficio y preparar pitch de tres minutos.

Los módulos de reservas `domain.py`, `service.py`, `ports.py`, `adapters/` y `api.py`
siguen como referencia compatible. Sus estados y su aprobación de reserva no equivalen
a aprobar una campaña o una compra. El dataset `data/synthetic/` también es anterior.

## Reglas de trabajo y confidencialidad

- Implementación independiente: no incorporar código, prompts, bases, configuraciones,
  reglas particulares ni recursos visuales privados de otros productos.
- No conectar cuentas empresariales ni cargar conversaciones reales como paso implícito.
- Conservar licencias y avisos de los componentes que sí se distribuyen.
- No versionar ni empaquetar `.context/`, adjuntos, secretos, logs o bases locales.
- No poner material propietario en prompts, fixtures, evaluaciones o documentos públicos.
- Documentar lo implementado, lo simulado y lo pendiente por separado.
- No prometer disponibilidad total ni impacto comercial todavía no medido.

## Evento

Los cinco PDFs de agenda, AWS, rúbrica, reglas y presentación están en
`.context/attachments/`; son referencia local y no se distribuyen.
La agenda adjunta fija cierre a las 15:45 y pitch de tres minutos.
La rúbrica asigna 30 puntos a valor/impacto, 25 a ejecución técnica, 20 a diferenciación,
15 a viabilidad y 10 a presentación.
Las reglas requieren declarar herramientas y trabajo previo, y no llegar con el producto
ya armado. La guía AWS pide datos permitidos/sintéticos y limita IA generativa a 1 RPS.
La propuesta busca contribuir a mejora operativa, servicio y fidelización; esos beneficios
son hipótesis, no resultados verificados.
