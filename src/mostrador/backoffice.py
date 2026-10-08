"""Deterministic demo analysis of synthetic commercial snapshots."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=80)]
Units = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]


@dataclass(frozen=True)
class Reviewer:
    id: str
    role: str
    branches: tuple[str, ...]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Product(Record):
    sku: Identifier
    title: Annotated[str, Field(min_length=1, max_length=160)]


class Branch(Record):
    id: Identifier
    city: Identifier


class Signal(Record):
    id: Identifier
    conversation_id: Identifier
    sku: Identifier
    branch_id: Identifier
    occurred_at: AwareDatetime
    message: Annotated[str, Field(min_length=1, max_length=500)]


class Movement(Record):
    id: Identifier
    sku: Identifier
    branch_id: Identifier
    occurred_at: AwareDatetime
    kind: Literal["sale", "receipt", "adjustment"]
    units: Annotated[int, Field(strict=True, gt=0, le=1_000_000)]


class Stock(Record):
    sku: Identifier
    branch_id: Identifier
    observed_at: AwareDatetime
    available_units: Units
    reference_units: Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
    target_units: Annotated[int, Field(strict=True, gt=0, le=1_000_000)]


class Promotion(Record):
    id: Identifier
    sku: Identifier
    branch_id: Identifier
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    enabled: bool


class Snapshot(Record):
    synthetic: Literal[True]
    context_revision: str = ""
    as_of: AwareDatetime
    coverage_start: AwareDatetime
    window_days: Annotated[int, Field(strict=True, ge=1, le=30)] = 7
    products: Annotated[list[Product], Field(min_length=1, max_length=1000)]
    branches: Annotated[list[Branch], Field(min_length=1, max_length=100)]
    signals: Annotated[list[Signal], Field(max_length=10000)]
    movements: Annotated[list[Movement], Field(max_length=10000)]
    stock: Annotated[list[Stock], Field(min_length=1, max_length=10000)]
    promotions: Annotated[list[Promotion], Field(max_length=1000)]

    @model_validator(mode="after")
    def validate_relations(self):
        if self.coverage_start > self.as_of - timedelta(days=2 * self.window_days):
            raise ValueError("Two complete analysis windows are required")
        for rows, key in (
            (self.products, "sku"),
            (self.branches, "id"),
            (self.signals, "id"),
            (self.movements, "id"),
            (self.promotions, "id"),
        ):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError("Duplicate source identifier")
        skus, branches = {p.sku for p in self.products}, {b.id for b in self.branches}
        pairs = {(s.sku, s.branch_id) for s in self.stock}
        if len(pairs) != len(self.stock):
            raise ValueError("Duplicate stock snapshot")
        for row in [*self.stock, *self.signals, *self.movements, *self.promotions]:
            if row.sku not in skus or row.branch_id not in branches:
                raise ValueError("Unknown product or branch")
            if (row.sku, row.branch_id) not in pairs:
                raise ValueError("Missing stock snapshot")
        for row in [*self.signals, *self.movements]:
            if not self.coverage_start <= row.occurred_at <= self.as_of:
                raise ValueError("Event outside snapshot coverage")
        if any(s.observed_at > self.as_of for s in self.stock):
            raise ValueError("Stock observed after snapshot cutoff")
        if any(p.ends_at <= p.starts_at for p in self.promotions):
            raise ValueError("Invalid promotion window")
        return self

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def load_demo() -> Snapshot:
    return Snapshot.model_validate_json(
        files("mostrador").joinpath("data/backoffice_demo.json").read_text(encoding="utf-8")
    )


def analyze(snapshot: Snapshot) -> list[dict]:
    """Analyze a fixed cutoff. Conversations are interest signals, not sales forecasts."""
    start = snapshot.as_of - timedelta(days=snapshot.window_days)
    previous_start = start - timedelta(days=snapshot.window_days)
    snapshot_id = snapshot.fingerprint()
    titles = {p.sku: p.title for p in snapshot.products}
    cities = {b.id: b.city for b in snapshot.branches}
    result = []
    for stock in snapshot.stock:
        pair = (stock.sku, stock.branch_id)
        signals = [s for s in snapshot.signals if (s.sku, s.branch_id) == pair]
        recent = [s for s in signals if start <= s.occurred_at < snapshot.as_of]
        previous = [s for s in signals if previous_start <= s.occurred_at < start]
        current_count = len({s.conversation_id for s in recent})
        previous_count = len({s.conversation_id for s in previous})
        sales = [
            m
            for m in snapshot.movements
            if (m.sku, m.branch_id) == pair
            and m.kind == "sale"
            and start <= m.occurred_at < snapshot.as_of
        ]
        sold = sum(m.units for m in sales)
        cover = stock.available_units * snapshot.window_days / sold if sold else None
        replenishment_days = max(7, snapshot.window_days)
        sales_target = (
            sold * replenishment_days + snapshot.window_days - 1
        ) // snapshot.window_days
        replenishment_target = max(stock.target_units, sales_target)
        active = [
            p.id
            for p in snapshot.promotions
            if (p.sku, p.branch_id) == pair
            and p.enabled
            and p.starts_at <= snapshot.as_of < p.ends_at
        ]
        growth = current_count / previous_count if previous_count else None
        low_stock = stock.available_units * 4 <= stock.target_units or (
            cover is not None and cover <= 3
        )
        spike = current_count >= 5 and growth is not None and growth >= 2
        units = None
        if snapshot.as_of - stock.observed_at > timedelta(hours=1):
            kind, priority = "refresh_data", "high"
            reason = "Actualizar inventario antes de recomendar una acción comercial."
        elif low_stock and (sold > 0 or spike):
            kind, priority = "replenish", "high"
            units = replenishment_target - stock.available_units
            reason = "Revisar abastecimiento; no impulsar una promoción antes de resolver el stock."
        elif current_count >= 5 and previous_count == 0:
            kind, priority = "review_demand", "medium"
            reason = "Hay interés sin base comparable; revisar antes de inferir crecimiento."
        elif spike and not active:
            kind, priority = "review_promotion", "medium"
            reason = "Revisar una promoción local; el interés creció y no hay promoción vigente."
        else:
            continue
        promotion_plan = None
        if spike and not active and kind in {"replenish", "review_promotion"}:
            promotion_plan = {
                "duration_days": 7,
                "activation_condition": (
                    "stock_replenished_and_revalidated"
                    if kind == "replenish"
                    else "stock_and_terms_revalidated"
                ),
                "discount_and_budget": "requires_review",
            }
        recommendation_id = hashlib.sha256(
            f"{snapshot_id}:{stock.sku}:{stock.branch_id}:{kind}".encode()
        ).hexdigest()
        result.append(
            {
                "id": recommendation_id,
                "snapshot_id": snapshot_id,
                "as_of": snapshot.as_of.isoformat(),
                "sku": stock.sku,
                "product": titles[stock.sku],
                "branch_id": stock.branch_id,
                "city": cities[stock.branch_id],
                "kind": kind,
                "priority": priority,
                "reason": reason,
                "suggested_units": units,
                "promotion_plan": promotion_plan,
                "evidence": {
                    "recent_conversations": current_count,
                    "previous_conversations": previous_count,
                    "growth_ratio": growth,
                    "sold_units": sold,
                    "available_units": stock.available_units,
                    "target_units": stock.target_units,
                    "replenishment_days": replenishment_days,
                    "replenishment_target_units": replenishment_target,
                    "reference_units": stock.reference_units,
                    "stock_percent_of_reference": round(
                        stock.available_units * 100 / stock.reference_units, 2
                    ),
                    "days_cover": round(cover, 2) if cover is not None else None,
                    "active_promotion_ids": active,
                    "signal_ids": [s.id for s in recent],
                    "baseline_signal_ids": [s.id for s in previous],
                    "movement_ids": [m.id for m in sales],
                    "stock_observed_at": stock.observed_at.isoformat(),
                    "recent_window": [start.isoformat(), snapshot.as_of.isoformat()],
                    "baseline_window": [previous_start.isoformat(), start.isoformat()],
                },
            }
        )
    return result
