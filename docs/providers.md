# Contratos para futuras integraciones

La demo acepta solamente snapshots sintéticos. Ningún conector real está incluido.
Los siguientes son requisitos de integración, no capacidades que se activen con una API key.

## Encaje con sistemas existentes

SAP/ERP, el repositorio analítico y los pipelines de Airflow siguen siendo sistemas
responsables de los datos. Adaptar sus salidas autorizadas al contrato; no copiarlos ni
sustituirlos. Una futura acción aprobada vuelve al ERP o gestor de campañas por su API.
La demo no certifica acceso, compatibilidad ni conexión a esas plataformas.

## Conversaciones

El adaptador autorizado debe producir señal con ID, ID pseudónimo de conversación,
fecha, SKU y sucursal. La demo usa mensajes ficticios ya etiquetados.
La extracción futura debe poder abstenerse si el producto o localidad es ambiguo.
No inferir una sucursal a partir de un teléfono ni convertir preguntas clínicas en recomendaciones.

Los mensajes son datos no confiables. No pueden elegir herramientas, permisos, destinos
de exportación ni instrucciones del agente. Minimizar contenido personal y mantener
los mensajes originales fuera de logs, respuestas públicas y datasets de evaluación compartidos.

## Inventario y movimientos

SKU, sucursal, unidad comercial y tiempo deben coincidir entre fuentes.
Separar disponible actual de movimientos históricos; no restar ventas nuevamente.
Usar IDs estables para evitar duplicar movimientos al reimportar.
La demo suma ventas; recepciones y ajustes no se cuentan como ventas.
Plazos de suministro, pedidos en tránsito y transferencias requieren nuevos campos antes
de optimizar cantidades o prometer cobertura.

## Catálogo y promociones

SKU exacto y sucursal obligatorios. Cada promoción declara vigencia e habilitación.
La ausencia de una promoción solo es concluyente si la extracción es completa y reciente.
El snapshot demo asume cobertura completa declarada; un conector real debe aportar
watermarks, completitud y errores por fuente y provocar abstención ante fuentes incompletas.
Para publicar hacen falta presupuesto, descuento, vigencia, elegibilidad y permisos,
además de verificar stock de nuevo.

## Ejecución después de aprobar

Antes de añadirla, definir payload inmutable, condiciones y vencimiento.
Revalidar permiso del encargado y evidencia, reclamar la ejecución atómicamente y usar
una clave idempotente durable en el proveedor. Si se pierde la respuesta, registrar
resultado incierto y reconciliar sin repetir a ciegas.

Una API de proveedor debe devolver resultados comerciales mínimos, sin código interno,
prompts, SQL, credenciales ni respuestas crudas de sus sistemas.
Los clientes del frontend nunca deben recibir una clave administrativa de base de datos.

## Pruebas exigidas

Completitud y frescura por fuente; aislamiento; SKU ambiguo; ventanas equivalentes;
duplicados; dinero/unidades; doble aprobación; evidencia cambiada; permisos revocados;
timeout antes/después de ejecución y reconciliación.
Usar entornos y datos autorizados. No ejecutar pruebas contra producción por defecto.
