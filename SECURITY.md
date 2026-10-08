# Seguridad y límites

La aplicación principal es una demo local de back office. Los tokens `demo-encargado`
y `demo-viewer`, además de `demo-jefe-zona` y `demo-encargado-quito`, son públicos y fijos; no exponer este modo a Internet.
La API antigua de reservas tiene también tokens públicos y no está montada en la nueva.

El servidor comprueba rol y sucursales autorizadas. Listados, resultados de análisis,
detalles, eventos y decisiones se limitan al alcance del token. Un ID ajeno devuelve 404.
La autenticación sigue siendo demo, no un login real. El body no permite asignarse un rol.
La aprobación queda registrada, pero no existe ejecutor externo.
Se comprueban vencimiento y coincidencia del snapshot antes de una aprobación nueva.

Los mensajes son datos, nunca instrucciones autorizadas. El analizador actual solo usa
campos estructurados; no entrega mensajes a un LLM. Las respuestas contienen agregados e IDs,
no textos crudos. No cargar conversaciones reales ni datos personales en esta demo.

`SALES_SNAPSHOT_PATH` es configuración confiable del servidor, no una ruta elegida por el
usuario HTTP. El JSON debe ser sintético y pasa validación de esquema y relaciones.
Un archivo con `synthetic=true` no prueba que sus datos realmente lo sean: revisarlos antes.

No conectar bases de producción ni copiar claves administrativas al frontend.
No versionar ni empaquetar `.context/`, archivos de entorno, bases locales, logs,
documentos de clientes ni material de productos privados.

Antes de un piloto: identidad real, aislamiento por organización/sucursal, límites de uso,
HTTPS, minimización de datos, autorización de fuentes, cobertura/frescura, gestión de secretos,
backups y monitoreo. Para acciones externas hacen falta revalidación, idempotencia durable
y reconciliación de resultados inciertos.

SQLite y el ciclo periódico están pensados para una instancia local. No se certifica
seguridad multiempresa, auditoría inmutable ni tolerancia a fallos de producción.
Reportar problemas por un canal privado al mantenedor, sin adjuntar secretos en issues.
