"""Persisted synthetic sources → interpreted context → evidence → human decision."""

import hashlib
import json
import time
from threading import RLock

from mostrador.backoffice import Signal, Snapshot, analyze
from mostrador.backoffice_store import RecommendationStore
from mostrador.bedrock import SYSTEM
from mostrador.domain import DomainError
from mostrador.sales_context import Conversation, Sources, applicable_documents, load_sources
from mostrador.sales_interpretation import (  # noqa: F401
    OfflineInterpreter,
    validate_interpretations,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class SalesWorkspace:
    def __init__(self, path, *, interpreter, sources=None):
        self.base = sources or load_sources()
        self.interpreter = interpreter
        self.store = RecommendationStore(path)
        self.lock = RLock()
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS source_conversations
                    (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS interpretation_cache
                    (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_state
                    (id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL);
            """)

    def sources(self):
        data = self.base.model_dump()
        with self.store.connect() as db:
            data["conversations"] += [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM source_conversations ORDER BY id")
            ]
        return Sources.model_validate(data)

    def revision(self, sources):
        return digest(
            [sources.revision(), self.interpreter.mode, self.interpreter.model_id, SYSTEM]
        )

    def state(self):
        with self.store.connect() as db:
            row = db.execute("SELECT payload FROM workspace_state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {}

    def save_state(self, state):
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO workspace_state VALUES (1, ?)", (json.dumps(state),))

    def view(self, actor):
        with self.lock:
            sources, state = self.sources(), self.state()
            conversations = [c for c in sources.conversations if c.branch_id in actor.branches]
            ids = {c.id for c in conversations}
            revision = self.revision(sources)
            status = state.get("status", "not_analyzed")
            if state.get("revision") and state["revision"] != revision:
                status = "sources_changed"
            recommendations = self.store.list(actor)
            for r in recommendations:
                r["approvable"] = (
                    r.get("approvable", False)
                    and r["status"] == "pending"
                    and r["expires_at"] > time.time()
                    and status == "ready"
                )
            return {
                "mode": self.interpreter.mode,
                "model_id": self.interpreter.model_id,
                "synthetic": True,
                "as_of": sources.operations.as_of.isoformat(),
                "source_revision": revision,
                "analyzed_revision": state.get("revision"),
                "analysis_status": status,
                "actor": {"id": actor.id, "role": actor.role, "branches": list(actor.branches)},
                "branches": [
                    b.model_dump() for b in sources.operations.branches if b.id in actor.branches
                ],
                "products": [p.model_dump() for p in sources.operations.products],
                "conversations": [c.model_dump(mode="json") for c in conversations],
                "documents": [
                    d.model_dump(mode="json")
                    for d in sources.documents
                    if set(d.branch_ids) & set(actor.branches)
                ],
                "movements": [
                    m.model_dump(mode="json")
                    for m in sources.operations.movements
                    if m.branch_id in actor.branches
                ],
                "stock": [
                    s.model_dump(mode="json")
                    for s in sources.operations.stock
                    if s.branch_id in actor.branches
                ],
                "interpretations": [
                    i for i in state.get("interpretations", []) if i["conversation_id"] in ids
                ],
                "recommendations": recommendations,
                "last_run": state.get("last_run"),
                "burst_added": all(
                    c.id in {x.id for x in sources.conversations} for c in sources.burst
                ),
            }

    @staticmethod
    def operator(actor):
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)

    def add_conversation(self, conversation: Conversation, actor):
        self.operator(actor)
        if conversation.branch_id not in actor.branches:
            raise DomainError("permission_denied", 403)
        with self.lock:
            sources = self.sources()
            existing = next((c for c in sources.conversations if c.id == conversation.id), None)
            if existing:
                if existing != conversation:
                    raise DomainError("conversation_conflict", 409)
                return self.view(actor)
            data = sources.model_dump()
            data["conversations"].append(conversation.model_dump())
            Sources.model_validate(data)
            with self.store.connect() as db:
                db.execute(
                    "INSERT INTO source_conversations VALUES (?, ?)",
                    (conversation.id, conversation.model_dump_json()),
                )
            return self.view(actor)

    def add_burst(self, actor):
        self.operator(actor)
        if not all(c.branch_id in actor.branches for c in self.base.burst):
            raise DomainError("permission_denied", 403)
        with self.lock:
            for conversation in self.base.burst:
                self.add_conversation(conversation, actor)
            return self.view(actor)

    def interpret(self, sources):
        active = [
            d for d in sources.documents if d.valid_from <= sources.operations.as_of < d.valid_until
        ]
        context = {
            "catalog": [p.model_dump() for p in sources.operations.products],
            "branches": [b.model_dump() for b in sources.operations.branches],
            "documents": [d.model_dump(mode="json") for d in active],
            "eligible_documents": {
                b.id: {
                    p.sku: [d.id for d in applicable_documents(sources, p.sku, b.id)]
                    for p in sources.operations.products
                }
                for b in sources.operations.branches
            },
        }
        namespace = digest([SYSTEM, self.interpreter.mode, self.interpreter.model_id, context])
        rows, missing = [], []
        hits, calls = 0, 0
        for c in sources.conversations:
            key = digest([namespace, c.model_dump(mode="json")])
            with self.store.connect() as db:
                cached = db.execute(
                    "SELECT payload FROM interpretation_cache WHERE key=?", (key,)
                ).fetchone()
            if cached:
                rows += validate_interpretations({"items": [json.loads(cached[0])]}, [c], sources)
                hits += 1
            else:
                missing.append((key, c))
        for offset in range(0, len(missing), 8):
            batch = missing[offset : offset + 8]
            payload = {**context, "conversations": [c.model_dump(mode="json") for _, c in batch]}
            reply = self.interpreter.infer(payload)
            calls += 1
            parsed = validate_interpretations(reply, [c for _, c in batch], sources)
            keys = {c.id: key for key, c in batch}
            with self.store.connect() as db:
                for row in parsed:
                    db.execute(
                        "INSERT OR REPLACE INTO interpretation_cache VALUES (?, ?)",
                        (keys[row.conversation_id], row.model_dump_json()),
                    )
            rows += parsed
        return rows, hits, calls

    def run(self, actor):
        self.operator(actor)
        if not self.lock.acquire(blocking=False):
            raise DomainError("analysis_in_progress", 409)
        try:
            sources = self.sources()
            revision = self.revision(sources)
            rows, hits, calls = self.interpret(sources)
            by_id = {c.id: c for c in sources.conversations}
            data = sources.operations.model_dump()
            data["context_revision"] = revision
            data["signals"] = [
                Signal(
                    id=r.conversation_id,
                    conversation_id=r.conversation_id,
                    sku=r.sku,
                    branch_id=r.branch_id,
                    occurred_at=by_id[r.conversation_id].occurred_at,
                    message=by_id[r.conversation_id].text()[:500],
                ).model_dump()
                for r in rows
                if r.status == "matched"
            ]
            snapshot = Snapshot.model_validate(data)
            proposals = [ground(p, sources, rows, self.interpreter.mode) for p in analyze(snapshot)]
            self.store.record(snapshot, proposals=proposals, renew_expired=True)
            self.save_state(
                {
                    "status": "ready",
                    "revision": revision,
                    "snapshot": snapshot.model_dump(mode="json"),
                    "interpretations": [r.model_dump() for r in rows],
                    "last_run": {
                        "mode": self.interpreter.mode,
                        "model_id": self.interpreter.model_id,
                        "cache_hits": hits,
                        "model_calls": calls if self.interpreter.mode == "bedrock" else 0,
                        "at": int(time.time()),
                    },
                }
            )
            return self.view(actor)
        except DomainError:
            state = self.state()
            state["status"] = "analysis_failed"
            self.save_state(state)
            raise
        finally:
            self.lock.release()

    def decide(self, identifier, decision, actor):
        self.operator(actor)
        with self.lock:
            proposal = self.store.get(identifier, actor)
            state = self.state()
            if decision == "approve" and proposal["status"] == "pending":
                if state.get("revision") != self.revision(self.sources()):
                    raise DomainError("evidence_changed", 409)
                if state.get("status") != "ready":
                    raise DomainError("analysis_required", 409)
                if not proposal["approvable"]:
                    raise DomainError("missing_required_context", 409)
            if not state.get("snapshot"):
                raise DomainError("analysis_required", 409)
            return self.store.decide(
                identifier, decision, actor, Snapshot.model_validate(state["snapshot"])
            )

    def events(self, identifier, actor):
        return self.store.events(identifier, actor)


def ground(proposal, sources, interpretations, mode):
    documents = applicable_documents(sources, proposal["sku"], proposal["branch_id"])
    procedure = [d for d in documents if d.kind == "procedure"]
    promotions = [d for d in documents if d.kind == "promotion"]
    missing, blockers = [], []
    used = procedure if proposal["kind"] == "replenish" else []
    if proposal["kind"] == "replenish":
        missing.append("Confirmar proveedor y plazo de entrega antes de emitir una compra.")
        if not procedure:
            blockers.append(
                "No hay un procedimiento vigente de abastecimiento para esta sucursal y producto."
            )
    if proposal["promotion_plan"]:
        used = [*used, *promotions]
        if promotions:
            durations = [
                d.conditions.max_duration_days for d in promotions if d.conditions.max_duration_days
            ]
            proposal["promotion_plan"]["duration_days"] = min([7, *durations])
        else:
            missing.append("Falta un documento vigente con condiciones de promoción.")
            if proposal["kind"] == "review_promotion":
                blockers.append("No se puede aprobar una promoción sin condiciones documentadas.")
            else:
                proposal["promotion_plan"] = None
        missing.append(
            "Definir descuento, presupuesto y elegibilidad antes de publicar una campaña."
        )
    evidence = proposal["evidence"]
    ids = set(evidence["signal_ids"] + evidence["baseline_signal_ids"])
    selected_ids = {d for i in interpretations if i.conversation_id in ids for d in i.document_ids}
    calculation = (
        f"Objetivo {evidence['replenishment_target_units']}"
        f" − disponibles {evidence['available_units']} = {proposal['suggested_units']} unidades."
        f" Horizonte: {evidence['replenishment_days']} días."
        if proposal["suggested_units"] is not None
        else (
            f"{evidence['recent_conversations']} conversaciones recientes "
            f"frente a {evidence['previous_conversations']} anteriores."
        )
    )
    proposal.update(
        {
            "analysis_mode": mode,
            "approvable": not blockers,
            "grounding": {
                "explanation": proposal["reason"],
                "calculation": calculation,
                "conversations": [
                    {"id": c.id, "excerpt": c.text()} for c in sources.conversations if c.id in ids
                ],
                "documents": [
                    {
                        "id": d.id,
                        "title": d.title,
                        "excerpt": d.body,
                        "selected_by_model": d.id in selected_ids,
                    }
                    for d in used
                ],
                "missing_information": missing,
                "required_approvals": sorted(
                    {
                        "Revisión humana de esta propuesta (sin ejecución)",
                        *(a for d in used for a in d.conditions.required_approvals),
                    }
                ),
                "blockers": blockers,
            },
        }
    )
    return proposal
