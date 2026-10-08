# Synthetic data implementation plan

Plan histórico de fixtures de reservas. El alcance vigente es [Sales Back Office](../../design.md).

**Goal:** Datos originales, reproducibles y relacionados para los cinco casos aprobados:
catálogo, precio/stock, reservas, cliente/historial y promociones.

**Architecture:** Un snapshot JSON portable con generador y validador Python estándar.
Se distribuye en `data/synthetic/`. No se cambian API, contratos ni la base SQLite actual.
Clientes/promociones son fixtures para integrar después, no funciones del agente ya activas.

**Spec:** Los cinco casos enumerados por el usuario; snapshot fijo `2026-10-08T14:00:00Z`,
30 SKU de cuidado personal/insumos no farmacológicos, tres sucursales, tres listas de
precios, 12 clientes ficticios, compras relacionadas, ocho promociones y estados de reserva.
IDs `DEMO-*`, centavos USD, cantidades enteras, fechas UTC, descuentos enteros redondeados
half-up y ninguna persona, marca, dato comercial o recomendación clínica real.

## Task 1 — Dataset y coherencia

- [x] Crear `tests/test_synthetic.py` con contrato de cantidades, reproducción exacta,
  relaciones, inventario, totales, vigencias y detección de datos dañados.
- [x] Ejecutar `uv run pytest tests/test_synthetic.py -q` antes de implementar.
- [x] Crear `src/mostrador/synthetic.py`: `build_dataset() -> dict`,
  `render_dataset(data) -> str` y CLI de exportación/validación sin cuentas externas.
- [x] Crear `src/mostrador/synthetic_checks.py`: `validate_dataset(data) -> None`;
  errores explícitos por IDs duplicados, referencias inválidas, stock negativo,
  descuentos incoherentes o estados sin sus eventos/condiciones.
- [x] Exportar `data/synthetic/dataset.json`; comprobar que coincide con el generador.

## Task 2 — Escenarios y entrega

- [x] Incluir escenarios con entradas y resultados literales: SKU ambiguo, distintas
  presentaciones, stock agotado/antiguo, cliente nuevo, membresía vencida, promociones
  válidas/futuras/vencidas/incompatibles y propuesta incierta sin reintento.
- [x] Comprobar resultados comerciales de los escenarios con cálculos independientes
  en tests; no inventar tasas de precisión de un agente que no se ha ejecutado.
- [x] Documentar diccionario, joins, reglas comerciales y uso en `data/synthetic/README.md`.
- [x] Actualizar README, CONEXT y packaging para incluir el dataset sin incluir `.context`.
- [x] Ejecutar suite completa, lint, formato, CLI de validación, build y revisar artefactos.

No push, despliegue AWS ni cambios en la visibilidad remota en esta solicitud.

**Resultado:** 90 pruebas pasan (40 previas + 50 nuevas), lint/formato y build correctos.
31 escenarios comprobados contra el snapshot con un oráculo de pruebas independiente.
Se conserva la advertencia upstream de Starlette/httpx ya existente. No se evaluó ningún LLM.
