# Arquitectura del sales back office

```text
Snapshot sintético de las tres fuentes
              ↓ validación y corte común
Analizador determinista — inicio / petición / intervalo
              ↓ propuestas con evidencia
Bandeja SQLite + eventos
              ↓ revisión del encargado
       approved / rejected
              ↓
Ejecución externa pendiente de implementar
```

## Responsabilidades

- `backoffice.py`: esquema de entrada, relaciones y reglas de análisis.
- `backoffice_store.py`: persistencia, deduplicación, vencimiento de aprobación y decisiones.
- `backoffice_api.py`: autenticación demo, HTTP y ciclo periódico opcional.
- `data/backoffice_demo.json` dentro del paquete: fixture de arranque sin secretos.
- `tests/test_backoffice.py`: resultados, límites, permisos y persistencia.

Se reutiliza el error genérico `DomainError` de la base MIT.
`Reviewer` representa identidad, rol y sucursales autorizadas por el servidor.
La API de reservas anterior queda separada y no se monta en el servicio principal.

## Datos y evidencia

El corte y las dos ventanas vienen del snapshot validado. El conteo usa conversaciones
distintas por SKU/sucursal/ventana, no cantidad de mensajes. La cobertura de stock usa
ventas observadas: disponible / (unidades vendidas / días), o valor desconocido sin ventas.
Es una estimación descriptiva, no un pronóstico ni una garantía de disponibilidad.

SKU y sucursal llegan ya resueltos. El mensaje de ejemplo no se ejecuta ni se interpreta
como instrucciones. Las recomendaciones contienen IDs de evidencia y agregados, no textos
de conversaciones. El contrato demo exige cobertura declarada de dos ventanas completas;
no puede comprobar que un proveedor realmente entregó todos los registros.

## Decisiones durables

Cada ID depende del snapshot completo, producto, sucursal y tipo. Mismo snapshot:
misma propuesta. Snapshot diferente: nueva evidencia y una aprobación independiente.
Un análisis nuevo marca propuestas pendientes anteriores como `superseded`; preserva
decisiones ya tomadas como historial.

La aprobación vence 900 segundos después de crear la propuesta. El rechazo sigue disponible
mientras esté pendiente. Repetir la misma decisión devuelve el resultado previo.
Una decisión contradictoria devuelve conflicto. SQLite serializa las escrituras y registra
cambio de estado y evento en la misma transacción.

Estados actuales: `pending`, `approved`, `rejected`, `superseded`.
`expires_at` indica hasta cuándo se puede aprobar; la demo no añade un estado de expiración.
Las propuestas aprobadas siguen mostrando `execution_status=not_configured`.
No existe endpoint de ejecución.

## Ciclo de análisis

Arranque y `POST /analysis/run` ejecutan un análisis. `SALES_SCAN_INTERVAL_SECONDS`
habilita el ciclo local (mínimo diez segundos; cero lo desactiva).
El reloj del análisis es el corte del archivo; el del vencimiento es el reloj del servidor.
Un snapshot inválido produce error de fuente y bloquea nuevas aprobaciones.
Los análisis se serializan desde la lectura hasta la persistencia para que una petición
manual y el ciclo periódico no invaliden mutuamente sus propuestas.

El ciclo vive dentro del proceso de la API. La deduplicación es durable, pero no hay
coordinación de un único scheduler entre réplicas, ingestión continua ni garantías de
entrega de tareas. Usar una sola instancia local para la demo.

## Límites

Tokens públicos de demo con permisos por sucursal/zona, una organización, sin CORS abierto,
sin LLM, sin WhatsApp,
sin ERP/POS, sin campañas externas ni compras. El snapshot por archivo es configuración
confiable del servidor, no una subida pública. Una integración real requiere contratos
por fuente, autenticación, límites, revalidación y reconciliación explícitos.
