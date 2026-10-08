"""Agent 1 — Customer Profiler.

Reads synthetic conversations and purchase movements to build a cumulative
profile per customer alias. Detects recurring SKUs, preferred channels,
time-of-year purchase patterns and branch affinity.

No real customer data is used. Customer IDs are opaque pseudonyms.
Clinical inference is forbidden; profiles describe purchase behaviour only.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class SkuPattern:
    sku: str
    title: str
    mention_count: int
    purchase_count: int
    last_seen: str          # ISO-8601
    months_active: list[int]  # 1–12; repeated entries = higher frequency


@dataclass
class CustomerProfile:
    customer_id: str          # opaque pseudonym — never a real name
    branch_ids: list[str]
    preferred_channel: str | None
    total_mentions: int
    total_purchases: int
    sku_patterns: list[SkuPattern]
    seasonal_months: list[int]   # months where activity spikes
    profile_revision: str        # sha256 of the input that generated this


# ---------------------------------------------------------------------------
# Core profiler
# ---------------------------------------------------------------------------

class CustomerProfiler:
    """Builds customer profiles from synthetic conversations and movements."""

    def __init__(self, sources: dict[str, Any]):
        """
        sources must contain:
          - conversations: list of Conversation dicts
          - movements:     list of Movement dicts  (kind=sale|receipt|adjustment)
          - products:      list of Product dicts   {sku, title}
        """
        self.conversations: list[dict] = sources.get("conversations", [])
        self.movements: list[dict] = sources.get("movements", [])
        self.products: dict[str, str] = {
            p["sku"]: p["title"] for p in sources.get("products", [])
        }

    # ------------------------------------------------------------------
    def _revision(self) -> str:
        payload = json.dumps(
            {"c": len(self.conversations), "m": len(self.movements)}, sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    def run(self) -> list[CustomerProfile]:
        """Return one profile per customer pseudonym found in conversations."""
        # Group conversations by customer_id if present; fall back to branch+channel
        by_customer: dict[str, list[dict]] = defaultdict(list)
        for conv in self.conversations:
            cid = conv.get("customer_id") or _pseudonym(conv)
            by_customer[cid].append(conv)

        # Group sales movements by customer_id (synthetic data may carry it)
        sales_by_customer: dict[str, list[dict]] = defaultdict(list)
        for m in self.movements:
            if m.get("kind") == "sale" and m.get("customer_id"):
                sales_by_customer[m["customer_id"]].append(m)

        revision = self._revision()
        profiles = []
        for cid, convs in by_customer.items():
            profiles.append(self._build(cid, convs, sales_by_customer.get(cid, []), revision))
        return profiles

    # ------------------------------------------------------------------
    def _build(
        self,
        customer_id: str,
        conversations: list[dict],
        sales: list[dict],
        revision: str,
    ) -> CustomerProfile:
        branches: set[str] = set()
        channels: list[str] = []
        sku_mentions: dict[str, list[str]] = defaultdict(list)   # sku -> [iso dates]
        sku_purchases: dict[str, int] = defaultdict(int)
        seasonal_months: list[int] = []

        for conv in conversations:
            if conv.get("branch_id"):
                branches.add(conv["branch_id"])
            if conv.get("channel"):
                channels.append(conv["channel"])
            dt = _parse_dt(conv.get("occurred_at", ""))
            if dt:
                seasonal_months.append(dt.month)
            # SKU signals embedded by the pipeline (field added by Profiler's caller
            # after interpretation — or pre-labelled in synthetic data)
            for sig in conv.get("signals", []):
                sku_mentions[sig["sku"]].append(conv.get("occurred_at", ""))

        for sale in sales:
            sku = sale.get("sku")
            if sku:
                sku_purchases[sku] += int(sale.get("units", 1))
                dt = _parse_dt(sale.get("occurred_at", ""))
                if dt:
                    seasonal_months.append(dt.month)
                    sku_mentions[sku].append(sale.get("occurred_at", ""))

        all_skus = set(sku_mentions) | set(sku_purchases)
        patterns = []
        for sku in all_skus:
            dates = sku_mentions.get(sku, [])
            months = [_parse_dt(d).month for d in dates if _parse_dt(d)]
            patterns.append(
                SkuPattern(
                    sku=sku,
                    title=self.products.get(sku, sku),
                    mention_count=len(dates),
                    purchase_count=sku_purchases.get(sku, 0),
                    last_seen=max(dates) if dates else "",
                    months_active=sorted(months),
                )
            )
        patterns.sort(key=lambda p: -(p.mention_count + p.purchase_count))

        preferred_channel = (
            max(set(channels), key=channels.count) if channels else None
        )

        return CustomerProfile(
            customer_id=customer_id,
            branch_ids=sorted(branches),
            preferred_channel=preferred_channel,
            total_mentions=sum(len(v) for v in sku_mentions.values()),
            total_purchases=sum(sku_purchases.values()),
            sku_patterns=patterns,
            seasonal_months=sorted(set(seasonal_months)),
            profile_revision=revision,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pseudonym(conv: dict) -> str:
    """Derive a stable opaque ID from branch + channel when no customer_id exists."""
    raw = f"{conv.get('branch_id', '')}:{conv.get('channel', '')}:{conv.get('id', '')}"
    return "anon-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def profiles_to_dict(profiles: list[CustomerProfile]) -> list[dict]:
    return [asdict(p) for p in profiles]
