# Contexto para continuar — Sales Coworker / Sales Back Office

Actualizado: 8 de octubre de 2026. Este es el contexto vigente del proyecto.

## Usuario y problema

El usuario objetivo es el encargado comercial o jefe de área/zona de Farmaenlace
(incluye Medicity, tiendas de mascotas y otras marcas del grupo), responsable
operativo de primera línea. No es el estratega corporativo ni el cliente final.
Decide qué productos abastecer, en qué sucursales y qué promociones evaluar.

La hipótesis central: las señales dispersas entre conversaciones, inventario y
promociones llegan tarde a esas decisiones. Debe validarse con usuarios y métricas.

## Propuesta de valor

«Convertimos la avalancha de datos operativos de Farmaenlace en decisiones concretas
para el encargado de primera línea, antes de perder el stock y la venta».

La organización maneja 172 mil transacciones diarias, 17.000 productos, 1.422 puntos
de venta y diez años de historial comercial. Estas son cifras de contexto; no son
volúmenes procesados ni validados por esta demo.

La capa complementa SAP, Big Data, Airflow y modelos predictivos existentes; no los
sustituye. El sistema analiza en segundo plano y propone. El humano decide.
Autonomía de observación y análisis no significa autonomía de ejecución.

## Arquitectura de tres agentes (HQ de agentes)

El núcleo diferenciador del producto es un pipeline de tres agentes que trabajan
en paralelo y se cruzan para producir insights accionables. Los tres perfiles son
fijos; puede haber más de un agente por perfil en una implementación real.

### Agente 1 — Perfilador de clientes (`agents/profiler.py`)

**Responsabilidad:** Analiza cada interacción y compra de los clientes que visitan
cualquier sucursal (Farmaenlace, Medicity, mascotas, etc.) y construye un perfil
acumulativo por cliente pseudónimo.

**Qué produce:**
- Patrones de compra por SKU y presentación.
- Canal preferido (WhatsApp, web, tienda física).
- Meses del año con mayor actividad (estacionalidad individual).
- Afinidad de sucursal.

**Lo que NO hace:** inferencia clínica, diagnóstico, ni uso de datos reales de personas.
Los IDs de cliente son seudónimos opacos.

### Agente 2 — Observador de stock (`agents/stock_observer.py`)

**Responsabilidad:** Agrega la visión completa del inventario desde todas las fuentes
disponibles y calcula métricas de cobertura y tendencias estacionales comparando la
ventana actual contra el período equivalente del año anterior.

**Qué produce:**
- Disponibilidad y cobertura en días para cada par SKU–sucursal.
- Razón de crecimiento año sobre año (YoY).
- Indicadores `low_stock` y `seasonal_spike`.
- Promociones activas por producto y sucursal.

**Lo que NO hace:** conectar con SAP, ERP o cualquier sistema real de inventario.
Trabaja únicamente con datos sintéticos o los que le pasen las fuentes autorizadas.

### Agente 3 — Auditor y ejecutor (`agents/auditor.py`)

**El más importante.** Cruza los perfiles de clientes (Agente 1) con las señales de
stock (Agente 2) para generar insights accionables orientados a ventas.

**Qué produce:**
- `replenish_and_promote`: stock bajo + pico estacional → reponer primero, luego campaña.
- `promote_available`: stock OK + pico → lanzar campaña ahora.
- `replenish_only`: stock bajo, sin pico → solo reabastecer.
- `seasonal_alert`: pico YoY detectado, el manager debe revisar.

**Flujo de decisión:**
1. El Auditor genera el insight con `status=pending` y lo persiste.
2. El manager de sucursal o zona lo revisa y aprueba o rechaza.
3. **Si aprueba:** el Auditor ejecuta de inmediato — genera un `ExecutionRecord`
   (alerta en dashboard, borrador de campaña) y lo registra. `status=executed`.
4. **Si rechaza:** `status=rejected`. El próximo ciclo de `run()` genera insights
   frescos con evidencia actualizada.

**Lo que NO hace:** enviar correos reales, publicar campañas, ejecutar compras ni
despachar automáticamente ninguna propuesta vieja o sin aprobación explícita.

## Endpoints de la API (Swagger en `/docs`)

### Back office original (sin cambios)
- `GET  /health`
- `POST /analysis/run`
- `GET  /recommendations`
- `GET  /recommendations/{id}`
- `POST /recommendations/{id}/decision`
- `GET  /recommendations/{id}/events`

### Sales workspace (sin cambios)
- `GET  /sales/view`
- `POST /sales/run`
- `POST /sales/conversations`
- `POST /sales/burst`
- `POST /sales/decide/{id}`
- `GET  /sales/events/{id}`

### Agent HQ (nuevo — rama `feature/jfede_info`)
- `POST /agents/run` — Corre los tres agentes en secuencia y devuelve insights nuevos.
- `GET  /agents/insights` — Lista todos los insights del actor filtrados por sucursal.
- `GET  /agents/insights/{id}` — Detalle completo con evidencia y registro de ejecución.
- `POST /agents/insights/{id}/decision` — Aprobar o rechazar. La aprobación dispara
  la ejecución simulada inmediatamente.
- `GET  /agents/insights/{id}/events` — Trazabilidad completa de cambios de estado.

**Tokens demo existentes (sin cambios):**
- `demo-encargado` → sucursal `gye-centro-demo`
- `demo-jefe-zona` → sucursales `gye-centro-demo` + `gye-norte-demo`
- `demo-encargado-quito` → sucursal `uio-demo`
- `demo-viewer` → solo lectura, `gye-centro-demo`

## Datos sintéticos

Todos los datos son inventados. No contienen información real de Farmaenlace,
clientes, empleados ni sistemas empresariales.

| Archivo | Contenido |
|---|---|
| `data/sales/operations.json` | Snapshot operativo: productos, sucursales, movimientos, stock, promociones |
| `data/sales/conversations.json` | Conversaciones sintéticas de WhatsApp/web/tienda |
| `data/sales/documents.json` | Procedimientos y condiciones de promoción vigentes |
| `data/sales/burst.json` | Conversaciones adicionales para el modo burst |
| `data/sales/historical_movements.json` | Movimientos del año anterior (oct 2025) para comparación YoY |
| `data/sales/customer_profiles_seed.json` | Perfiles semilla de clientes con historial estacional |
| `data/backoffice_demo.json` | Snapshot legacy de la demo original (Vitamina C, Jabón, Pañuelos) |

## Estado implementado

### Lo que ya funciona
- API FastAPI con Swagger completo en `http://127.0.0.1:8000/docs`.
- Análisis determinista de snapshot (`backoffice.py` → `analyze()`).
- Bandeja de recomendaciones con aprobación/rechazo y eventos en SQLite.
- Propuestas con expiración de 15 minutos; nuevas evidencias marcan pendientes
  anteriores como `superseded`.
- Permisos demo por sucursal/zona y rol; decisiones concurrentes sin duplicados.
- Interpretación de conversaciones con modelo Bedrock (`bedrock.py`) o simulación
  local (`OfflineInterpreter`).
- **Agente 1 — Perfilador** (`agents/profiler.py`): construye perfiles desde
  conversaciones y movimientos sintéticos.
- **Agente 2 — Observador de stock** (`agents/stock_observer.py`): calcula cobertura,
  crecimiento YoY y picos estacionales.
- **Agente 3 — Auditor** (`agents/auditor.py`): cruza ambos, genera insights,
  persiste decisiones y ejecuta (simulado) al aprobar.
- **Endpoints `/agents/`** montados en la misma app FastAPI.

### Lo que está simulado / pendiente
- Conexión real a WhatsApp, SAP, ERP o cualquier sistema de Farmaenlace.
- Envío real de correos, alertas push o publicación de campañas.
- Extracción de SKU/sucursal de mensajes con IA en tiempo real (hoy los mensajes
  sintéticos tienen las señales pre-etiquetadas o el `OfflineInterpreter` las infiere
  por palabras clave).
- Ejecución real de compras o despacho de órdenes.
- Interfaz de usuario (en desarrollo por el equipo de frontend).
- Conexión de los endpoints a fuentes autorizadas reales.

## Arranque

```sh
uv sync --locked
COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=30 uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`

Tokens: `demo-encargado`, `demo-viewer` (Centro); `demo-jefe-zona` (Centro + Norte);
`demo-encargado-quito` (Quito).

Base de datos principal: `.local/sales.sqlite`
Base de datos de insights: `.local/sales_insights.sqlite`

Variables opcionales:
- `COPILOT_DB_PATH` — ruta alternativa para la base principal.
- `SALES_SCAN_INTERVAL_SECONDS=0` — desactiva el ciclo periódico.
- `SALES_SNAPSHOT_PATH` — ruta a un snapshot JSON externo.
- `SALES_BEDROCK_MODEL` — modelo de Bedrock (default: `amazon.nova-lite-v1:0`).
- `AWS_PROFILE`, `AWS_REGION` — credenciales para Bedrock.

Solo se permite `COPILOT_MODE=demo`; los proveedores reales todavía no están
implementados.

## Historia de demo (back office original)

En Guayaquil Centro (sucursal ficticia):
- **Vitamina C:** 8 conversaciones recientes vs. 2 anteriores, 560 unidades vendidas
  en 7 días, 180 disponibles de referencia 1.000 (18%). Propone reponer 500 u. y
  evaluar promoción solo después de reponer stock.
- **Jabón:** 6 conversaciones vs. 2, stock suficiente, sin promoción. Propone evaluar
  una promoción.
- **Pañuelos:** interés creciente, stock suficiente y promoción vigente. No duplica campaña.

Norte y Quito añaden casos separados para comprobar el alcance por sucursal/zona.

## Historia de demo — Agent HQ (nueva)

El mismo escenario visto desde los tres agentes:

1. El **Perfilador** detecta que `cust-anon-001` y `cust-anon-002` compraron Vitamina C
   en octubre del año pasado y de nuevo este año → patrón estacional confirmado.
2. El **Observador** calcula que las ventas de Vitamina C en `gye-centro-demo` crecieron
   ~167% YoY (560 u. este período vs. 210 u. el año anterior) y que el stock cubre
   menos de 3 días → `low_stock=True`, `seasonal_spike=True`.
3. El **Auditor** cruza ambos y genera un insight `replenish_and_promote` de prioridad
   `high`: «Reponer Vitamina C 500 mg en gye-centro-demo: stock bajo + pico estacional».
4. El manager llama a `POST /agents/insights/{id}/decision` con `"approve"`.
5. El Auditor ejecuta: registra un `ExecutionRecord` de tipo `campaign_stub` en el
   dashboard simulado. Ninguna compra ni campaña real se despacha.

## Arquitectura y próximos incrementos

Ver [diseño](docs/design.md), [arquitectura](docs/architecture.md),
[datos](data/backoffice/README.md) y [proveedores](docs/providers.md).

1. **UI de Agent HQ** — interfaz para ver los tres agentes corriendo en paralelo,
   ver perfiles de clientes, señales de stock e insights con evidencia. En desarrollo.
2. **Extracción de señales con IA en tiempo real** — usar Bedrock para extraer SKU,
   sucursal e intención de mensajes reales; validar contra catálogo; separar instrucciones
   de datos.
3. **Conexión de fuentes autorizadas** — registrar cobertura, frescura y procedencia
   de cada fuente real (WhatsApp, SAP, inventario).
4. **Evaluación contra escenarios reservados** — detectar correctamente picos, stock
   bajo y oportunidades de campaña en datos no vistos.
5. **Ejecución real** — definir payload exacto aprobado, condiciones, vencimiento,
   permisos, idempotencia y estados inciertos. No despachar automáticamente.
6. **Medir beneficio** — preparar pitch de tres minutos con impacto estimado.

## Reglas de trabajo y confidencialidad

- Implementación independiente: no incorporar código, prompts, bases, configuraciones
  ni recursos visuales privados de otros productos.
- No conectar cuentas empresariales ni cargar conversaciones reales como paso implícito.
- Conservar licencias y avisos de los componentes que sí se distribuyen.
- No versionar ni empaquetar `.context/`, adjuntos, secretos, logs o bases locales.
- No poner material propietario en prompts, fixtures, evaluaciones o documentos públicos.
- Documentar lo implementado, lo simulado y lo pendiente por separado.
- No prometer disponibilidad total ni impacto comercial todavía no medido.

## Evento

Los cinco PDFs de agenda, AWS, rúbrica, reglas y presentación están en
`.context/attachments/`; son referencia local y no se distribuyen.
La agenda fija cierre a las 15:45 y pitch de tres minutos.
La rúbrica asigna: 30 pts valor/impacto, 25 pts ejecución técnica, 20 pts
diferenciación, 15 pts viabilidad, 10 pts presentación.
Las reglas requieren declarar herramientas y trabajo previo, y no llegar con el
producto ya armado. La guía AWS pide datos permitidos/sintéticos y limita IA
generativa a 1 RPS.
La propuesta busca contribuir a mejora operativa, servicio y fidelización; esos
beneficios son hipótesis, no resultados verificados.
