# Contribuir

Usar Python 3.11+, `uv sync --locked` y las comprobaciones indicadas en README.
Añadir primero una prueba para cada regla de negocio nueva. Mantener el dominio sin SDKs
externos; las decisiones del proveedor pertenecen a un adaptador.

No incorporar código, prompts, esquemas, conectores ni datos propietarios de otros
proyectos. Solo datos sintéticos con procedencia documentada. Nunca añadir `.context/`,
adjuntos, `.env`, tokens o bases locales al control de versiones.

Una contribución debe explicar qué cambia, cómo se verifica, qué permisos requiere y
qué garantía ofrece ante reintentos y fallos. Al aportar código, confirmar que se tienen
los derechos para distribuirlo bajo la licencia MIT del proyecto.

Evitar frameworks, servicios y abstracciones nuevos salvo que resuelvan una necesidad
demostrable del encargado comercial de primera línea. No añadir dependencias de proveedores al dominio ni
convertir el modelo de lenguaje en autoridad para precios, stock o aprobaciones.
