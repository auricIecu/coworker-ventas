# Snapshot de análisis comercial — demo

La fixture ejecutable está en
[src/mostrador/data/backoffice_demo.json](../../src/mostrador/data/backoffice_demo.json).
Se incluye dentro del paquete para que la demo funcione también después de instalarlo.

Contiene tres productos, tres sucursales ficticias (Guayaquil Centro/Norte y Quito),
46 señales de conversaciones, cinco movimientos de venta, cinco snapshots de stock
y una promoción.
No proviene de WhatsApp real ni contiene teléfonos, contactos o historias clínicas.

## Contrato

`Snapshot`, en [backoffice.py](../../src/mostrador/backoffice.py), valida:

| Colección | Campos principales |
| --- | --- |
| products | sku, title |
| branches | id, city |
| signals | id, conversation_id, sku, branch_id, occurred_at, message |
| movements | id, sku, branch_id, occurred_at, kind, units |
| stock | sku, branch_id, observed_at, available_units, reference_units, target_units |
| promotions | id, sku, branch_id, starts_at, ends_at, enabled |

`synthetic` debe ser true. `as_of` fija el corte, `coverage_start` declara el inicio de
cobertura completa y `window_days` vale siete en la fixture.
Fechas con zona horaria; cantidades enteras en unidades de venta; IDs únicos.
No mezclar paquetes, piezas o kilos bajo un mismo SKU.
Las relaciones deben existir y no se admiten eventos posteriores al corte.

La ventana reciente es [corte − 7 días, corte); la anterior, [corte − 14 días, corte − 7 días).
Ambas incluyen inicio y excluyen fin. Una conversación cuenta una vez por producto,
sucursal y ventana, aunque tenga varios mensajes.
SKU y sucursal se etiquetaron manualmente: la fixture no demuestra extracción con IA.

## Reglas de demo, no políticas comerciales reales

- Interés inusual: al menos cinco conversaciones distintas y al menos el doble que antes.
- Sin conversaciones anteriores no hay ratio fiable: proponer revisión de demanda,
  salvo que las ventas y el stock ya justifiquen priorizar reposición.
- Stock bajo: 25% o menos del objetivo, o cobertura de hasta tres días según ventas.
- Reposición sugerida: máximo de objetivo y ventas normalizadas a al menos siete días
  (o la ventana completa si es mayor), redondeadas hacia arriba, menos stock disponible.
  La evidencia expone ese horizonte y el objetivo calculado; no es un pronóstico.
- Porcentaje de stock: disponible / nivel de referencia × 100. El nivel de referencia
  y el objetivo de reposición son parámetros distintos y explícitos de la fixture.
- Inventario con más de una hora de antigüedad: actualizar datos antes de recomendar.
- Promoción vigente: habilitada y corte dentro de [inicio, fin).
- Promoción candidata: interés creciente y ninguna promoción vigente; sugerir siete días
  sujetos a revisión de términos, presupuesto y stock. Si falta stock, la activación queda
  condicionada al reabastecimiento y a revalidar condiciones.

Estos umbrales sirven para probar el flujo. No son un modelo estadístico, optimizador,
pronóstico de ventas ni reglas validadas por la empresa.

## Resultados comprobables

- SC-001 en Centro: 8 conversaciones frente a 2; 560 unidades vendidas; 180 disponibles,
  referencia 1.000 (18%) y objetivo 680. Cobertura 2,25 días; revisar reposición de 500.
  Promoción propuesta por siete días, condicionada a abastecimiento y revalidación.
- SC-002: 6 frente a 2; 14 vendidas; 80 disponibles. Evaluar promoción local.
- SC-003: 6 frente a 2; 14 vendidas; 80 disponibles. Ya hay promoción: no duplicarla.

Norte: SC-001 con 80 disponibles, objetivo/referencia 100 y 35 ventas; evaluar promoción.
Quito: SC-001 con 20 disponibles, objetivo/referencia 100 y 35 ventas; reponer 80.
Son escenarios separados, no se mezclan existencias entre sucursales.

La API relee el snapshot, pero nunca modifica sus existencias ni promociones.
Una aprobación no descuenta stock ni convierte estos registros en operaciones reales.
