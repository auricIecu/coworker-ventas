"""Agent 3 — Auditor + Executor.

Crosses CustomerProfile data (from Profiler) with StockObservation data
(from StockObserver) to generate actionable insights for the branch/zone manager.

Lifecycle:
  1. run()        → produces a list of AuditInsight with status=pending
  2. decide()     → manager approves or rejects an insight
       approve    → status=executing, then execute() is called automatically
       reject     → status=rejected; next run() will produce fresh alternatives
  3. execute()    → simulated dispatch (alert record + campaign stub)
                    status becomes executed | failed

No real email, push notification or campaign platform is contacted.
Everything is recorded in the provided InsightStore (SQLite-backed).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from mostrador.agents.profiler import CustomerProfile
from mostrador.agents.stock_observer import StockObservation, StockSignal
from mostrador.domain import DomainError

# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

InsightKind = Literal[
    "replenish_and_promote",  # low stock + seasonal spike → restock first, then campaign
    "promote_available",  # good stock + spike → launch campaign now
    "replenish_only",  # low stock, no spike → just restock, no promo yet
    "seasonal_alert",  # YoY spike detected, manager should review
]

InsightStatus = Literal[
    "pending", "approved", "rejected", "executing", "executed", "failed", "superseded"
]


@dataclass
class ExecutionRecord:
    kind: Literal["alert", "campaign_stub"]
    channel: Literal["simulated_email", "simulated_push", "simulated_dashboard"]
    recipient_role: str
    subject: str
    body: str
    dispatched_at: str


@dataclass
class AuditInsight:
    id: str
    sku: str
    product_title: str
    branch_id: str
    kind: InsightKind
    priority: Literal["high", "medium", "low"]
    headline: str  # one-line summary for the manager UI
    rationale: str  # evidence-based explanation
    suggested_action: str  # concrete recommended step
    campaign_draft: dict | None  # stub campaign if applicable
    evidence: dict  # numbers that support the insight
    status: InsightStatus
    created_at: str
    expires_at: str  # insight is stale after this
    execution: ExecutionRecord | None = None


# ---------------------------------------------------------------------------
# Insight store (thin SQLite wrapper)
# ---------------------------------------------------------------------------


class InsightStore:
    """Persists audit insights and their decisions across requests."""

    TTL_SECONDS = 900  # 15 min, matching RecommendationStore

    def __init__(self, path: str):
        if path == ":memory:":
            raise ValueError("Use a file for durable insight decisions")
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS insights (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS insight_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def _event(self, db, insight_id: str, kind: str, actor_id: str, now: int):
        db.execute(
            "INSERT INTO insight_events (insight_id, kind, actor_id, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (insight_id, kind, actor_id, now),
        )

    def save(self, insight: AuditInsight) -> None:
        now = int(time.time())
        expires = now + self.TTL_SECONDS
        with self._connect() as db:
            existing = db.execute(
                "SELECT status FROM insights WHERE id = ?", (insight.id,)
            ).fetchone()
            if existing:
                # Never overwrite a decided insight
                if existing["status"] not in {"pending"}:
                    return
                db.execute(
                    "UPDATE insights SET payload = ?, expires_at = ? WHERE id = ?",
                    (json.dumps(asdict(insight)), expires, insight.id),
                )
            else:
                db.execute(
                    "INSERT INTO insights VALUES (?, ?, ?, ?, ?)",
                    (insight.id, json.dumps(asdict(insight)), "pending", now, expires),
                )
                self._event(db, insight.id, "proposed", "auditor-agent", now)

    def get(self, insight_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM insights WHERE id = ?", (insight_id,)).fetchone()
        if row is None:
            raise DomainError("insight_not_found", 404)
        return self._decode(row)

    @staticmethod
    def _decode(row) -> dict:
        return {
            **json.loads(row["payload"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "execution_status": "simulated" if row["status"] == "executed" else "not_configured",
        }

    def list(self, branch_ids: list[str] | None = None) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM insights ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload"])
            if branch_ids is not None and payload.get("branch_id") not in branch_ids:
                continue
            result.append(self._decode(row))
        return result

    def decide(self, insight_id: str, decision: str, actor_id: str) -> dict:
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_decision", 422)
        now = int(time.time())
        with self._connect() as db:
            row = db.execute("SELECT * FROM insights WHERE id = ?", (insight_id,)).fetchone()
            if row is None:
                raise DomainError("insight_not_found", 404)
            current_status = row["status"]
            requested = "approved" if decision == "approve" else "rejected"
            if current_status == requested or (
                decision == "approve" and current_status == "executed"
            ):
                return self._decode(row)
            if current_status != "pending":
                raise DomainError("decision_conflict", 409)
            if decision == "approve" and now >= row["expires_at"]:
                raise DomainError("insight_expired", 409)
            new_status = "approved" if decision == "approve" else "rejected"
            db.execute("UPDATE insights SET status = ? WHERE id = ?", (new_status, insight_id))
            self._event(db, insight_id, new_status, actor_id, now)
        return self.get(insight_id)

    def record_execution(self, insight_id: str, execution: ExecutionRecord, actor_id: str) -> dict:
        now = int(time.time())
        with self._connect() as db:
            row = db.execute("SELECT * FROM insights WHERE id = ?", (insight_id,)).fetchone()
            if row is None:
                raise DomainError("insight_not_found", 404)
            if row["status"] == "executed":
                return self._decode(row)
            if row["status"] != "approved":
                raise DomainError("insight_not_approved", 409)
            payload = json.loads(row["payload"])
            payload["execution"] = asdict(execution)
            db.execute(
                "UPDATE insights SET payload = ?, status = 'executed' WHERE id = ?",
                (json.dumps(payload), insight_id),
            )
            self._event(db, insight_id, "executed", actor_id, now)
        return self.get(insight_id)

    def supersede(self, current_ids: set[str]) -> None:
        # This pipeline scans the whole synthetic dataset, not the actor's subset.
        with self._connect() as db:
            for row in db.execute(
                "SELECT id, payload FROM insights WHERE status='pending'"
            ).fetchall():
                if row["id"] not in current_ids:
                    db.execute("UPDATE insights SET status='superseded' WHERE id=?", (row["id"],))
                    self._event(db, row["id"], "superseded", "auditor-agent", int(time.time()))

    def events(self, insight_id: str) -> list[dict]:
        with self._connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT sequence, kind, actor_id, timestamp FROM insight_events "
                    "WHERE insight_id = ? ORDER BY sequence",
                    (insight_id,),
                )
            ]


# ---------------------------------------------------------------------------
# Core auditor
# ---------------------------------------------------------------------------

_SPIKE_THRESHOLD = 1.5  # YoY ratio ≥ 1.5 = seasonal spike
_MIN_PROFILES_FOR_PATTERN = 2  # at least 2 customers showing the same behaviour


class Auditor:
    """Crosses profile and stock data to produce actionable insights."""

    def __init__(self, store: InsightStore):
        self.store = store

    # ------------------------------------------------------------------
    def run(
        self,
        observation: StockObservation,
        profiles: list[CustomerProfile],
    ) -> list[AuditInsight]:
        """
        Generate insights by crossing stock signals with customer patterns.
        Insights are persisted in the store; already-decided ones are skipped.
        """
        insights: list[AuditInsight] = []
        for signal in observation.signals:
            insight = self._evaluate(signal, profiles, observation.as_of)
            if insight:
                self.store.save(insight)
                insights.append(insight)
        self.store.supersede({i.id for i in insights})
        return insights

    # ------------------------------------------------------------------
    def _evaluate(
        self,
        signal: StockSignal,
        profiles: list[CustomerProfile],
        as_of_str: str,
    ) -> AuditInsight | None:
        # How many customer profiles also show this SKU active in current month?
        as_of = _parse_dt(as_of_str) or datetime.now(UTC)
        observed = _parse_dt(signal.observed_at)
        if observed is None or not timedelta(0) <= as_of - observed <= timedelta(hours=1):
            return None
        current_month = as_of.month
        matching_profiles = [
            p
            for p in profiles
            if signal.branch_id in p.branch_ids
            and any(
                sp.sku == signal.sku and current_month in sp.months_active for sp in p.sku_patterns
            )
        ]
        profile_match = len(matching_profiles) >= _MIN_PROFILES_FOR_PATTERN

        # Determine insight kind
        if signal.low_stock and signal.seasonal_spike and not signal.active_promotion_ids:
            kind: InsightKind = "replenish_and_promote"
            priority = "high"
            headline = (
                f"Reponer {signal.title} en {signal.branch_id}: "
                f"stock bajo + pico estacional detectado"
            )
            rationale = (
                f"Stock disponible ({signal.available_units} u.) cubre solo "
                f"{signal.coverage_days or '?'} días al ritmo actual. "
                f"Las ventas crecieron {round((signal.yoy_growth_ratio or 1) * 100 - 100)}% "
                f"vs. el mismo período del año anterior. "
                + (
                    f"{len(matching_profiles)} perfiles de clientes muestran compras "
                    f"recurrentes de este producto en este mes. "
                    if profile_match
                    else ""
                )
                + "Prioridad: reabastecer antes de lanzar campaña."
            )
            suggested_action = (
                "1. Emitir orden de reposición al proveedor. "
                "2. Una vez confirmado el stock, activar campaña de pack/descuento."
            )
            campaign_draft = _campaign_stub(signal, "post_replenishment")

        elif not signal.low_stock and signal.seasonal_spike and not signal.active_promotion_ids:
            kind = "promote_available"
            priority = "medium"
            headline = (
                f"Campaña sugerida para {signal.title} en {signal.branch_id}: "
                f"stock OK y demanda en alza"
            )
            rationale = (
                f"Stock suficiente ({signal.available_units} u., "
                f"cobertura {signal.coverage_days or '?'} días). "
                f"Ventas +{round((signal.yoy_growth_ratio or 1) * 100 - 100)}% vs. año anterior. "
                + (
                    f"{len(matching_profiles)} clientes con patrón estacional confirmado. "
                    if profile_match
                    else ""
                )
            )
            suggested_action = (
                "Activar campaña de pack o descuento; condiciones y presupuesto "
                "deben ser aprobados antes de publicar."
            )
            campaign_draft = _campaign_stub(signal, "immediate")

        elif signal.low_stock:
            kind = "replenish_only"
            priority = "medium"
            headline = f"Reabastecer {signal.title} en {signal.branch_id}"
            rationale = (
                f"Stock bajo ({signal.available_units} u. de {signal.target_units} objetivo). "
                "No se propone otra campaña: revisar abastecimiento y promociones vigentes."
            )
            suggested_action = "Emitir orden de reposición."
            campaign_draft = None

        elif signal.seasonal_spike and not signal.low_stock:
            # Already covered by promote_available above; skip duplicates
            return None

        else:
            return None  # No actionable signal

        evidence = {
            "available_units": signal.available_units,
            "target_units": signal.target_units,
            "coverage_days": signal.coverage_days,
            "sold_last_window": signal.sold_last_window,
            "sold_prior_year_equivalent": signal.sold_equivalent_period_prior_year,
            "yoy_growth_ratio": signal.yoy_growth_ratio,
            "active_promotion_ids": signal.active_promotion_ids,
            "matching_customer_profiles": len(matching_profiles),
            "observation_as_of": as_of_str,
            "stock_observed_at": signal.observed_at,
            "matching_profile_ids": sorted(p.customer_id for p in matching_profiles),
            "profile_revisions": sorted(p.profile_revision for p in matching_profiles),
        }

        insight_id = _insight_id(signal.sku, signal.branch_id, kind, evidence)
        return AuditInsight(
            id=insight_id,
            sku=signal.sku,
            product_title=signal.title,
            branch_id=signal.branch_id,
            kind=kind,
            priority=priority,
            headline=headline,
            rationale=rationale,
            suggested_action=suggested_action,
            campaign_draft=campaign_draft,
            evidence=evidence,
            status="pending",
            created_at=as_of_str,
            expires_at="",  # set by InsightStore.save()
            execution=None,
        )

    # ------------------------------------------------------------------
    def execute(self, insight_id: str, actor_id: str) -> dict:
        """
        Simulate execution of an approved insight.
        Builds an ExecutionRecord (alert + campaign stub) and persists it.
        No real external system is contacted.
        """
        insight = self.store.get(insight_id)
        if insight.get("status") == "executed":
            return insight
        if insight.get("status") != "approved":
            raise DomainError("insight_not_approved", 409)

        execution = ExecutionRecord(
            kind="campaign_stub",
            channel="simulated_dashboard",
            recipient_role="branch_manager",
            subject=f"[Sales HQ] Acción aprobada: {insight.get('headline', '')}",
            body=(
                f"Insight aprobado por {actor_id}.\n\n"
                f"Acción sugerida: {insight.get('suggested_action', '')}\n\n"
                "Campaña borrador: "
                f"{json.dumps(insight.get('campaign_draft'), ensure_ascii=False)}\n\n"
                "NOTA: Este es un registro sintético de demo. "
                "Ninguna compra, campaña ni comunicación real fue ejecutada."
            ),
            dispatched_at=datetime.now(UTC).isoformat(),
        )
        return self.store.record_execution(insight_id, execution, actor_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insight_id(sku: str, branch_id: str, kind: str, evidence: dict) -> str:
    raw = json.dumps([sku, branch_id, kind, evidence], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _campaign_stub(signal: StockSignal, activation: str) -> dict:
    return {
        "sku": signal.sku,
        "branch_id": signal.branch_id,
        "activation_condition": activation,
        "suggested_duration_days": 7,
        "discount_and_budget": "requires_commercial_review",
        "pack_option": "requires_review",
        "note": (
            "Borrador de campaña. Descuento, presupuesto y elegibilidad "
            "deben ser definidos y aprobados antes de publicar."
        ),
    }


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
