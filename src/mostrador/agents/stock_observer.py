"""Agent 2 — Stock Observer.

Aggregates multi-source stock information, computes coverage metrics and
detects seasonal patterns by comparing the current window against the
equivalent period in the previous year (or the available historical baseline).

Works entirely with synthetic data. No live ERP, SAP or warehouse connection.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class StockSignal:
    sku: str
    title: str
    branch_id: str
    available_units: int
    target_units: int
    coverage_days: float | None        # days of stock at current sales rate
    sold_last_window: int
    sold_equivalent_period_prior_year: int
    yoy_growth_ratio: float | None     # None when no prior-year data
    low_stock: bool
    seasonal_spike: bool               # True when YoY growth ≥ threshold
    active_promotion_ids: list[str]
    observed_at: str


@dataclass
class StockObservation:
    as_of: str
    window_days: int
    signals: list[StockSignal]
    observation_revision: str


# ---------------------------------------------------------------------------
# Core observer
# ---------------------------------------------------------------------------

_LOW_STOCK_RATIO   = 0.25   # available < 25 % of target → low stock
_COVERAGE_DAYS_MIN = 3      # fewer days cover → low stock regardless
_SPIKE_THRESHOLD   = 1.5    # YoY ≥ 150 % = seasonal spike


class StockObserver:
    """Builds a full stock observation from synthetic operations data."""

    def __init__(self, sources: dict[str, Any]):
        """
        sources must contain the same structure as operations.json:
          as_of, window_days, products, branches, stock, movements, promotions
        """
        self.as_of: datetime = _parse_dt(sources.get("as_of", "")) or datetime.now(timezone.utc)
        self.window_days: int = int(sources.get("window_days", 7))
        self.products: dict[str, str] = {
            p["sku"]: p["title"] for p in sources.get("products", [])
        }
        self.stock_rows: list[dict] = sources.get("stock", [])
        self.movements: list[dict] = sources.get("movements", [])
        self.promotions: list[dict] = sources.get("promotions", [])

    # ------------------------------------------------------------------
    def run(self) -> StockObservation:
        window_start = self.as_of - timedelta(days=self.window_days)
        # Equivalent window one year ago (52 weeks back)
        prior_end   = self.as_of   - timedelta(weeks=52)
        prior_start = window_start - timedelta(weeks=52)

        signals: list[StockSignal] = []
        for row in self.stock_rows:
            sku, branch = row["sku"], row["branch_id"]
            available = int(row.get("available_units", 0))
            target    = int(row.get("target_units", 1))

            sold_now  = self._sold(sku, branch, window_start, self.as_of)
            sold_prev = self._sold(sku, branch, prior_start, prior_end)

            coverage = (
                available * self.window_days / sold_now if sold_now > 0 else None
            )
            yoy = sold_now / sold_prev if sold_prev > 0 else None

            low_stock = (
                available <= target * _LOW_STOCK_RATIO
                or (coverage is not None and coverage <= _COVERAGE_DAYS_MIN)
            )
            seasonal_spike = yoy is not None and yoy >= _SPIKE_THRESHOLD

            active_promos = [
                p["id"]
                for p in self.promotions
                if p.get("sku") == sku
                and p.get("branch_id") == branch
                and p.get("enabled", True)
                and _parse_dt(p.get("starts_at", "")) <= self.as_of  # type: ignore[operator]
                < _parse_dt(p.get("ends_at", ""))  # type: ignore[operator]
            ]

            signals.append(
                StockSignal(
                    sku=sku,
                    title=self.products.get(sku, sku),
                    branch_id=branch,
                    available_units=available,
                    target_units=target,
                    coverage_days=round(coverage, 2) if coverage is not None else None,
                    sold_last_window=sold_now,
                    sold_equivalent_period_prior_year=sold_prev,
                    yoy_growth_ratio=round(yoy, 3) if yoy is not None else None,
                    low_stock=low_stock,
                    seasonal_spike=seasonal_spike,
                    active_promotion_ids=active_promos,
                    observed_at=row.get("observed_at", self.as_of.isoformat()),
                )
            )

        return StockObservation(
            as_of=self.as_of.isoformat(),
            window_days=self.window_days,
            signals=signals,
            observation_revision=self._revision(signals),
        )

    # ------------------------------------------------------------------
    def _sold(
        self,
        sku: str,
        branch_id: str,
        start: datetime,
        end: datetime,
    ) -> int:
        return sum(
            int(m.get("units", 0))
            for m in self.movements
            if m.get("sku") == sku
            and m.get("branch_id") == branch_id
            and m.get("kind") == "sale"
            and start <= (_parse_dt(m.get("occurred_at", "")) or start) < end
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _revision(signals: list[StockSignal]) -> str:
        payload = json.dumps(
            [{"sku": s.sku, "branch": s.branch_id, "avail": s.available_units} for s in signals],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
