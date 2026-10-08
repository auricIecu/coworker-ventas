# Dataset sintético de mostrador — v1

Referencia de la demo anterior de reservas. No alimenta el analista de back office.
El dataset vigente para el encargado está en [../backoffice/README.md](../backoffice/README.md).

[dataset.json](dataset.json) contiene un snapshot original para los cinco casos del
copiloto: encontrar productos, consultar precio/stock, preparar reservas, consultar
historial del cliente y explicar promociones. Es JSON UTF-8, portable a los servicios
que habilite el evento. No necesita cuentas, APIs ni datasets externos.

**Todo es inventado.** No representa el catálogo, precios, clientes, reglas o promociones
de Farmaenlace ni otra empresa. No se utilizaron Kaggle, documentos privados,
registros reales ni código ajeno para generarlo. Se distribuye bajo MIT.

## Alcance y estado de integración

El archivo está listo para construir adaptadores y pruebas. **No se carga automáticamente
en la API actual**: esta conserva su seed mínimo de tres SKU y su propio inventario.
No se han implementado todavía rutas de clientes, historial ni promociones en esa API.
El generador y el validador son herramientas de fixtures, no un motor comercial de producción.

Los 30 productos son insumos no farmacológicos, higiene y cuidado personal. No hay
medicamentos, principios activos, dosificaciones, diagnósticos ni equivalencias terapéuticas.
Cada persona se identifica como `Cliente ficticio NNN`; no hay teléfonos, direcciones,
correos, documentos, fechas de nacimiento ni otros identificadores personales.

## Contenido

| Tabla JSON | Filas | Clave | Relaciones / uso |
| --- | ---: | --- | --- |
| `categories` | 6 | `category_id` | Clasificación comercial, no clínica |
| `branches` | 3 | `branch_id` | Centro, Norte y Sur, todas ficticias |
| `products` | 30 | `sku` | Categoría, presentación y unidad comercial |
| `price_lists` | 3 | `price_list_id` | General, club y alianza ficticios |
| `prices` | 90 | `(sku, price_list_id)` | Un precio vigente por SKU/lista |
| `inventory` | 90 | `(sku, branch_id)` | Existencias, reservas y hora observada |
| `customers` | 12 | `customer_id` | Segmento, membresía y sucursal preferida |
| `purchases` | 30 | `purchase_id` | Cliente, sucursal, fecha y total de venta |
| `purchase_lines` | 60 | `(purchase_id, line_number)` | Producto, cantidad y precios históricos |
| `promotions` | 8 | `promotion_id` | Vigencia, elegibilidad, beneficio y combinabilidad |
| `reservation_proposals` | 8 | `proposal_id` | Propuesta y, solo si se confirmó, recibo de reserva |
| `reservation_events` | 19 | `(proposal_id, sequence)` | Quién propuso/aprobó y resultado |
| `scenarios` | 31 | `scenario_id` | Pregunta, entrada estructurada y respuesta esperada |

`metadata` identifica versión, origen, licencia, moneda y fecha de corte. `business_rules`
contiene las convenciones que todos los consumidores deben respetar.

## Reloj y reproducibilidad

El corte es **2026-10-08T14:00:00Z**. Todas las fechas son UTC ISO 8601; todas las
ventanas se interpretan como `[valid_from, valid_until)`: inicio inclusivo, fin exclusivo.

Las pruebas usan ese reloj fijo, no la hora actual. Un mes después, la misma fixture
sigue describiendo el mismo momento; no significa que sus ofertas sigan vigentes en vivo.
Si se cambia la fecha de demo hay que mover coherentemente membresías, compras, precios,
promociones, stock y eventos, y volver a calcular las respuestas esperadas.

No hay aleatoriedad ni Faker. La fuente editable es
[src/mostrador/synthetic.py](../../src/mostrador/synthetic.py); el JSON se deriva de ella.

```sh
# Desde la raíz del repo: verifica integridad y coincidencia exacta con el generador.
uv run python -m mostrador.synthetic --check data/synthetic/dataset.json

# Exporta una copia nueva; la carpeta destino debe existir.
# Se niega a sobrescribir un archivo existente.
uv run python -m mostrador.synthetic --output .local/dataset-v1.json

# Sin argumentos imprime JSON en stdout, sin modificar archivos ni bases de datos.
uv run python -m mostrador.synthetic

uv run pytest tests/test_synthetic.py tests/test_synthetic_scenarios.py -q
```

Para actualizar el dataset: editar el generador y las expectativas que deban cambiar,
exportar a una ruta nueva, revisar el diff y reemplazar el JSON versionado de forma
explícita. No corregir solo el JSON: la verificación de reproducibilidad lo rechazará.

## Diccionario de datos y reglas

### Productos: identificar antes de actuar

`sku` identifica una **presentación vendible**, no una familia de productos.
`name`, `category_id`, `presentation` y `aliases` permiten buscar y pedir aclaración.
`sell_unit` es la unidad de venta; `content_quantity` y `content_unit` describen lo
que contiene. `active=false` impide ofrecer un producto retirado.

Por ejemplo, `DEMO-001` son gasas en un paquete de 10 unidades y `DEMO-004` en uno de 20.
Pedir "gasas" es ambiguo. Pedir dos de `DEMO-001` significa **dos paquetes**, no dos gasas.
No se fraccionan empaques ni se sustituyen presentaciones automáticamente.
`DEMO-030` está retirado y `DEMO-029` no tiene disponibilidad en ninguna sucursal.

### Precios aplicables

`prices` contiene `unit_price_cents`, `currency`, vigencias, versión y `updated_at`.
El precio depende de SKU y lista, no de sucursal en esta versión. Todo está en centavos
enteros USD; 700 equivale a USD 7,00. Son precios finales ficticios: no hay cálculo
adicional de impuestos ni se pretende representar normativa tributaria.

Reglas inventadas para la demo:

- `general`: precio base, también para visitantes sin perfil.
- `club`: 95% del precio general, solo con membresía vigente.
- `alianza`: 90% del precio general, solo con membresía vigente.
- Una membresía vencida vuelve a `general`. No inferir segmento por gasto o productos comprados.
- Redondear a centavo con **half-up**: `floor((importe × factor + 5000) / 10000)`
  cuando el factor está en puntos base. No usar el redondeo bancario de `round()`.

Ejemplos: gasas 350 → club 333; shampoo 625 → club 594 o alianza 563.
Los porcentajes de lista se aplican al precio unitario antes de multiplicar por cantidad.
Las promociones se calculan después; **no descontar otra vez el beneficio de la lista**.

### Stock y actualización

`on_hand` es existencia física reportada; `reserved` es cantidad retenida en reservas
confirmadas activas; `available = on_hand - reserved`. Se mide en unidades de venta.
`version` identifica el snapshot comercial y `observed_at` su hora de observación.

- `DEMO-001` en Centro: 8 físicos, 2 reservados, **6 disponibles**.
- `DEMO-002` en Centro: agotado; Norte tiene 9 y Sur 3 disponibles.
- `DEMO-010` en Sur: observación de un día antes. Más de 900 segundos de antigüedad
  obliga a consultar de nuevo antes de prometer stock.
- El resto tiene una observación diez segundos anterior al corte.

El inventario es un snapshot después de movimientos previos. **No volver a descontar
las compras históricas ni las reservas ya reflejadas** al importarlo. No se entrega un
libro completo de entradas, reposiciones y movimientos de almacén.

### Cliente e historial

`customers` vincula `customer_id`, `display_name`, `segment`, estado y vigencia de
membresía, y sucursal preferida. No simula permiso legal para consultar personas reales:
el futuro adaptador debe autenticar y autorizar el acceso al perfil.

`purchases` es la cabecera y `purchase_lines` el detalle. Los importes históricos se
guardan en la línea; no deben recalcularse usando precios o promociones de otra fecha.
Cada cabecera suma subtotales, descuentos y totales de sus líneas. Son ventas ficticias
completadas, no transacciones bancarias ni información de medios de pago.

- `DEMO-C001`: tres compras, total **2933 centavos**, última compra el 7 de octubre;
  `DEMO-001` aparece en dos compras. No se deduce ninguna condición médica de ello.
- `DEMO-C011`: cliente existente sin compras. Mostrar "sin historial", no inventar actividad.
- `DEMO-C012`: membresía club vencida; aplica precio general.
- `DEMO-C999`: no existe. No confundir "no encontrado" con "sin compras".

Esto permite una vista comercial básica, no un perfil 360 real completo ni una
recomendación clínica/personalizada ya implementada en el agente.

### Promociones: vigencia, restricciones y combinación

Cada promoción declara SKU, listas y sucursales elegibles, fechas, cantidad mínima,
subtotal mínimo, beneficio, prioridad y combinaciones permitidas. No hay cupones en v1.

| ID | Beneficio | Restricciones principales |
| --- | --- | --- |
| `DEMO-P01` | 10% gasas de 10 | Mínimo dos paquetes, general/club; permite P02 |
| `DEMO-P02` | 5% gasas de 10 | Solo Centro y lista general; permite P01 |
| `DEMO-P03` | 15% shampoo | Solo club, presentaciones 250/500 ml |
| `DEMO-P04` | Jabón 3x2 | Mismo SKU, general/club, grupos completos de tres |
| `DEMO-P05` | 20% gasas | Vencida al momento del corte |
| `DEMO-P06` | 25% gasas | Empieza después del corte |
| `DEMO-P07` | 8% shampoo 250 ml | Solo alianza |
| `DEMO-P08` | 10% gasas | Solo Norte, general, subtotal mínimo 1000 centavos |

La selección es explícita: **no hay algoritmo de mejor oferta automática**. Primero
comprobar fechas, SKU, sucursal, lista, cantidad y subtotal; después, combinación.
Todas las parejas deben permitirse mutuamente. `combinable_with=[]` significa exclusiva,
no "se combina con todo". La prioridad ordena la aplicación de menor a mayor.

El subtotal mínimo se evalúa sobre el precio de lista × cantidad **antes** de descuentos
promocionales. Cada descuento porcentual se calcula sobre el saldo de la línea y se
redondea half-up. El descuento nunca supera el saldo. El 3x2 regala una unidad comercial
por cada grupo completo de tres del mismo SKU: cuatro jabones pagan tres, no dos.

Ejemplo verificable, gasas × 2 en Centro con P01 y P02:

```text
Subtotal: 350 × 2              = 700 centavos
P01: 10% de 700                =  70
Saldo                         = 630
P02: 5% de 630, half-up(31,5)   =  32
Total                         = 598 centavos (USD 5,98)
```

P01 y P08 son incompatibles aunque ambas pudieran aplicar por separado en Norte.
No ofrecer el descuento club a un cliente con lista general. No prometer ahorro
usando una promoción futura o vencida.

### Propuestas, reservas y eventos

`reservation_proposals` modela **estados del flujo**, no solamente reservas existentes:

| Estado | Significado de la fixture |
| --- | --- |
| `pending` | Propuesta sin ejecutar; no retiene stock |
| `executing` | Aprobada, resultado pendiente; no volver a despachar |
| `executed` | Reserva confirmada; contiene `receipt` y stock retenido |
| `rejected` | Rechazo humano; sin reserva |
| `expired` | Propuesta vencida; sin reserva |
| `failed` | Cambio de oferta rechazado sin efecto confirmado |
| `uncertain` | No se sabe si el proveedor ejecutó; reconciliar, no reintentar |

Se preservan cantidad, precio cotizado, versión, condiciones, vencimiento, actor,
cliente y claves de idempotencia. La propuesta dura 300 segundos; una reserva confirmada
de estas fixtures conserva el stock 3600 segundos después de ejecutarse. **Ese plazo de
reserva es una condición del dataset, no un scheduler implementado en la API actual.**

Solo `DEMO-R003` y `DEMO-R008` tienen recibos confirmados `held`; sus cantidades están
incluidas en `inventory.reserved`. No deducir un recibo o un descuento adicional del
stock para estados `executing`/`uncertain`. Es una vista de resultados **conocidos**;
el estado autoritativo de esas operaciones pendientes exige consultar al proveedor.

No insertar estas propuestas directamente en las tablas de la demo actual: el JSON es
un modelo de fixtures más amplio que sus DTO. No reenviar sus IDs como acciones reales.

## Escenarios para el futuro agente

Cada entrada de `scenarios` tiene `scenario_id`, `capability`, `question`, `as_of`,
`input` estructurado y `expected`. Las preguntas están en español y cubren tanto
respuestas comerciales como cuándo pedir aclaración, abstenerse o solicitar aprobación.

Los 31 resultados son literales revisados con cálculos y consultas independientes en
[tests/test_synthetic_scenarios.py](../../tests/test_synthetic_scenarios.py). **No son una
evaluación de un agente real ni una promesa de que la API actual responda esas preguntas.**

Para evaluar al agente, entregarle la pregunta y acceso solo a las tablas/herramientas
necesarias. **No incluir `scenarios.expected` en su contexto**: son el resultado reservado
al evaluador. No usar todo el JSON como un documento para que el LLM calcule dinero,
interprete permisos o invente stock. Esas reglas se ejecutan fuera del modelo.

## Integración posterior

1. Cargar productos, listas/precios e inventario en el proveedor o adaptador autorizado.
2. Extender contratos de cliente/historial/promociones de forma explícita; hoy no existen.
3. Implementar cotización comercial determinista con los casos de referencia.
4. Reutilizar el flujo de propuesta/aprobación, sin dar al modelo acceso directo a escrituras.
5. Ejecutar los escenarios contra el sistema integrado, distinguiendo respuestas, permisos
   y efectos sobre el stock; declarar siempre qué datos son simulados.

No se subió nada a AWS. Mantener privados los códigos de acceso del evento y no incorporar
los PDFs adjuntos en este directorio. El dataset por sí solo no resuelve la autorización
para reutilizar código preparado antes del hackatón.
