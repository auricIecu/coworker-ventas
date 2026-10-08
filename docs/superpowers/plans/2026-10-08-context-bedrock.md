# Contexto, Bedrock y bandeja — plan de implementación

## Objetivo y decisiones

Ejecutar el alcance aprobado por el usuario de fuentes → IA → evidencia → decisión.
Continuar en el worktree existente dev/eric. Sin commits/push automáticos adicionales.
Una instancia local, datos sintéticos, sin conectores ni acciones empresariales reales.
No hay canal autorizado al mentor: dejar pregunta lista en la documentación.

## Arquitectura

Fuentes JSON empaquetadas: operaciones, conversaciones completas y documentos.
SQLite mantiene conversaciones añadidas, cache de interpretación y bandeja de decisiones.
Bedrock Converse con boto3, perfil del entorno, region us-east-1 y modelo configurable.
Un limitador por proceso serializa llamadas a >=1 segundo, sin reintentos SDK ocultos.
Modo offline explícito para pruebas/demos sin AWS; nunca fallback silencioso.
Validar IDs y citas, abstenerse ante producto/sucursal ambiguos. Recuperar documentos
por SKU, sucursal y vigencia, y pedir al modelo selección de referencias pertinentes.
Las condiciones tipadas del documento se aplican en código aunque el modelo omita citarlas.
Cantidades deterministas, aprobación de intención separada de ejecución.

## Contrato de bandeja (API /workspace)

Bearer demo-encargado, demo-jefe-zona, demo-encargado-quito o demo-viewer, mismos alcances actuales.
GET /workspace devuelve:
{mode:'bedrock'|'offline', model_id:string|null, synthetic:true, as_of:string,
 source_revision:string, analyzed_revision:string|null, analysis_status:string,
 actor:{id,role,branches}, branches:[{id,city}], products:[{sku,title}],
 recommendations:[propuesta], conversations:[{id,branch_id,channel,occurred_at,messages:[{role,text}]}],
 documents:[{id,title,kind,branch_ids,skus,valid_from,valid_until,body,conditions}],
 movements:[registro], stock:[registro], interpretations:[{conversation_id,status,sku,branch_id,reason,document_ids}],
 last_run:{mode,model_id,cache_hits,model_calls,at}|null, burst_added:boolean}.

Propuesta conserva id, sku, product, branch_id, city, kind, priority, reason,
suggested_units, promotion_plan, evidence, status, expires_at y execution_status.
Añade grounding:{conversations:[{id,excerpt}],documents:[{id,title,excerpt}],
missing_information:[string], required_approvals:[string], explanation:string,
calculation:string, blockers:[string]}, analysis_mode, approvable:boolean.

POST /workspace/analyze sin body: devuelve GET /workspace actualizado. Puede tardar;
deshabilitar controles mientras espera. Error {error:codigo}; no fingir éxito.
POST /workspace/demo/burst sin body: añade seis conversaciones sintéticas una sola vez,
NO analiza automáticamente; devuelve GET /workspace. CTA después: Analizar fuentes.
POST /workspace/conversations body {synthetic:true,id,branch_id,channel,occurred_at,messages}:
añade conversación sintética validada del ámbito del actor. El remitente debe asegurar
que no contiene datos reales: la declaración synthetic no es un filtro de información personal.
POST /workspace/recommendations/{id}/decision {decision:'approve'|'reject'}: devuelve propuesta.
GET /workspace/recommendations/{id}/events devuelve [{kind,actor_id,timestamp}].
El servidor bloquea aprobación si cambia source_revision, caduca o faltan condiciones obligatorias.

## Tareas y comprobación

- [x] Fuentes y contratos. Crear sales_context.py, data/sales/{operations,conversations,documents,burst}.json.
  Pruebas: referencias válidas, ciudades distintas, ventas/recepciones/ajustes, ambigüedad,
  documentos vencidos y condiciones de promoción. No copiar materiales privados.
- [x] Intérprete Bedrock en bedrock.py. Pruebas de salida inválida, IDs inventados,
  abstención, límite de llamadas y fallos AWS seguros. Probar una invocación real acotada.
- [x] Motor y API en sales_workspace.py / sales_routes.py. Pruebas de incorporación,
  cache, citas exactas, bloqueo por documentos, permisos, evidencia modificada y decisiones.
  Mantener la API histórica compatible y separar su SQLite de la nueva bandeja.
- [x] UI en static/{index.html,app.js,styles.css}. Montarla desde backoffice_api.
  Lista/detalle con evidencia, fuentes inspeccionables, perfiles, pendientes/historial,
  simulación de consultas, análisis, aprobación/rechazo y estados de error/carga.
  Sin frameworks nuevos ni dependencias externas/CDN. Evitar HTML no confiable.
- [x] Integración, documentación y revisión. Suite completa, lint, build, smoke HTTP,
  navegador escritorio/móvil, screenshots en .context, demo real Bedrock, escaneo de secretos.

## Diseño visual

Registro producto, blanco puro y grises neutros, tinta ciruela oscura y acento frambuesa
restringido a acción/selección, siguiendo semilla 343°. Sistema sans y monospace para IDs.
Lista de decisiones + panel de evidencia. La firma es la cadena visible consulta → stock
→ condiciones. No hero ni tarjetas métricas decorativas. Contraste AA y foco visible.

## Límites

No afirmar calidad estadística o beneficios comerciales demostrados. Las credenciales
temporales permanecen fuera del proyecto. Un modelo que responde no implica agente evaluado.
Las fuentes sintéticas tienen corte fijo: el ciclo no representa ingestión empresarial en vivo.

## Verificación realizada

- 132 pruebas Python y 4 pruebas Node; lint, formato y build verificados.
- Nova Lite real vía Bedrock: interpretación de los 40 registros, seis consultas nuevas,
  reutilización de 40 interpretaciones y una llamada adicional para el nuevo lote.
- Resultado observado: 8 consultas recientes frente a 2 previas, 500 unidades, promoción
  de 7 días condicionada y citas PROC-REPLENISH/DOC-CAMPAIGN-GYE. Aprobación sin ejecución.
- Navegador Chrome: análisis, incorporación, bloqueo por cambios, reanálisis, aprobar,
  rechazar, historial, enlaces a registros, aislamiento por perfil y móvil de 390 px.
- Revisión independiente: corregida renovación de pendientes vencidas, con evento de auditoría.
- Capturas y bases de comprobación quedan en `.context/`, no distribuidas.
- No se contactó al mentor; la pregunta está preparada en README para envío humano.
