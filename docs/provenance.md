# Procedencia y distribución

Sales Coworker parte de la base Mostrador Copilot distribuida bajo MIT.
Se conserva su archivo `LICENSE`, incluido el aviso de copyright.
El módulo de back office, su fixture y sus pruebas se escribieron en este proyecto
a partir de los requisitos del encargado operativo, sin copiar archivos de productos privados.

La arquitectura usa patrones generales: separación de análisis y operaciones, evidencia
trazable, permisos del servidor, aprobación humana e idempotencia.
No se distribuyen implementaciones, prompts, reglas particulares, conectores ni datos
privados de otros productos. No se importó su historial Git.

## Alcance de los datos

Los productos, conversaciones, movimientos y promociones de la demo son ficticios.
Farmaenlace es el contexto del caso de uso; no se afirma afiliación, integración oficial
ni validación de resultados. No se usan logos de la empresa.

Los adjuntos del evento son referencia local dentro de `.context/` y no se distribuyen.
Los secretos, bases locales, logs y material de análisis también quedan fuera de paquetes.

## Licencias y publicación

MIT se aplica al material que este proyecto puede distribuir bajo esa licencia.
Los componentes de terceros mantienen sus propios términos. Una futura integración
no incorpora automáticamente el código o los derechos del proveedor.
No eliminar avisos de copyright para cambiar la identidad del producto.

Antes de publicar, revisar el contenido y el historial, declarar trabajo previo al evento
y comprobar que no se añadieron adjuntos, secretos ni datos empresariales.
El repositorio remoto y su visibilidad no se modifican al ejecutar la demo.
