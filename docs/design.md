# Sales back office: alcance y decisiones

## Objetivo aprobado

Ayudar al encargado comercial de primera línea a decidir abastecimiento y promociones a partir de señales
de conversaciones, movimientos de inventario y catálogo/promociones/stock.
Observar y analizar automáticamente; exigir decisión humana para cualquier ejecución.

## Base implementada

Se añade una capa sobre los sistemas existentes (SAP, Big Data, Airflow); sus conectores
quedan pendientes y ningún acceso está supuesto.

Un servicio FastAPI, un snapshot JSON sintético y una bandeja SQLite son suficientes para
demostrar el flujo. El análisis determinista hace reproducibles las cifras; un futuro LLM
podrá extraer intenciones y redactar explicaciones, sin calcular stock ni autorizar acciones.

Cada propuesta identifica producto, sucursal, corte de datos, tipo, evidencia y prioridad.
La cantidad de reposición es una heurística explícita; una propuesta de promoción no incluye
un descuento inventado. Puede sugerir siete días de campaña, condicionados
a disponibilidad verificada; con stock bajo exige antes reabastecimiento. La aprobación registra intención y queda pendiente de un ejecutor real.

## Criterios verificables

- Tres fuentes relacionadas por SKU y sucursal; sin mensajes ni datos de personas reales.
- Comparar dos ventanas de igual duración, contando conversaciones distintas.
- Las ventas salen de movimientos; el stock sale del snapshot actual. No descontar dos veces.
- Un inventario de más de una hora impide recomendar abastecimiento o promoción.
- Una promoción solo está vigente si está habilitada y el corte pertenece a su intervalo.
- Sin base comparable, pedir revisión; no afirmar crecimiento infinito.
- Falta de stock tiene prioridad sobre aumentar demanda mediante promoción.
- Cada propuesta incluye evidencia verificable, no una cifra de confianza inventada.
- Solo el encargado/jefe autorizado para la sucursal decide; repetir decisión no duplica eventos; evidencia cambiada exige nueva revisión.
- No hay ejecución externa, publicación, correos ni conexión empresarial por defecto.

## Producto pendiente

Interfaz operativa, extracción de señales con IA, conectores autorizados, autenticación real,
manejo de cobertura parcial por fuente y ejecutor con reconciliación.
La demo local no certifica seguridad multiempresa, calidad de un LLM ni viabilidad comercial.
