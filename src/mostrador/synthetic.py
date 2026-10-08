"""Original fixtures, not a production pricing engine or live commerce adapter.

Generate without randomness, network, wall clock, customer records or clinical claims.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

AS_OF = "2026-10-08T14:00:00Z"
SOURCE = "synthetic-mostrador-v1"
START = "2026-09-01T00:00:00Z"
END = "2026-11-01T00:00:00Z"

# name, category, presentation, sale unit, contained amount, content unit, retail cents
CATALOG = [
    ("Gasas demo", "curacion", "10 unidades", "paquete", 10, "unidad", 350),
    ("Shampoo demo", "cabello", "250 ml", "frasco", 250, "ml", 625),
    ("Jabón demo", "higiene", "100 g", "unidad", 100, "g", 180),
    ("Gasas demo", "curacion", "20 unidades", "paquete", 20, "unidad", 600),
    ("Venda demo", "curacion", "5 cm x 5 m", "rollo", 1, "rollo", 450),
    ("Venda demo", "curacion", "10 cm x 5 m", "rollo", 1, "rollo", 725),
    ("Algodón demo", "curacion", "50 g", "bolsa", 50, "g", 225),
    ("Algodón demo", "curacion", "100 g", "bolsa", 100, "g", 390),
    ("Cinta de papel demo", "curacion", "1,25 cm x 9 m", "rollo", 1, "rollo", 310),
    ("Curitas demo", "curacion", "20 unidades", "caja", 20, "unidad", 480),
    ("Shampoo demo", "cabello", "500 ml", "frasco", 500, "ml", 1090),
    ("Acondicionador demo", "cabello", "250 ml", "frasco", 250, "ml", 650),
    ("Jabón líquido demo", "higiene", "250 ml", "frasco", 250, "ml", 420),
    ("Jabón líquido demo", "higiene", "500 ml", "frasco", 500, "ml", 750),
    ("Gel de ducha demo", "higiene", "400 ml", "frasco", 400, "ml", 810),
    ("Cepillo dental demo", "oral", "1 unidad suave", "unidad", 1, "unidad", 290),
    ("Cepillo dental demo", "oral", "2 unidades suaves", "paquete", 2, "unidad", 510),
    ("Pasta dental demo", "oral", "90 g", "tubo", 90, "g", 380),
    ("Pasta dental demo", "oral", "150 g", "tubo", 150, "g", 560),
    ("Hilo dental demo", "oral", "50 m", "dispensador", 50, "m", 430),
    ("Toallitas demo", "cuidado_personal", "40 unidades", "paquete", 40, "unidad", 520),
    ("Toallitas demo", "cuidado_personal", "80 unidades", "paquete", 80, "unidad", 890),
    ("Pañuelos demo", "cuidado_personal", "100 unidades", "caja", 100, "unidad", 270),
    ("Discos de algodón demo", "cuidado_personal", "80 unidades", "paquete", 80, "unidad", 395),
    ("Crema de manos demo", "cuidado_personal", "75 ml", "tubo", 75, "ml", 610),
    ("Peine demo", "accesorios", "1 unidad", "unidad", 1, "unidad", 240),
    ("Estuche de viaje demo", "accesorios", "1 unidad", "unidad", 1, "unidad", 990),
    ("Esponja de baño demo", "accesorios", "1 unidad", "unidad", 1, "unidad", 330),
    ("Guantes demo", "accesorios", "10 unidades talla M", "caja", 10, "unidad", 690),
    ("Neceser demo retirado", "accesorios", "1 unidad", "unidad", 1, "unidad", 1200),
]


def timestamp(offset_seconds: int) -> str:
    instant = datetime.fromisoformat(AS_OF.replace("Z", "+00:00"))
    return (instant + timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z")


def round_basis_points(amount: int, basis_points: int) -> int:
    return (amount * basis_points + 5000) // 10_000


def build_dataset() -> dict:
    data = {
        "metadata": {
            "schema_version": "1.0.0",
            "dataset_id": SOURCE,
            "synthetic": True,
            "as_of": AS_OF,
            "timezone": "UTC",
            "currency": "USD",
            "license": "MIT",
            "provenance": "Creado desde cero; sin fuentes, marcas, personas ni sistemas reales.",
            "purpose": "Fixtures comerciales; no consejo clínico ni datos de Farmaenlace.",
            "runtime_integration": "not_loaded_by_existing_api",
        },
        "business_rules": {
            "quantity": {
                "type": "integer",
                "min": 1,
                "max": 10_000,
                "unit": "product.sell_unit",
                "split_packages": False,
            },
            "money": {
                "unit": "cent",
                "currency": "USD",
                "rounding": "half_up",
                "tax_model": "final_demo_price_no_additional_tax",
                "discount_order": "price_list_then_selected_promotions_by_priority",
                "round_per": "promotion_per_line",
            },
            "price_list": {
                "default": "general",
                "requires_active_membership": ["club", "alianza"],
                "fallback_on_expired_membership": "general",
                "selection": "explicit_customer_segment_not_spend_inference",
            },
            "validity": {"start_inclusive": True, "end_exclusive": True},
            "inventory": {
                "available_formula": "on_hand - reserved",
                "max_age_seconds": 900,
                "stale_policy": "refresh_before_promising_availability",
            },
            "reservation": {
                "proposal_ttl_seconds": 300,
                "hold_ttl_seconds": 3600,
                "requires_human_approval": True,
                "pickup_only": True,
                "recheck_stock_and_price": True,
                "automatic_retry_uncertain": False,
                "idempotency_scope": "actor_and_request_key",
                "provider_operation_key": "proposal_id",
            },
            "promotion": {
                "selection": "explicit_not_automatically_best_price",
                "combination": "all_pairs_must_allow_each_other",
                "minimum_subtotal_basis": "price_list_total_before_promotions",
                "buy_x_pay_y": "complete_groups_only_same_sku_sale_units",
                "max_discount": "remaining_line_total",
            },
            "customer": {
                "identity": "synthetic_customer_id_only",
                "history_authorization": "staff_customer_lookup_required_before_use",
                "clinical_inference": "forbidden",
            },
        },
        "categories": [
            {"category_id": key, "label": label}
            for key, label in [
                ("curacion", "Insumos de curación demo"),
                ("cabello", "Cuidado del cabello demo"),
                ("higiene", "Higiene demo"),
                ("oral", "Higiene oral demo"),
                ("cuidado_personal", "Cuidado personal demo"),
                ("accesorios", "Accesorios demo"),
            ]
        ],
        "branches": [
            {
                "branch_id": branch,
                "name": f"Sucursal demo {branch.title()}",
                "pickup_enabled": True,
                "source": SOURCE,
            }
            for branch in ["centro", "norte", "sur"]
        ],
        "products": [],
        "price_lists": [],
        "prices": [],
        "inventory": [],
        "customers": [],
        "purchases": [],
        "purchase_lines": [],
        "promotions": [],
        "reservation_proposals": [],
        "reservation_events": [],
        "scenarios": [],
    }
    for number, (name, category, presentation, unit, content, content_unit, _) in enumerate(
        CATALOG, 1
    ):
        data["products"].append(
            {
                "sku": f"DEMO-{number:03}",
                "name": name,
                "category_id": category,
                "presentation": presentation,
                "sell_unit": unit,
                "content_quantity": content,
                "content_unit": content_unit,
                "aliases": [name.removesuffix(" demo").lower()],
                "active": number != 30,
                "clinical_use": "not_provided",
                "source": SOURCE,
            }
        )
    for list_id, factor in [("general", 10_000), ("club", 9500), ("alianza", 9000)]:
        data["price_lists"].append(
            {
                "price_list_id": list_id,
                "label": f"Lista ficticia {list_id}",
                "retail_factor_basis_points": factor,
                "currency": "USD",
            }
        )
        for number, row in enumerate(CATALOG, 1):
            data["prices"].append(
                {
                    "price_list_id": list_id,
                    "sku": f"DEMO-{number:03}",
                    "unit_price_cents": round_basis_points(row[6], factor),
                    "currency": "USD",
                    "valid_from": START,
                    "valid_until": END,
                    "version": 1,
                    "updated_at": START,
                    "source": SOURCE,
                }
            )
    for number in range(1, 13):
        segment = ["club", "general", "alianza"][(number - 1) % 3]
        if number == 12:
            segment = "club"
        data["customers"].append(
            {
                "customer_id": f"DEMO-C{number:03}",
                "display_name": f"Cliente ficticio {number:03}",
                "segment": segment,
                "membership_status": "expired"
                if number == 12
                else ("none" if segment == "general" else "active"),
                "membership_valid_from": None if segment == "general" else START,
                "membership_valid_until": None
                if segment == "general"
                else ("2026-10-01T00:00:00Z" if number == 12 else END),
                "preferred_branch_id": ["centro", "norte", "sur"][(number - 1) % 3],
                "source": SOURCE,
            }
        )

    def promotion(
        identifier,
        title,
        skus,
        lists,
        rate,
        *,
        branches=None,
        start=None,
        end=None,
        quantity=1,
        minimum=0,
        compatible=None,
        priority=10,
        benefit=None,
    ):
        return {
            "promotion_id": identifier,
            "title": title,
            "sku_ids": skus,
            "price_list_ids": lists,
            "branch_ids": branches or ["centro", "norte", "sur"],
            "valid_from": start or "2026-10-01T00:00:00Z",
            "valid_until": end or END,
            "minimum_quantity": quantity,
            "minimum_subtotal_cents": minimum,
            "benefit": benefit or {"kind": "percent", "basis_points": rate},
            "combinable_with": compatible or [],
            "priority": priority,
            "requires_coupon": False,
            "source": SOURCE,
        }

    data["promotions"] = [
        promotion(
            "DEMO-P01",
            "Dos paquetes de gasas: 10% demo",
            ["DEMO-001"],
            ["general", "club"],
            1000,
            quantity=2,
            compatible=["DEMO-P02"],
        ),
        promotion(
            "DEMO-P02",
            "Gasas en Centro: 5% demo",
            ["DEMO-001"],
            ["general"],
            500,
            branches=["centro"],
            compatible=["DEMO-P01"],
            priority=20,
        ),
        promotion("DEMO-P03", "Shampoo club: 15% demo", ["DEMO-002", "DEMO-011"], ["club"], 1500),
        promotion(
            "DEMO-P04",
            "Jabón 3x2 demo",
            ["DEMO-003"],
            ["general", "club"],
            0,
            quantity=3,
            benefit={"kind": "buy_x_pay_y", "buy_quantity": 3, "pay_quantity": 2},
        ),
        promotion(
            "DEMO-P05",
            "Gasas: oferta vencida demo",
            ["DEMO-001"],
            ["general"],
            2000,
            end="2026-10-07T00:00:00Z",
        ),
        promotion(
            "DEMO-P06",
            "Gasas: oferta futura demo",
            ["DEMO-001"],
            ["general"],
            2500,
            start="2026-10-09T00:00:00Z",
        ),
        promotion("DEMO-P07", "Shampoo alianza: 8% demo", ["DEMO-002"], ["alianza"], 800),
        promotion(
            "DEMO-P08",
            "Gasas Norte: compra mínima demo",
            ["DEMO-001"],
            ["general"],
            1000,
            branches=["norte"],
            minimum=1000,
        ),
    ]
    prices = {(row["sku"], row["price_list_id"]): row["unit_price_cents"] for row in data["prices"]}
    for customer_number in range(1, 11):
        customer = data["customers"][customer_number - 1]
        for visit, date in enumerate(["2026-09-20", "2026-10-02", "2026-10-07"]):
            purchase_id = f"DEMO-S{(customer_number - 1) * 3 + visit + 1:03}"
            items = [
                (f"DEMO-{((customer_number + visit) % 28) + 1:03}", 1),
                (f"DEMO-{((customer_number + visit + 7) % 28) + 1:03}", 2),
            ]
            if customer_number == 1:
                items = [
                    [("DEMO-001", 2), ("DEMO-002", 1)],
                    [("DEMO-003", 3), ("DEMO-004", 1)],
                    [("DEMO-001", 1), ("DEMO-005", 1)],
                ][visit]
            lines = []
            for line_number, (sku, quantity) in enumerate(items, 1):
                unit_price = prices[sku, customer["segment"]]
                discount = (
                    unit_price if customer_number == 1 and visit == 1 and line_number == 1 else 0
                )
                line = {
                    "purchase_id": purchase_id,
                    "line_number": line_number,
                    "sku": sku,
                    "quantity": quantity,
                    "sell_unit": data["products"][int(sku[-3:]) - 1]["sell_unit"],
                    "unit_price_cents": unit_price,
                    "subtotal_cents": unit_price * quantity,
                    "discount_cents": discount,
                    "total_cents": unit_price * quantity - discount,
                    "promotion_ids": ["DEMO-P04"] if discount else [],
                }
                lines.append(line)
            data["purchase_lines"].extend(lines)
            data["purchases"].append(
                {
                    "purchase_id": purchase_id,
                    "customer_id": customer["customer_id"],
                    "branch_id": customer["preferred_branch_id"],
                    "purchased_at": f"{date}T12:00:00Z",
                    "price_list_id": customer["segment"],
                    "status": "completed",
                    "currency": "USD",
                    "subtotal_cents": sum(row["subtotal_cents"] for row in lines),
                    "discount_cents": sum(row["discount_cents"] for row in lines),
                    "total_cents": sum(row["total_cents"] for row in lines),
                    "source": SOURCE,
                }
            )

    for number, status in enumerate(
        [
            "pending",
            "executing",
            "executed",
            "rejected",
            "expired",
            "failed",
            "uncertain",
            "executed",
        ],
        1,
    ):
        sku, branch, quantity = (
            ("DEMO-003", "norte", 3) if number == 8 else ("DEMO-001", "centro", 2)
        )
        created = -600 if status == "expired" else -60
        proposal_id = f"DEMO-R{number:03}"
        total = prices[sku, "general"] * quantity
        events = [("proposed", created)]
        if status in {"executing", "executed", "failed", "uncertain"}:
            events.append(("approved", -30))
        if status not in {"pending", "executing"}:
            events.append((status, -20))
        data["reservation_proposals"].append(
            {
                "proposal_id": proposal_id,
                "customer_id": "DEMO-C002",
                "actor_id": "demo-clerk",
                "idempotency_key": f"fixture-{number:03}",
                "operation_id": proposal_id,
                "sku": sku,
                "branch_id": branch,
                "quantity": quantity,
                "price_list_id": "general",
                "unit_price_cents": prices[sku, "general"],
                "total_cents": total,
                "currency": "USD",
                "offer_version_at_quote": 1,
                "created_at": timestamp(created),
                "expires_at": timestamp(created + 300),
                "status": status,
                "conditions": {
                    "human_approval_required": True,
                    "pickup_branch_id": branch,
                    "hold_seconds_after_execution": 3600,
                    "partial_fulfillment": False,
                },
                "error_code": {
                    "failed": "offer_changed",
                    "uncertain": "provider_outcome_unknown",
                }.get(status),
                "receipt": {
                    "reservation_id": f"DEMO-H{number:03}",
                    "status": "held",
                    "held_quantity": quantity,
                    "hold_expires_at": timestamp(-20 + 3600),
                }
                if status == "executed"
                else None,
                "reconciliation_required": status in {"executing", "uncertain"},
                "source": SOURCE,
            }
        )
        data["reservation_events"].extend(
            {
                "proposal_id": proposal_id,
                "sequence": sequence,
                "kind": kind,
                "actor_id": "demo-clerk",
                "occurred_at": timestamp(offset),
            }
            for sequence, (kind, offset) in enumerate(events, 1)
        )

    for number in range(1, 31):
        sku = f"DEMO-{number:03}"
        for branch_number, branch in enumerate(["centro", "norte", "sur"]):
            on_hand = 8 + (number * 7 + branch_number * 5) % 25
            if number == 1:
                on_hand = [8, 20, 3][branch_number]
            if number == 2:
                on_hand = [0, 9, 3][branch_number]
            if number in {29, 30}:
                on_hand = 0
            reserved = sum(
                r["quantity"]
                for r in data["reservation_proposals"]
                if r["sku"] == sku and r["branch_id"] == branch and r["receipt"]
            )
            data["inventory"].append(
                {
                    "sku": sku,
                    "branch_id": branch,
                    "on_hand": on_hand,
                    "reserved": reserved,
                    "available": on_hand - reserved,
                    "version": 2 if reserved else 1,
                    "observed_at": timestamp(-86400 if (number == 10 and branch == "sur") else -10),
                    "source": SOURCE,
                }
            )
    data["scenarios"] = build_scenarios()
    return data


def build_scenarios() -> list[dict]:
    """Expected answers are literal, hand-calculated fixtures, not outputs of the generator math."""
    rows = [
        (
            "SEARCH-01",
            "product_search",
            "Busca DEMO-001",
            {"query": "DEMO-001"},
            {"sku_ids": ["DEMO-001"], "needs_clarification": False},
        ),
        (
            "SEARCH-02",
            "product_search",
            "Quiero gasas",
            {"query": "gasas"},
            {"sku_ids": ["DEMO-001", "DEMO-004"], "needs_clarification": True},
        ),
        (
            "SEARCH-03",
            "product_search",
            "Shampoo de 500 ml",
            {"query": "shampoo", "presentation": "500 ml"},
            {"sku_ids": ["DEMO-011"], "needs_clarification": False},
        ),
        (
            "SEARCH-04",
            "product_search",
            "Busca DEMO-999",
            {"query": "DEMO-999"},
            {"sku_ids": [], "needs_clarification": False},
        ),
        (
            "SEARCH-05",
            "product_search",
            "Busca el neceser retirado",
            {"query": "DEMO-030"},
            {"sku_ids": [], "needs_clarification": False, "reason": "inactive_product"},
        ),
        (
            "STOCK-01",
            "price_stock",
            "Dos shampoos de 250 ml, ¿dónde hay?",
            {"sku": "DEMO-002", "quantity": 2},
            {"eligible_branch_ids": ["norte", "sur"], "unavailable_branch_ids": ["centro"]},
        ),
        (
            "STOCK-02",
            "price_stock",
            "¿Cuántas gasas de 10 quedan en Centro?",
            {"sku": "DEMO-001", "branch_id": "centro"},
            {"on_hand": 8, "reserved": 2, "available": 6},
        ),
        (
            "STOCK-03",
            "price_stock",
            "¿Puedo prometer curitas en Sur?",
            {"sku": "DEMO-010", "branch_id": "sur"},
            {"refresh_required": True, "promise_stock": False},
        ),
        (
            "STOCK-04",
            "price_stock",
            "¿Hay guantes talla M?",
            {"sku": "DEMO-029", "quantity": 1},
            {"eligible_branch_ids": [], "unavailable_branch_ids": ["centro", "norte", "sur"]},
        ),
        (
            "PRICE-01",
            "price_stock",
            "Dos gasas de 10 a precio general",
            {"sku": "DEMO-001", "quantity": 2, "customer_id": "DEMO-C002"},
            {"price_list_id": "general", "unit_price_cents": 350, "total_cents": 700},
        ),
        (
            "PRICE-02",
            "price_stock",
            "Dos gasas de 10 para cliente club",
            {"sku": "DEMO-001", "quantity": 2, "customer_id": "DEMO-C001"},
            {"price_list_id": "club", "unit_price_cents": 333, "total_cents": 666},
        ),
        (
            "PRICE-03",
            "price_stock",
            "Shampoo para membresía vencida",
            {"sku": "DEMO-002", "quantity": 1, "customer_id": "DEMO-C012"},
            {"price_list_id": "general", "unit_price_cents": 625, "total_cents": 625},
        ),
        (
            "CLIENT-01",
            "customer_360",
            "Resumen del cliente ficticio 001",
            {"customer_id": "DEMO-C001"},
            {
                "purchase_count": 3,
                "total_spent_cents": 2933,
                "last_purchase_at": "2026-10-07T12:00:00Z",
                "repeated_sku_ids": ["DEMO-001"],
            },
        ),
        (
            "CLIENT-02",
            "customer_360",
            "Historial del cliente nuevo 011",
            {"customer_id": "DEMO-C011"},
            {
                "purchase_count": 0,
                "total_spent_cents": 0,
                "last_purchase_at": None,
                "repeated_sku_ids": [],
            },
        ),
        (
            "CLIENT-03",
            "customer_360",
            "Consulta un cliente inexistente",
            {"customer_id": "DEMO-C999"},
            {"error": "customer_not_found", "must_not_invent_history": True},
        ),
        (
            "PROMO-01",
            "promotion",
            "Combina las dos ofertas de gasas en Centro",
            {
                "sku": "DEMO-001",
                "quantity": 2,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P01", "DEMO-P02"],
            },
            {"subtotal_cents": 700, "discounts_cents": [70, 32], "total_cents": 598},
        ),
        (
            "PROMO-02",
            "promotion",
            "Shampoo de 250 ml con oferta club",
            {
                "sku": "DEMO-002",
                "quantity": 1,
                "branch_id": "norte",
                "price_list_id": "club",
                "promotion_ids": ["DEMO-P03"],
            },
            {"subtotal_cents": 594, "discounts_cents": [89], "total_cents": 505},
        ),
        (
            "PROMO-03",
            "promotion",
            "Tres jabones con 3x2",
            {
                "sku": "DEMO-003",
                "quantity": 3,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P04"],
            },
            {"subtotal_cents": 540, "discounts_cents": [180], "total_cents": 360},
        ),
        (
            "PROMO-04",
            "promotion",
            "¿Puedo combinar las ofertas de Norte?",
            {
                "sku": "DEMO-001",
                "quantity": 3,
                "branch_id": "norte",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P01", "DEMO-P08"],
            },
            {"error": "incompatible_promotions"},
        ),
        (
            "PROMO-05",
            "promotion",
            "Usa la oferta de gasas vencida",
            {
                "sku": "DEMO-001",
                "quantity": 2,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P05"],
            },
            {"error": "promotion_expired"},
        ),
        (
            "PROMO-06",
            "promotion",
            "Usa la oferta que empieza mañana",
            {
                "sku": "DEMO-001",
                "quantity": 2,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P06"],
            },
            {"error": "promotion_not_started"},
        ),
        (
            "PROMO-07",
            "promotion",
            "Aplica oferta de Norte en Centro",
            {
                "sku": "DEMO-001",
                "quantity": 3,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P08"],
            },
            {"error": "branch_ineligible"},
        ),
        (
            "PROMO-08",
            "promotion",
            "Dos gasas alcanzan el mínimo de Norte?",
            {
                "sku": "DEMO-001",
                "quantity": 2,
                "branch_id": "norte",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P08"],
            },
            {"error": "minimum_subtotal_not_met"},
        ),
        (
            "PROMO-09",
            "promotion",
            "Aplica descuento club a precio general",
            {
                "sku": "DEMO-002",
                "quantity": 1,
                "branch_id": "norte",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P03"],
            },
            {"error": "price_list_ineligible"},
        ),
        (
            "PROMO-10",
            "promotion",
            "Una gasa con oferta por cantidad",
            {
                "sku": "DEMO-001",
                "quantity": 1,
                "branch_id": "centro",
                "price_list_id": "general",
                "promotion_ids": ["DEMO-P01"],
            },
            {"error": "minimum_quantity_not_met"},
        ),
        (
            "PROMO-11",
            "promotion",
            "Shampoo alianza con oferta",
            {
                "sku": "DEMO-002",
                "quantity": 1,
                "branch_id": "norte",
                "price_list_id": "alianza",
                "promotion_ids": ["DEMO-P07"],
            },
            {"subtotal_cents": 563, "discounts_cents": [45], "total_cents": 518},
        ),
        (
            "RESERVE-01",
            "reservation",
            "Prepara siete gasas de 10 en Centro",
            {"sku": "DEMO-001", "branch_id": "centro", "quantity": 7},
            {"error": "insufficient_stock", "available": 6, "must_not_reserve": True},
        ),
        (
            "RESERVE-02",
            "reservation",
            "Prepara dos gasas de 10 en Centro",
            {"sku": "DEMO-001", "branch_id": "centro", "quantity": 2},
            {"can_propose": True, "human_approval_required": True, "stock_delta_on_propose": 0},
        ),
        (
            "RESERVE-03",
            "reservation",
            "Reintenta la operación incierta",
            {"proposal_id": "DEMO-R007", "decision": "approve"},
            {"status": "uncertain", "automatic_retry": False, "reconciliation_required": True},
        ),
        (
            "RESERVE-04",
            "reservation",
            "Consulta la reserva ya ejecutada",
            {"proposal_id": "DEMO-R003"},
            {"status": "executed", "reservation_id": "DEMO-H003", "held_quantity": 2},
        ),
        (
            "RESERVE-05",
            "reservation",
            "Confirma propuesta vencida",
            {"proposal_id": "DEMO-R005", "decision": "approve"},
            {"status": "expired", "must_not_reserve": True},
        ),
    ]
    return [
        {
            "scenario_id": key,
            "capability": capability,
            "question": question,
            "as_of": AS_OF,
            "input": request,
            "expected": expected,
        }
        for key, capability, question, request, expected in rows
    ]


def render_dataset(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    from mostrador.synthetic_checks import validate_dataset

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", type=Path, help="Validate a snapshot and verify reproducibility")
    group.add_argument("--output", type=Path, help="Export to a NEW file; refuses to overwrite")
    args = parser.parse_args()
    expected = build_dataset()
    data = json.loads(args.check.read_text(encoding="utf-8")) if args.check else expected
    validate_dataset(data)
    if args.check:
        if data != expected:
            parser.error(
                "Snapshot differs from generator; update source and regenerate intentionally"
            )
        print(
            f"OK: synthetic snapshot, {len(data['products'])} products, "
            f"{len(data['scenarios'])} scenarios; reproducible"
        )
    elif args.output:
        # Explicit CLI export only; never touches a database or overwrites a prior fixture.
        with args.output.open("x", encoding="utf-8") as target:
            target.write(render_dataset(data))
    else:
        print(render_dataset(data), end="")


if __name__ == "__main__":
    main()
