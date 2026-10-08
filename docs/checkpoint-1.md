# Checkpoint #1 — Sales Coworker

## Problema

Según la presentación del reto, Farmaenlace procesa 172 mil transacciones diarias,
maneja 17.000 productos en 1.422 puntos de venta y dispone de diez años de historial
comercial. El desafío es convertir esa información en una decisión útil a tiempo
para quien opera una sucursal o zona.

El encargado no puede cruzar manualmente consultas de clientes, movimientos de
inventario y promociones durante toda su jornada. Nuestra hipótesis es que una alerta
con evidencia puede ayudarle a anticipar faltantes y oportunidades comerciales.

## Usuario

El encargado comercial o jefe de área/zona de Farmaenlace: la primera línea que decide
abastecimiento y promociones en su ámbito. La interfaz y los permisos se organizan
por sus sucursales, sin asumir acceso a toda la compañía.

## Solución

Un analista operativo que revisa tres fuentes sintéticas en segundo plano:
consultas de clientes por canales como WhatsApp, movimientos de inventario por sucursal,
y catálogo con stock y promociones. Detecta situaciones, explica la evidencia y propone
una acción. El encargado revisa y aprueba antes de cualquier ejecución.

Ejemplo verificable en la demo:

> Las consultas sobre Vitamina C en Guayaquil Centro pasaron de 2 a 8 conversaciones.
> Quedan 180 unidades, un 18% del nivel de referencia. Proponemos reabastecer 500
> unidades y evaluar una promoción local de siete días, condicionada a recuperar
> disponibilidad y aprobar sus términos.

Los números salen de datos ficticios y reglas visibles: objetivo de reposición 680
menos 180 disponibles. No son recomendaciones reales de compra ni consejo clínico.

## Los tres ejes

- **Mejora operativa:** reducir el tiempo para cruzar fuentes y priorizar una decisión.
- **Servicio al cliente:** ayudar a anticipar faltantes y reducir consultas sin disponibilidad.
- **Fidelización:** orientar propuestas de promociones locales según señales observadas;
  una futura integración podría apoyar SmartClub.

Estos son beneficios por validar. Mediremos tiempo de análisis/revisión, propuestas
aceptadas y faltantes; no prometemos disponibilidad permanente ni aumento probado de ventas.

## Encaje técnico

La propuesta se sitúa sobre SAP, Big Data, Airflow y los modelos existentes.
Recibe datos autorizados y entrega recomendaciones; las operaciones siguen perteneciendo
a sus sistemas responsables. No exige reemplazarlos.

Hoy funcionan el análisis determinista periódico, la evidencia y la aprobación persistente.
Son sintéticos todos los datos. Faltan la interfaz final, extracción de señales con LLM,
conectores empresariales y ejecución externa. Aprobar en la demo registra la decisión;
no hace una compra ni publica una campaña. Declarar el trabajo previo y las herramientas.

## Frase de una línea

«Convertimos la avalancha de datos operativos de Farmaenlace en decisiones concretas
para el encargado de primera línea, antes de perder el stock y la venta».
