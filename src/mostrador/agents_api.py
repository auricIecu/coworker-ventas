"""Agent HQ — FastAPI routes for the three-agent pipeline.

Endpoints are mounted under /agents/ and share the same Bearer token
scheme as the rest of the back office.

  POST /agents/run
      Runs all three agents in sequence (Profiler → StockObserver → Auditor).
      Returns the list of generated insights.

  GET  /agents/insights
      Lists all insights visible to the current actor (filtered by branch).

  GET  /agents/insights/{insight_id}
      Returns a single insight with full evidence and execution record.

  POST /agents/insights/{insight_id}/decision
      Manager approves or rejects an insight.
      On approval the Auditor executes immediately (simulated dispatch).

  GET  /agents/insights/{insight_id}/events
      Full audit trail of state transitions for an insight.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from mostrador.agents.auditor import Auditor, InsightStore
from mostrador.agents.profiler import CustomerProfile, CustomerProfiler, profiles_to_dict
from mostrador.agents.stock_observer import StockObserver
from mostrador.domain import DomainError


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_operations() -> dict:
    root = files("mostrador").joinpath("data/sales")
    return json.loads(root.joinpath("operations.json").read_text(encoding="utf-8"))


def _load_historical() -> list[dict]:
    root = files("mostrador").joinpath("data/sales")
    try:
        data = json.loads(root.joinpath("historical_movements.json").read_text(encoding="utf-8"))
        return data.get("movements", [])
    except (OSError, ValueError):
        return []


def _load_customer_seed() -> list[dict]:
    root = files("mostrador").joinpath("data/sales")
    try:
        data = json.loads(
            root.joinpath("customer_profiles_seed.json").read_text(encoding="utf-8")
        )
        return data.get("customers", [])
    except (OSError, ValueError):
        return []


def _load_conversations() -> list[dict]:
    root = files("mostrador").joinpath("data/sales")
    data = json.loads(root.joinpath("conversations.json").read_text(encoding="utf-8"))
    return data.get("conversations", [])


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_agents_router(identity_dep, insight_store: InsightStore) -> APIRouter:
    """
    identity_dep: FastAPI dependency that returns the current Reviewer.
    insight_store: shared InsightStore instance (same SQLite file as the app).
    """
    router = APIRouter(prefix="/agents", tags=["agents"])
    current_actor = Annotated[object, Depends(identity_dep)]
    auditor = Auditor(insight_store)

    # ------------------------------------------------------------------
    @router.post("/run", summary="Run all three agents and return new insights")
    def run_agents(actor: current_actor):
        """
        Executes the full pipeline:
        1. CustomerProfiler — builds profiles from conversations + purchase seed.
        2. StockObserver    — computes stock signals with YoY comparison.
        3. Auditor          — crosses both outputs, generates and persists insights.

        Only insights for branches the actor has access to are returned.
        """
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)

        # --- Agent 1: Profiler ---
        operations = _load_operations()
        conversations = _load_conversations()
        seed_customers = _load_customer_seed()

        # Merge seed purchase history into profiler-friendly format
        # Each seed customer becomes synthetic conversations with embedded signals
        seed_conversations = _seed_to_conversations(seed_customers)
        all_conversations = conversations + seed_conversations

        profiler_sources = {
            "conversations": all_conversations,
            "movements": _seed_to_movements(seed_customers),
            "products": operations.get("products", []),
        }
        profiler = CustomerProfiler(profiler_sources)
        profiles: list[CustomerProfile] = profiler.run()

        # --- Agent 2: StockObserver ---
        historical = _load_historical()
        observer_sources = {
            **operations,
            # Inject prior-year movements alongside current ones for YoY calc
            "movements": operations.get("movements", []) + historical,
        }
        observer = StockObserver(observer_sources)
        observation = observer.run()

        # --- Agent 3: Auditor ---
        insights = auditor.run(observation, profiles)

        # Filter by actor's branch access
        visible = [
            i for i in insights
            if i.branch_id in actor.branches
        ]

        return {
            "agents_run": ["profiler", "stock_observer", "auditor"],
            "profiles_built": len(profiles),
            "stock_signals": len(observation.signals),
            "insights_generated": len(visible),
            "insights": [_insight_dict(i) for i in visible],
        }

    # ------------------------------------------------------------------
    @router.get("/insights", summary="List all insights for the actor's branches")
    def list_insights(actor: current_actor):
        return insight_store.list(branch_ids=list(actor.branches))

    # ------------------------------------------------------------------
    @router.get("/insights/{insight_id}", summary="Get a single insight with full evidence")
    def get_insight(insight_id: str, actor: current_actor):
        insight = insight_store.get(insight_id)
        _authorize(insight, actor)
        return insight

    # ------------------------------------------------------------------
    @router.post(
        "/insights/{insight_id}/decision",
        summary="Approve or reject an insight; approval triggers simulated execution",
    )
    def decide_insight(insight_id: str, body: AgentDecision, actor: current_actor):
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)
        insight = insight_store.get(insight_id)
        _authorize(insight, actor)
        result = insight_store.decide(insight_id, body.decision, actor.id)
        if body.decision == "approve":
            result = auditor.execute(insight_id, actor.id)
        return result

    # ------------------------------------------------------------------
    @router.get("/insights/{insight_id}/events", summary="Audit trail for an insight")
    def insight_events(insight_id: str, actor: current_actor):
        insight = insight_store.get(insight_id)
        _authorize(insight, actor)
        return insight_store.events(insight_id)

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _authorize(insight: dict, actor) -> None:
    if insight.get("branch_id") not in actor.branches:
        raise DomainError("insight_not_found", 404)


def _insight_dict(insight) -> dict:
    from dataclasses import asdict
    return asdict(insight)


def _seed_to_conversations(customers: list[dict]) -> list[dict]:
    """Convert seed customer signal records into conversation dicts for the Profiler."""
    convs = []
    for c in customers:
        cid = c["customer_id"]
        for i, sig in enumerate(c.get("signals", [])):
            convs.append({
                "id": f"seed-conv-{cid}-{i}",
                "customer_id": cid,
                "branch_id": c["branch_ids"][0] if c.get("branch_ids") else None,
                "channel": c.get("preferred_channel", "store"),
                "occurred_at": sig["occurred_at"],
                "messages": [
                    {"role": "customer", "text": f"Consulta sobre {sig['sku']}"},
                ],
                "signals": [{"sku": sig["sku"]}],
            })
    return convs


def _seed_to_movements(customers: list[dict]) -> list[dict]:
    """Convert seed purchase records into movement dicts for the Profiler."""
    movements = []
    for c in customers:
        cid = c["customer_id"]
        branch = c["branch_ids"][0] if c.get("branch_ids") else "unknown"
        for i, purchase in enumerate(c.get("purchases", [])):
            movements.append({
                "id": f"seed-sale-{cid}-{i}",
                "customer_id": cid,
                "sku": purchase["sku"],
                "branch_id": branch,
                "occurred_at": purchase["occurred_at"],
                "kind": "sale",
                "units": purchase.get("units", 1),
            })
    return movements
