"""Independent oracle over the JSON fixtures; does NOT test an LLM or add API features."""

import json
from collections import Counter
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

DATA = json.loads(Path("data/synthetic/dataset.json").read_text(encoding="utf-8"))


def date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def price_list_for(customer_id):
    customer = next(c for c in DATA["customers"] if c["customer_id"] == customer_id)
    if customer["segment"] == "general":
        return "general"
    if (
        date(customer["membership_valid_from"])
        <= date(DATA["metadata"]["as_of"])
        < date(customer["membership_valid_until"])
    ):
        return customer["segment"]
    return DATA["business_rules"]["price_list"]["fallback_on_expired_membership"]


def unit_price(sku, price_list):
    return next(
        p["unit_price_cents"]
        for p in DATA["prices"]
        if p["sku"] == sku and p["price_list_id"] == price_list
    )


def promotion_answer(request, at):
    """Use Decimal here, independent of integer generator/validator rounding."""
    selected = [
        next(p for p in DATA["promotions"] if p["promotion_id"] == key)
        for key in request["promotion_ids"]
    ]
    selected.sort(key=lambda p: p["priority"])
    price = unit_price(request["sku"], request["price_list_id"])
    subtotal = price * request["quantity"]
    for promotion in selected:
        checks = [
            (at < date(promotion["valid_from"]), "promotion_not_started"),
            (at >= date(promotion["valid_until"]), "promotion_expired"),
            (request["sku"] not in promotion["sku_ids"], "sku_ineligible"),
            (request["branch_id"] not in promotion["branch_ids"], "branch_ineligible"),
            (request["price_list_id"] not in promotion["price_list_ids"], "price_list_ineligible"),
            (request["quantity"] < promotion["minimum_quantity"], "minimum_quantity_not_met"),
            (subtotal < promotion["minimum_subtotal_cents"], "minimum_subtotal_not_met"),
        ]
        for invalid, code in checks:
            if invalid:
                return {"error": code}
    for promotion in selected:
        if any(
            other["promotion_id"] not in promotion["combinable_with"]
            for other in selected
            if other is not promotion
        ):
            return {"error": "incompatible_promotions"}
    remaining = subtotal
    discounts = []
    for promotion in selected:
        benefit = promotion["benefit"]
        if benefit["kind"] == "percent":
            discount = int(
                (Decimal(remaining) * Decimal(benefit["basis_points"]) / 10_000).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        else:
            groups, _ = divmod(request["quantity"], benefit["buy_quantity"])
            discount = groups * (benefit["buy_quantity"] - benefit["pay_quantity"]) * price
        discount = min(remaining, discount)
        discounts.append(discount)
        remaining -= discount
    return {"subtotal_cents": subtotal, "discounts_cents": discounts, "total_cents": remaining}


def customer_answer(request):
    if not any(c["customer_id"] == request["customer_id"] for c in DATA["customers"]):
        return {"error": "customer_not_found", "must_not_invent_history": True}
    purchases = [p for p in DATA["purchases"] if p["customer_id"] == request["customer_id"]]
    ids = {p["purchase_id"] for p in purchases}
    counts = Counter(line["sku"] for line in DATA["purchase_lines"] if line["purchase_id"] in ids)
    return {
        "purchase_count": len(purchases),
        "total_spent_cents": sum(p["total_cents"] for p in purchases),
        "last_purchase_at": max((p["purchased_at"] for p in purchases), default=None),
        "repeated_sku_ids": sorted(sku for sku, count in counts.items() if count > 1),
    }


def stock_answer(request, at):
    if "customer_id" in request:
        price_list = price_list_for(request["customer_id"])
        price = unit_price(request["sku"], price_list)
        return {
            "price_list_id": price_list,
            "unit_price_cents": price,
            "total_cents": price * request["quantity"],
        }
    rows = [r for r in DATA["inventory"] if r["sku"] == request["sku"]]
    max_age = DATA["business_rules"]["inventory"]["max_age_seconds"]
    if "branch_id" in request:
        row = next(r for r in rows if r["branch_id"] == request["branch_id"])
        if (at - date(row["observed_at"])).total_seconds() > max_age:
            return {"refresh_required": True, "promise_stock": False}
        return {key: row[key] for key in ["on_hand", "reserved", "available"]}
    eligible = [
        r["branch_id"]
        for r in rows
        if r["available"] >= request["quantity"]
        and (at - date(r["observed_at"])).total_seconds() <= max_age
    ]
    return {
        "eligible_branch_ids": eligible,
        "unavailable_branch_ids": [r["branch_id"] for r in rows if r["branch_id"] not in eligible],
    }


def reservation_answer(request):
    if "proposal_id" in request:
        proposal = next(
            p for p in DATA["reservation_proposals"] if p["proposal_id"] == request["proposal_id"]
        )
        result = {"status": proposal["status"]}
        if proposal["status"] == "uncertain":
            result.update(
                automatic_retry=DATA["business_rules"]["reservation"]["automatic_retry_uncertain"],
                reconciliation_required=proposal["reconciliation_required"],
            )
        elif proposal["status"] == "expired":
            result["must_not_reserve"] = True
        else:
            result.update(
                {key: proposal["receipt"][key] for key in ["reservation_id", "held_quantity"]}
            )
        return result
    row = next(
        r
        for r in DATA["inventory"]
        if r["sku"] == request["sku"] and r["branch_id"] == request["branch_id"]
    )
    if row["available"] < request["quantity"]:
        return {
            "error": "insufficient_stock",
            "available": row["available"],
            "must_not_reserve": True,
        }
    return {
        "can_propose": True,
        "human_approval_required": DATA["business_rules"]["reservation"]["requires_human_approval"],
        "stock_delta_on_propose": 0,
    }


@pytest.mark.parametrize("scenario", DATA["scenarios"], ids=lambda s: s["scenario_id"])
def test_golden_answer_is_supported_by_snapshot(scenario):
    request, capability = scenario["input"], scenario["capability"]
    at = date(scenario["as_of"])
    if capability == "product_search":
        found = [
            p
            for p in DATA["products"]
            if request["query"].casefold()
            in f"{p['sku']} {p['name']} {' '.join(p['aliases'])}".casefold()
        ]
        matches = [
            p
            for p in found
            if p["active"]
            and ("presentation" not in request or p["presentation"] == request["presentation"])
        ]
        answer = {"sku_ids": [p["sku"] for p in matches], "needs_clarification": len(matches) > 1}
        if found and all(not p["active"] for p in found):
            answer["reason"] = "inactive_product"
    elif capability == "promotion":
        answer = promotion_answer(request, at)
    elif capability == "customer_360":
        answer = customer_answer(request)
    elif capability == "price_stock":
        answer = stock_answer(request, at)
    elif capability == "reservation":
        answer = reservation_answer(request)
    else:
        pytest.fail(f"Unsupported scenario capability: {capability}")
    assert answer == scenario["expected"]


def test_promotion_start_is_inclusive_and_end_is_exclusive():
    request = {
        "sku": "DEMO-001",
        "quantity": 2,
        "branch_id": "centro",
        "price_list_id": "general",
        "promotion_ids": ["DEMO-P05"],
    }
    assert promotion_answer(request, date("2026-10-01T00:00:00Z"))["total_cents"] == 560
    assert promotion_answer(request, date("2026-10-07T00:00:00Z")) == {"error": "promotion_expired"}


def test_buy_three_pay_two_only_discounts_complete_groups():
    request = {
        "sku": "DEMO-003",
        "quantity": 4,
        "branch_id": "centro",
        "price_list_id": "general",
        "promotion_ids": ["DEMO-P04"],
    }
    assert promotion_answer(request, date(DATA["metadata"]["as_of"])) == {
        "subtotal_cents": 720,
        "discounts_cents": [180],
        "total_cents": 540,
    }
