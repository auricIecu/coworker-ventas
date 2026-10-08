/* The only credentials here are public demo profiles. No token is persisted. */
(function () {
  "use strict";

  const LABELS = {
    replenish: "Revisar abastecimiento", review_promotion: "Evaluar promoción local",
    refresh_data: "Actualizar inventario", review_demand: "Revisar interés",
    pending: "Pendiente", approved: "Intención aprobada", rejected: "Rechazada",
    superseded: "Sustituida por otro análisis", expired: "Vencida", proposed: "Propuesta creada", revalidated: "Propuesta revalidada",
    high: "Prioridad alta", medium: "Prioridad media", low: "Prioridad baja",
    sale: "Venta", receipt: "Recepción", adjustment: "Ajuste", customer: "Cliente", staff: "Asesor",
    user: "Cliente", assistant: "Asesor", agent: "Asesor", operator: "Asesor",
    matched: "Producto identificado", resolved: "Producto identificado", ambiguous: "Requiere aclaración",
    abstained: "Sin atribución", unclassified: "Sin clasificar", ignored: "Sin señal comercial", irrelevant: "Sin señal comercial",
    not_configured: "Sin ejecución externa", blocked: "Bloqueada", policy: "Política",
    promotion: "Promoción", procedure: "Procedimiento", inventory: "Inventario", supplier: "Proveedor", whatsapp: "WhatsApp",
    web: "Web", store: "Tienda", phone: "Teléfono", email: "Correo",
    valid_from: "Vigente desde", valid_until: "Vigente hasta", branch_ids: "Sucursales",
    skus: "Productos", minimum_stock: "Stock mínimo", min_stock: "Stock mínimo",
    minimum_margin: "Margen mínimo", min_margin: "Margen mínimo", max_discount: "Descuento máximo",
    requires_approval: "Requiere aprobación", required_approvals: "Aprobaciones requeridas",
    discount_and_budget: "Descuento y presupuesto", requires_review: "Pendiente de revisión",
    stock_replenished_and_revalidated: "Reponer y volver a validar inventario",
    stock_and_terms_revalidated: "Validar inventario y condiciones", duration_days: "Duración (días)",
    activation_condition: "Condición de activación", manager: "Jefe de zona", commercial: "Área comercial",
    requires_stock: "Requiere inventario", max_duration_days: "Duración máxima (días)", encargado: "Encargado de sucursal",
  };
  const ERRORS = {
    invalid_credentials: "El perfil no está disponible. Selecciona otro perfil y actualiza la bandeja.",
    permission_denied: "Este perfil no tiene permiso para realizar esta acción.",
    evidence_changed: "Las fuentes cambiaron. Analiza de nuevo antes de aprobar.",
    source_changed: "Las fuentes cambiaron. Analiza de nuevo antes de aprobar.",
    recommendation_expired: "La propuesta venció. Analiza las fuentes para revisar su vigencia.",
    decision_conflict: "La propuesta ya tiene otra decisión. Actualiza la bandeja para revisarla.",
    recommendation_not_found: "La propuesta ya no está disponible para este perfil. Actualiza la bandeja.",
    analysis_failed: "No se pudo completar el análisis. Revisa la conexión y vuelve a analizar.",
    source_unavailable: "No se pudieron leer las fuentes. Actualiza la bandeja para reintentar.",
    bedrock_unavailable: "Bedrock no está disponible. Revisa su configuración y vuelve a analizar.",
    bedrock_timeout: "Bedrock tardó demasiado. No se completó el análisis. Puedes volver a analizar o usar la demo de respaldo offline.",
    bedrock_invalid_response: "Bedrock devolvió un análisis no válido. No se incorporó a la bandeja.",
    missing_required_approvals: "Faltan aprobaciones requeridas. La intención no se registró.",
    recommendation_blocked: "La propuesta tiene condiciones pendientes. Revisa los bloqueos antes de aprobar.",
    request_timeout: "La solicitud tardó demasiado. Actualiza la bandeja para comprobar el resultado antes de reintentar.",
    network_error: "No se pudo conectar con la demo. Comprueba que el servidor esté disponible y pulsa Actualizar.",
    aws_session_expired: "La sesión de AWS venció. Renueva la sesión en el servidor antes de volver a analizar.",
    model_invalid_response: "Bedrock devolvió una respuesta inválida también en el único reintento. No se incorporó a la bandeja. Puedes usar la demo de respaldo offline.",
    analysis_required: "Se necesita un análisis válido antes de aprobar. Pulsa Analizar fuentes.",
    analysis_in_progress: "Ya hay un análisis en curso. Espera y actualiza la bandeja para comprobar el resultado.",
    missing_required_context: "Falta contexto obligatorio. Revisa las condiciones que bloquean la aprobación.",
  };
  const label = value => LABELS[value] || String(value ?? "No informado").replaceAll("_", " ");
  const epoch = value => typeof value === "number" ? value * 1000 : Date.parse(value);
  const date = value => {
    const milliseconds = epoch(value);
    return Number.isFinite(milliseconds) ? new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" }).format(milliseconds) : "Fecha no informada";
  };
  const number = value => typeof value === "number" ? new Intl.NumberFormat("es", { maximumFractionDigits: 2 }).format(value) : "—";
  function approvalBlockers(workspace, recommendation, now = Date.now()) {
    if (!workspace || !recommendation) return ["Selecciona una propuesta."];
    const blockers = [];
    if (workspace.actor?.role !== "operator") blockers.push("Este perfil solo permite consultar.");
    if (recommendation.status !== "pending") blockers.push("Esta propuesta ya no está pendiente.");
    if (!workspace.analyzed_revision || workspace.source_revision !== workspace.analyzed_revision) blockers.push("Las fuentes cambiaron o aún no se analizaron. Analiza antes de aprobar.");
    if (workspace.analysis_status !== "ready") blockers.push("El análisis no está listo. Analiza las fuentes antes de aprobar.");
    if (!Number.isFinite(epoch(recommendation.expires_at)) || epoch(recommendation.expires_at) <= now) blockers.push("La propuesta venció o no tiene una vigencia válida. Vuelve a analizar las fuentes.");
    if (recommendation.approvable !== true) blockers.push("Hay condiciones pendientes; la aprobación no está habilitada.");
    blockers.push(...(recommendation.grounding?.blockers || []));
    return [...new Set(blockers)];
  }
  function sourceMatches(row, query) {
    return !query || JSON.stringify(row).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es").includes(query.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es"));
  }
  // The small pure boundary is shared with node:test; the browser uses the same rules.
  if (typeof module !== "undefined" && module.exports) module.exports = { approvalBlockers, sourceMatches, epoch, label };
  if (typeof document === "undefined") return;

  const $ = id => document.getElementById(id);
  const state = { workspace: null, profile: "demo-jefe-zona", view: "inbox", filter: "pending", source: "conversations", selected: null, busy: false, loadId: 0, events: new Map(), confirmation: null, sourceFocus: null };
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  }
  function button(text, className, onClick) {
    const element = node("button", text, className);
    element.type = "button";
    element.addEventListener("click", onClick);
    return element;
  }
  function announce(message, success = false) {
    $("notice").textContent = message;
    $("notice").className = success ? "notice success" : "notice";
    $("notice").hidden = !message;
  }
  function showError(error) {
    $("error").textContent = ERRORS[error.code] || `No se pudo completar la acción (${error.code || "error inesperado"}). Actualiza la bandeja antes de reintentar.`;
    $("error").hidden = false;
  }
  function clearError() { $("error").hidden = true; }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), path.endsWith("/analyze") ? 300000 : 30000);
    try {
      const response = await fetch(path, {
        ...options,
        headers: { Authorization: `Bearer ${state.profile}`, ...(options.body ? { "Content-Type": "application/json" } : {}) },
        signal: controller.signal,
      });
      let data;
      try { data = await response.json(); } catch { throw { code: "invalid_response" }; }
      if (!response.ok) throw { code: data.error || `http_${response.status}` };
      return data;
    } catch (error) {
      if (error.code) throw error;
      throw { code: error.name === "AbortError" ? "request_timeout" : "network_error" };
    } finally { clearTimeout(timer); }
  }
  function setBusy(busy, action) {
    state.busy = busy;
    $("main").setAttribute("aria-busy", String(busy));
    $("profile").disabled = busy;
    $("refresh").disabled = busy;
    $("analyze").disabled = busy || !state.workspace || state.workspace.actor?.role !== "operator";
    $("burst").disabled = busy || !state.workspace || state.workspace.burst_added || state.workspace.actor?.role !== "operator";
    $("analyze").textContent = busy && action === "analyze" ? "Analizando fuentes…" : "Analizar fuentes";
    $("burst").textContent = state.workspace?.burst_added ? "Consultas simuladas" : "Simular 6 consultas";
    $("confirm-decision").disabled = busy;
    document.querySelectorAll("[data-decision]").forEach(element => { element.disabled = busy || element.dataset.blocked === "true"; });
    document.querySelectorAll("[data-run-analysis]").forEach(element => { element.disabled = busy || state.workspace?.actor?.role !== "operator"; });
  }
  function getSelected() { return state.workspace?.recommendations.find(item => item.id === state.selected); }
  function filteredRecommendations() { return (state.workspace?.recommendations || []).filter(item => state.filter === "pending" ? item.status === "pending" : item.status !== "pending"); }
  function branchName(id) {
    const branch = state.workspace?.branches.find(item => item.id === id);
    return branch ? `${branch.city} · ${id.replaceAll("-demo", "")}` : id;
  }
  function productName(sku) { return state.workspace?.products.find(item => item.sku === sku)?.title || sku; }
  function applyWorkspace(workspace) {
    state.workspace = workspace;
    state.events.clear();
    if (!filteredRecommendations().some(item => item.id === state.selected)) state.selected = filteredRecommendations()[0]?.id || null;
    render();
  }
  async function loadWorkspace(action = "refresh") {
    if (state.busy) return;
    const loadId = ++state.loadId;
    clearError();
    setBusy(true, action);
    if (action === "analyze") announce("Analizando conversaciones y contrastando operaciones y documentos. El proceso puede tardar unos minutos.");
    try {
      const path = action === "analyze" ? "/workspace/analyze" : action === "burst" ? "/workspace/demo/burst" : "/workspace";
      const workspace = await request(path, action === "refresh" ? {} : { method: "POST" });
      if (loadId !== state.loadId) return;
      applyWorkspace(workspace);
      if (action === "analyze") announce("Análisis terminado. Revisa la evidencia y las condiciones de cada propuesta.", true);
      else if (action === "burst") announce("Se añadieron 6 conversaciones sintéticas. Analiza las fuentes para actualizar las propuestas; las anteriores no se pueden aprobar.");
      else if (workspace.analyzed_revision && workspace.source_revision !== workspace.analyzed_revision) announce("Hay fuentes nuevas sin analizar. Las propuestas anteriores no se pueden aprobar.");
      else announce("");
    } catch (error) {
      if (action === "analyze" && state.workspace) {
        state.workspace.analysis_status = "analysis_failed";
        render();
      }
      showError(error);
      announce("");
      if (!state.workspace) {
        $("recommendation-list").replaceChildren(node("p", "Sin conexión con la bandeja.", "queue-empty"));
        $("recommendation-detail").replaceChildren(empty("No se pudo cargar la mesa", "Comprueba el servidor y pulsa Actualizar para volver a intentarlo."));
        $("engine").textContent = "Sin conexión";
        $("analysis-state").textContent = "No se pudo consultar el estado";
      }
    } finally { if (loadId === state.loadId) setBusy(false); }
  }
  function render() {
    const w = state.workspace;
    if (!w) return;
    $("scope").textContent = `${w.actor.role === "viewer" ? "Solo lectura" : "Revisión comercial"} · ${w.branches.map(item => branchName(item.id)).join(" / ")}`;
    $("engine").textContent = w.mode === "bedrock" ? "IA · Amazon Bedrock" : "Respaldo offline · Simulación local sin IA";
    $("engine").title = w.model_id || "Interpretación de demo sin llamadas al modelo";
    const fresh = !!w.analyzed_revision && w.source_revision === w.analyzed_revision && w.analysis_status === "ready";
    $("analysis-state").textContent = w.analysis_status === "analysis_failed" ? "Falló el último análisis · requiere revisión" : fresh ? "Fuentes analizadas" : w.analyzed_revision ? "Fuentes cambiaron · requiere análisis" : "Fuentes listas · sin analizar";
    $("analysis-state").parentElement.parentElement.dataset.status = fresh ? "ready" : "pending";
    $("cutoff").textContent = `Corte de las fuentes: ${date(w.as_of)}`;
    $("inbox-count").textContent = w.recommendations.filter(item => item.status === "pending").length;
    $("sources-count").textContent = ["conversations", "movements", "stock", "documents"].reduce((sum, key) => sum + w[key].length, 0);
    $("run-info").textContent = w.last_run ? `Último análisis: ${date(w.last_run.at)} · ${number(w.last_run.model_calls)} llamadas al modelo · ${number(w.last_run.cache_hits)} reutilizadas` : "Aún no se ha analizado este contexto.";
    renderList();
    renderDetail();
    renderSources();
    setBusy(state.busy);
  }
  function renderList() {
    const target = $("recommendation-list");
    target.replaceChildren();
    const items = filteredRecommendations();
    if (!items.length) {
      target.append(node("p", state.filter === "history" ? "Las decisiones y las propuestas sustituidas aparecerán aquí." : "No hay propuestas pendientes.", "queue-empty"));
      return;
    }
    for (const item of items) {
      const row = button("", "recommendation-row", () => {
        state.selected = item.id;
        renderList();
        renderDetail();
        if (matchMedia("(max-width: 680px)").matches) $("recommendation-detail").scrollIntoView({ behavior: "auto", block: "start" });
      });
      row.setAttribute("aria-current", String(item.id === state.selected));
      const meta = node("span", null, "row-meta");
      meta.append(node("span", item.city), node("span", label(item.status === "pending" ? item.priority : item.status), `status-label ${item.status === "pending" ? item.priority : item.status}`));
      row.append(meta, node("span", label(item.kind), "row-title"), node("span", item.product, "row-product"), node("span", item.branch_id.replaceAll("-demo", ""), "row-description"));
      target.append(row);
    }
  }
  function empty(title, description) {
    const result = node("div", null, "empty-state");
    result.append(node("h2", title), node("p", description));
    return result;
  }
  function section(title, text) {
    const result = node("section", null, "detail-section");
    result.append(node("h3", title));
    if (text) result.append(node("p", text));
    return result;
  }
  function listSection(title, items) {
    const result = section(title);
    const list = node("ul");
    for (const item of items) list.append(node("li", label(item)));
    result.append(list);
    return result;
  }
  function renderDetail() {
    const target = $("recommendation-detail");
    target.replaceChildren();
    const w = state.workspace;
    const item = getSelected();
    if (!item) {
      const result = empty(w.analyzed_revision ? "Todo listo para revisar" : "De las fuentes a una decisión", w.analyzed_revision ? "Selecciona una propuesta de la bandeja o consulta el historial. Puedes explorar las fuentes originales en cualquier momento." : "Analiza las conversaciones, el inventario y los documentos. Aquí aparecerán las propuestas con sus citas, cálculos y condiciones para tu revisión.");
      if (!w.analyzed_revision) {
        const analyze = button("Analizar fuentes", "primary", () => loadWorkspace("analyze"));
        analyze.dataset.runAnalysis = "true";
        analyze.disabled = state.busy || w.actor.role !== "operator";
        result.append(analyze);
        if (w.actor.role !== "operator") result.append(node("p", "Elige un perfil encargado o jefe de zona para iniciar el análisis."));
      }
      target.append(result);
      return;
    }
    const grounding = item.grounding || {};
    const heading = node("header", null, "detail-heading");
    const titles = node("div");
    titles.append(node("span", label(item.kind), "detail-kind"), node("h2", item.product), node("p", branchName(item.branch_id)));
    heading.append(titles, node("span", label(item.status), `status-label ${item.status}`));
    target.append(heading, section("La situación", grounding.explanation || item.reason));
    const e = item.evidence || {};
    const chain = node("dl", null, "evidence-chain");
    const facts = [
      ["Consultas recientes", number(e.recent_conversations), `Antes: ${number(e.previous_conversations)}`],
      ["Stock disponible", `${number(e.available_units)} uds.`, `${number(e.days_cover)} días de cobertura`],
      ["Ventas registradas", `${number(e.sold_units)} uds.`, "En la ventana analizada"],
      ["Condiciones", `${(grounding.documents || []).length} documentos`, "Citas y vigencia abajo"],
    ];
    for (const [title, value, note] of facts) {
      const fact = node("div", null, "chain-link");
      const dd = node("dd", value);
      dd.append(node("small", note));
      fact.append(node("dt", title), dd);
      chain.append(fact);
    }
    target.append(chain);
    const calculation = section("Cálculo operativo · determinista");
    calculation.append(node("p", grounding.calculation || "No hay un cálculo de unidades para esta propuesta.", "calculation"));
    if (item.suggested_units != null) calculation.append(node("p", `Cantidad sugerida para revisar: ${number(item.suggested_units)} unidades.`));
    target.append(calculation);
    if (item.promotion_plan) {
      const promotion = section("Condiciones de la promoción propuesta");
      promotion.append(fields(item.promotion_plan));
      target.append(promotion);
    }
    const citations = section("Evidencia citada");
    citations.append(node("p", item.analysis_mode === "bedrock" ? "Interpretación de IA contrastada con estas fuentes. Revisa el contenido original." : "Interpretación offline de demo. Revisa el contenido original.", "muted"));
    for (const [key, title] of [["conversations", "Conversación"], ["documents", "Documento"]]) {
      const group = grounding[key] || [];
      const extra = node("details", null, "more-citations");
      extra.append(node("summary", `Ver ${Math.max(0, group.length - 2)} citas más de ${key === "conversations" ? "conversaciones" : "documentos"}`));
      group.forEach((citation, index) => {
        const figure = node("figure", null, "citation");
        const open = button(`${title} · ${citation.title || citation.id} ↗`, "text-button", () => openSource(key, citation.id));
        figure.append(open, node("blockquote", citation.excerpt || "Abre la fuente para revisar su contenido."));
        if (key === "documents") figure.append(node("figcaption", item.analysis_mode === "bedrock" && citation.selected_by_model ? "Referencia seleccionada por la IA y validada por reglas." : "Condición documental aplicada por reglas.", "citation-caption"));
        (index < 2 ? citations : extra).append(figure);
      });
      if (group.length > 2) citations.append(extra);
    }
    if (!(grounding.conversations?.length || grounding.documents?.length)) citations.append(node("p", "Esta propuesta no incluye citas. Revisa las fuentes antes de tomar una decisión."));
    citations.append(node("h4", "Registros operativos"));
    for (const id of e.movement_ids || []) {
      const movement = w.movements.find(row => row.id === id);
      citations.append(button(`Movimiento · ${id}${movement ? ` · ${number(movement.units)} unidades` : ""} ↗`, "text-button", () => openSource("movements", id)));
    }
    citations.append(button(`Inventario · ${item.sku} / ${item.branch_id} ↗`, "text-button", () => openSource("stock", `${item.sku}:${item.branch_id}`)));
    target.append(citations);
    if (grounding.missing_information?.length) target.append(listSection("Información pendiente", grounding.missing_information));
    if (grounding.required_approvals?.length) target.append(listSection("Aprobaciones requeridas", grounding.required_approvals));
    if (grounding.blockers?.length) target.append(listSection("Condiciones que bloquean la aprobación", grounding.blockers));
    const decision = node("section", null, "decision-area");
    decision.append(node("h3", "Tu decisión"), node("p", `Vigencia de la propuesta: ${date(item.expires_at)}. Corte de inventario: ${date(e.stock_observed_at)}.`));
    if (item.status === "pending") {
      const blockers = approvalBlockers(w, item);
      const actions = node("div", null, "decision-actions");
      const approve = button("Aprobar intención", "primary", () => confirmDecision("approve"));
      const reject = button("Rechazar propuesta", "secondary", () => confirmDecision("reject"));
      approve.dataset.decision = "approve";
      approve.dataset.blocked = String(blockers.length > 0);
      approve.disabled = state.busy || blockers.length > 0;
      reject.dataset.decision = "reject";
      reject.dataset.blocked = String(w.actor.role !== "operator");
      reject.disabled = state.busy || w.actor.role !== "operator";
      actions.append(approve, reject);
      decision.append(actions);
      if (blockers.length) decision.append(node("p", blockers.join(" "), "decision-blocker"));
    } else decision.append(node("p", item.status === "approved" ? "Intención registrada. No se ha ejecutado ninguna acción comercial." : `Estado registrado: ${label(item.status).toLocaleLowerCase("es")}.`));
    decision.append(node("p", "Aprobar registra tu intención; no compra productos ni activa promociones."));
    target.append(decision);
    const history = node("details", null, "event-log");
    history.append(node("summary", "Historial de esta propuesta"));
    const events = node("div");
    history.append(events);
    history.addEventListener("toggle", () => { if (history.open) loadEvents(item.id, events); });
    target.append(history);
  }
  async function loadEvents(id, target) {
    target.replaceChildren(node("p", "Cargando historial…", "muted"));
    const profile = state.profile;
    try {
      const events = state.events.get(id) || await request(`/workspace/recommendations/${encodeURIComponent(id)}/events`);
      if (profile !== state.profile || !target.isConnected) return;
      state.events.set(id, events);
      const list = node("ol");
      for (const event of events) {
        const row = node("li");
        row.append(node("span", `${label(event.kind)} · ${event.actor_id}`), node("time", date(event.timestamp)));
        list.append(row);
      }
      target.replaceChildren(events.length ? list : node("p", "Sin eventos registrados.", "muted"));
    } catch (error) { if (target.isConnected) target.replaceChildren(node("p", ERRORS[error.code] || "No se pudo cargar el historial. Ciérralo y vuelve a abrirlo.", "muted")); }
  }
  function confirmDecision(decision) {
    const item = getSelected();
    if (!item || state.busy || state.workspace.actor.role !== "operator" || item.status !== "pending") return;
    if (decision === "approve" && approvalBlockers(state.workspace, item).length) { renderDetail(); return; }
    state.confirmation = { id: item.id, decision };
    $("decision-title").textContent = decision === "approve" ? "¿Aprobar esta intención?" : "¿Rechazar esta propuesta?";
    $("decision-description").textContent = decision === "approve" ? "Confirma que revisaste la evidencia y las condiciones. Se guardará tu aprobación con el perfil seleccionado." : "Se guardará el rechazo de esta propuesta con el perfil seleccionado.";
    $("decision-target").textContent = `${label(item.kind)} · ${item.product} · ${branchName(item.branch_id)}`;
    $("confirm-decision").textContent = decision === "approve" ? "Confirmar aprobación" : "Confirmar rechazo";
    $("decision-dialog").showModal();
  }
  async function submitDecision() {
    const confirmation = state.confirmation;
    if (!confirmation || state.busy) return;
    const item = state.workspace.recommendations.find(row => row.id === confirmation.id);
    if (confirmation.decision === "approve" && approvalBlockers(state.workspace, item).length) {
      $("decision-dialog").close();
      renderDetail();
      announce("La propuesta ya no se puede aprobar. Revisa su vigencia y las condiciones.");
      return;
    }
    clearError();
    setBusy(true, "decision");
    $("confirm-decision").textContent = "Registrando…";
    try {
      const updated = await request(`/workspace/recommendations/${encodeURIComponent(confirmation.id)}/decision`, { method: "POST", body: JSON.stringify({ decision: confirmation.decision }) });
      state.workspace.recommendations = state.workspace.recommendations.map(row => row.id === updated.id ? updated : row);
      state.events.delete(updated.id);
      state.filter = "history";
      syncFilters();
      render();
      announce(confirmation.decision === "approve" ? "Intención aprobada y registrada en el historial. No se ejecutó ninguna acción comercial." : "Propuesta rechazada. La decisión quedó registrada en el historial.", true);
    } catch (error) {
      if (["evidence_changed", "source_changed", "analysis_required"].includes(error.code)) {
        state.workspace.analysis_status = "sources_changed";
        render();
      }
      showError(error);
    }
    finally {
      $("decision-dialog").close();
      state.confirmation = null;
      setBusy(false);
    }
  }
  function fields(record) {
    const dl = node("dl", null, "field-list");
    for (const [key, value] of Object.entries(record || {})) {
      const dd = node("dd");
      if (Array.isArray(value)) dd.textContent = value.map(item => typeof item === "object" ? Object.entries(item).map(([k, v]) => `${label(k)}: ${label(v)}`).join(" · ") : label(item)).join(", ") || "Ninguno";
      else if (value && typeof value === "object") dd.append(fields(value));
      else dd.textContent = typeof value === "boolean" ? value ? "Sí" : "No" : label(value);
      dl.append(node("dt", label(key)), dd);
    }
    return dl;
  }
  function openSource(type, id) {
    state.source = type;
    state.sourceFocus = id;
    $("source-search").value = "";
    setView("sources");
    renderSources();
    const source = [...document.querySelectorAll("[data-source-id]")].find(element => element.dataset.sourceId === id);
    if (source) {
      if (source.tagName === "DETAILS") source.open = true;
      source.scrollIntoView({ behavior: "auto", block: "start" });
      (source.querySelector("summary") || source).focus();
    }
  }
  function renderSources() {
    const w = state.workspace;
    if (!w) return;
    document.querySelectorAll("[data-source]").forEach(element => {
      element.setAttribute("aria-pressed", String(element.dataset.source === state.source));
      const titles = { conversations: "Conversaciones", movements: "Movimientos", stock: "Inventario", documents: "Documentos" };
      element.textContent = `${titles[element.dataset.source]} (${w[element.dataset.source].length})`;
    });
    const target = $("source-content");
    target.replaceChildren();
    const rows = w[state.source].filter(row => sourceMatches({ ...row, product: productName(row.sku), branch: branchName(row.branch_id) }, $("source-search").value.trim()));
    if (!rows.length) { target.append(empty("No hay fuentes para mostrar", $("source-search").value ? "Prueba otra búsqueda o cambia el tipo de fuente." : "Este perfil no tiene fuentes de este tipo disponibles.")); return; }
    if (state.source === "movements" || state.source === "stock") { target.append(sourceTable(rows, state.source)); return; }
    for (const row of rows) {
      const details = node("details", null, "source-record");
      details.dataset.sourceId = row.id;
      details.open = row.id === state.sourceFocus;
      const summary = node("summary");
      const body = node("div", null, "source-body");
      if (state.source === "conversations") {
        summary.append(node("span", row.id, "mono"), node("span", branchName(row.branch_id)), node("span", `${label(row.channel)} · ${date(row.occurred_at)}`, "muted"));
        for (const message of row.messages) {
          const line = node("div", null, "source-message");
          line.append(node("strong", label(message.role)), node("p", message.text));
          body.append(line);
        }
        const interpretation = w.interpretations.find(item => item.conversation_id === row.id);
        const interpretationNode = node("div", null, "source-interpretation");
        if (interpretation) {
          interpretationNode.append(node("strong", `Lectura del análisis: ${label(interpretation.status)}`), node("p", interpretation.reason));
          if (interpretation.sku) interpretationNode.append(node("p", `Producto: ${productName(interpretation.sku)}`));
          if (interpretation.document_ids?.length) interpretationNode.append(node("p", `Documentos: ${interpretation.document_ids.join(", ")}`));
        } else interpretationNode.append(node("p", "Esta conversación aún no tiene interpretación."));
        body.append(interpretationNode);
      } else {
        summary.append(node("span", row.title), node("span", row.id, "mono"), node("span", label(row.kind), "muted"));
        body.append(node("p", row.body, "document-body"), fields({ valid_from: date(row.valid_from), valid_until: date(row.valid_until), branch_ids: row.branch_ids.map(branchName), skus: row.skus.map(productName) }));
        if (row.conditions && Object.keys(row.conditions).length) { body.append(node("h3", "Condiciones documentales"), fields(row.conditions)); }
        const cutoff = epoch(w.as_of);
        if (epoch(row.valid_until) < cutoff || epoch(row.valid_from) > cutoff) body.append(node("p", "Documento fuera de vigencia para el corte de estas fuentes.", "notice"));
      }
      details.append(summary, body);
      target.append(details);
    }
  }
  function sourceTable(rows, type) {
    const wrapper = node("div", null, "table-scroll");
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", type === "stock" ? "Inventario por producto y sucursal" : "Movimientos comerciales");
    const table = node("table");
    const headers = type === "stock" ? ["Producto", "Sucursal", "Disponible", "Objetivo", "Referencia", "Observado"] : ["Producto", "Sucursal", "Tipo", "Unidades", "Fecha", "Registro"];
    const thead = node("thead");
    const tr = node("tr");
    for (const title of headers) { const th = node("th", title); th.scope = "col"; tr.append(th); }
    thead.append(tr);
    const tbody = node("tbody");
    for (const row of rows) {
      const line = node("tr");
      line.dataset.sourceId = type === "stock" ? `${row.sku}:${row.branch_id}` : row.id;
      line.tabIndex = -1;
      const values = type === "stock" ? [productName(row.sku), branchName(row.branch_id), number(row.available_units), number(row.target_units), number(row.reference_units), date(row.observed_at)] : [productName(row.sku), branchName(row.branch_id), label(row.kind), number(row.units), date(row.occurred_at), row.id];
      for (const value of values) line.append(node("td", value));
      tbody.append(line);
    }
    table.append(thead, tbody);
    wrapper.append(table);
    return wrapper;
  }
  function setView(view) {
    state.view = view;
    $("inbox-view").hidden = view !== "inbox";
    $("sources-view").hidden = view !== "sources";
    document.querySelectorAll("[data-view]").forEach(element => {
      if (element.dataset.view === view) element.setAttribute("aria-current", "page");
      else element.removeAttribute("aria-current");
    });
  }
  function syncFilters() { document.querySelectorAll("[data-filter]").forEach(element => element.setAttribute("aria-pressed", String(element.dataset.filter === state.filter))); }
  $("profile").addEventListener("change", () => {
    state.profile = $("profile").value;
    state.workspace = null;
    state.selected = null;
    state.events.clear();
    state.filter = "pending";
    state.sourceFocus = null;
    $("source-search").value = "";
    syncFilters();
    $("recommendation-list").replaceChildren(node("p", "Cargando este perfil…", "queue-empty"));
    $("recommendation-detail").replaceChildren(empty("Cambiando de perfil", "Cargando las fuentes disponibles para este ámbito."));
    $("source-content").replaceChildren();
    loadWorkspace();
  });
  $("refresh").addEventListener("click", () => loadWorkspace());
  $("analyze").addEventListener("click", () => loadWorkspace("analyze"));
  $("burst").addEventListener("click", () => loadWorkspace("burst"));
  $("confirm-decision").addEventListener("click", submitDecision);
  $("decision-dialog").addEventListener("close", () => { if (!state.busy) state.confirmation = null; });
  $("source-search").addEventListener("input", renderSources);
  document.querySelectorAll("[data-view]").forEach(element => element.addEventListener("click", () => setView(element.dataset.view)));
  document.querySelectorAll("[data-filter]").forEach(element => element.addEventListener("click", () => {
    state.filter = element.dataset.filter;
    state.selected = filteredRecommendations()[0]?.id || null;
    syncFilters(); renderList(); if (state.workspace) renderDetail();
  }));
  document.querySelectorAll("[data-source]").forEach(element => element.addEventListener("click", () => { state.source = element.dataset.source; state.sourceFocus = null; renderSources(); }));
  // Expiry can change without another HTTP response. Keep decision affordances honest.
  setInterval(() => {
    if (state.busy || !state.workspace) return;
    const item = getSelected();
    const approve = document.querySelector('[data-decision="approve"]');
    if (item && approve && !approve.disabled && approvalBlockers(state.workspace, item).length) renderDetail();
  }, 10000);
  loadWorkspace();
})();
