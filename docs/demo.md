# Demo: seis consultas → 500 unidades → evidencia → aprobación

Objetivo: mostrar cómo el encargado de Guayaquil Centro convierte señales comerciales
en una intención revisable. Fuentes ficticias con corte del 8 de octubre de 2026.
La aprobación se guarda localmente; no emite compras ni publica promociones.

## Preparar las dos pestañas

Desde la raíz del proyecto, ejecutar `uv sync --locked`. Usar una sesión nueva por
ensayo: las conversaciones y aprobaciones persisten, y el botón de seis consultas
solo añade ese lote una vez. No hace falta borrar bases anteriores.

Terminal 1, demo con Bedrock (perfil `sales-hackathon` configurado fuera del repositorio):

```sh
demo_session=$(mktemp -d /tmp/sales-bedrock.XXXXXX)
AWS_PROFILE=sales-hackathon AWS_REGION=us-east-1 \
SALES_AI_MODE=bedrock COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=0 \
COPILOT_DB_PATH="$demo_session/sales.sqlite" \
uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8010
```

Terminal 2, respaldo offline independiente:

```sh
demo_session=$(mktemp -d /tmp/sales-offline.XXXXXX)
SALES_AI_MODE=offline COPILOT_MODE=demo SALES_SCAN_INTERVAL_SECONDS=0 \
COPILOT_DB_PATH="$demo_session/sales.sqlite" \
uv run uvicorn mostrador.backoffice_api:create_app --factory --host 127.0.0.1 --port 8011
```

Abrir [Bedrock](http://127.0.0.1:8010) y [respaldo offline](http://127.0.0.1:8011).
En ambas pestañas elegir **Encargado · Centro** y pulsar **Analizar fuentes** antes
de presentar. Esperar a «Fuentes analizadas» y comprobar las dos propuestas de Centro.
El análisis inicial procesa 40 conversaciones; los siguientes reutilizan la caché.
Dejar «Simular 6 consultas» disponible en las dos pestañas.

La primera muestra **IA · Amazon Bedrock**. La segunda muestra
**Respaldo offline · Simulación local sin IA**. Preparar ambas no conecta sistemas reales
ni necesita servicios adicionales: son dos procesos locales de la misma aplicación.

## Guion de tres minutos

1. **Situación inicial.** Seleccionar Vitamina C 500 mg · 30 tabletas, Centro.
   Hay dos consultas recientes frente a dos anteriores y 180 unidades disponibles.
2. **Seis consultas nuevas.** Pulsar **Simular 6 consultas** una sola vez. La bandeja
   avisa de fuentes nuevas y bloquea la aprobación de las propuestas anteriores.
   Pulsar **Analizar fuentes** y esperar a que termine.
3. **500 unidades propuestas.** Seleccionar la nueva propuesta de Vitamina C de Centro.
   Mostrar ocho consultas recientes frente a dos anteriores y el cálculo explícito:
   **objetivo 680 − disponibles 180 = 500 unidades**, con horizonte de siete días.
   Las seis consultas son una señal de interés; no equivalen a 500 ventas.
   La reposición ya era de 500 antes del lote, porque depende del inventario y las
   operaciones. El nuevo interés añade la promoción propuesta, condicionada al stock.
4. **Evidencia.** Abrir una conversación, un documento y los registros operativos desde
   sus enlaces. Volver a **Bandeja**. Hay diez conversaciones citadas (ocho recientes
   y dos anteriores), el procedimiento `PROC-REPLENISH` y `DOC-CAMPAIGN-GYE`.
   Señalar la promoción de siete días: primero reponer y revalidar stock; siguen
   pendientes proveedor/plazo, descuento, presupuesto y elegibilidad.
5. **Aprobación.** Pulsar **Aprobar intención**, revisar la confirmación y confirmar.
   La propuesta aparece en **Historial** como «Intención aprobada». Abrir
   **Historial de esta propuesta**: creación y aprobación, con actor y fecha.
   Recargar y comprobar que sigue aprobada. No se ejecutó ninguna acción comercial.

## Si Bedrock falla durante la presentación

- **Timeout:** la API devuelve `503 bedrock_timeout` y la pantalla explica que no se
  completó el análisis. No se reintenta automáticamente ni se habilita la aprobación.
- **Respuesta inválida:** se permite un solo reintento por lote, también si el JSON
  referencia documentos o productos incorrectos. Cada intento pasa por la misma
  validación. Si vuelve a fallar, devuelve `502 model_invalid_response` sin publicar
  propuestas nuevas. Las llamadas del reintento cuentan en el total del análisis.
- **Sesión AWS vencida/disponibilidad:** el error se muestra sin detalles privados y
  sin reintentos automáticos. No dedicar el tiempo de presentación a renovar AWS.

Pasar a la pestaña **8011** y decir: «Continuamos con el respaldo offline: usa las mismas
fuentes sintéticas y cálculos, con interpretación local simulada, sin IA».
Ejecutar allí los pasos pendientes. Las dos sesiones son independientes: las consultas
y decisiones hechas en Bedrock no se copian a offline. Nunca hay cambio silencioso.

Si el navegador agota su propia espera, pulsar **Actualizar** para consultar el
resultado antes de repetir una operación. Para repetir el ensayo completo, detener
el servidor correspondiente y relanzar su bloque de arranque: `mktemp` crea otra sesión.

## Comprobación repetible

```sh
uv run pytest -q tests/test_bedrock.py tests/test_sales_workspace.py tests/test_sales_routes.py
node --test tests/ui/app.test.cjs
```

Estas pruebas cubren errores y el recorrido con fuentes sintéticas. El ensayo con
Bedrock real debe hacerse antes de presentar, porque la disponibilidad y las
credenciales de AWS pueden cambiar.
