"""Validate the fixture's internal integrity, not external facts or production policy."""

from collections import Counter, defaultdict
from datetime import datetime


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer(value, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(
        result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
        f"Timestamp must be UTC: {value}",
    )
    return result


def unique(rows: list[dict], *fields: str) -> dict:
    result = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        require(key not in result, f"Duplicate key {fields}: {key}")
        result[key] = row
    return result


def validate_dataset(data: dict) -> None:
    require(data["metadata"]["synthetic"] is True, "Only synthetic data is supported")
    require(data["metadata"]["currency"] == "USD", "Fixture currency must be USD")
    now = instant(data["metadata"]["as_of"])
    products = {key[0]: row for key, row in unique(data["products"], "sku").items()}
    branches = {key[0]: row for key, row in unique(data["branches"], "branch_id").items()}
    categories = {key[0] for key in unique(data["categories"], "category_id")}
    customers = {key[0]: row for key, row in unique(data["customers"], "customer_id").items()}
    lists = {key[0]: row for key, row in unique(data["price_lists"], "price_list_id").items()}
    prices = unique(data["prices"], "sku", "price_list_id")
    inventory = unique(data["inventory"], "sku", "branch_id")
    purchases = {key[0]: row for key, row in unique(data["purchases"], "purchase_id").items()}
    promotions = {key[0]: row for key, row in unique(data["promotions"], "promotion_id").items()}
    proposals = {
        key[0]: row for key, row in unique(data["reservation_proposals"], "proposal_id").items()
    }
    unique(data["purchase_lines"], "purchase_id", "line_number")
    unique(data["reservation_events"], "proposal_id", "sequence")
    unique(data["reservation_proposals"], "actor_id", "idempotency_key")
    unique(data["scenarios"], "scenario_id")
    source = data["metadata"]["dataset_id"]
    for table in [
        "branches",
        "products",
        "prices",
        "inventory",
        "customers",
        "purchases",
        "promotions",
        "reservation_proposals",
    ]:
        require(
            all(row["source"] == source for row in data[table]), f"Unexpected source in {table}"
        )
    for sku, product in products.items():
        require(sku.startswith("DEMO-") and "demo" in product["name"].lower(), "Non-demo product")
        require(product["category_id"] in categories, "Unknown category")
        require(
            product["sell_unit"] and product["presentation"] and product["content_unit"],
            "Product missing commercial presentation",
        )
        require(integer(product["content_quantity"], 1), "Invalid package contents")
        require(type(product["active"]) is bool, "Invalid active flag")
        require(
            product["clinical_use"] == "not_provided", "Clinical advice is outside this fixture"
        )
    for price_list in lists.values():
        require(
            integer(price_list["retail_factor_basis_points"], 1)
            and price_list["retail_factor_basis_points"] <= 10_000,
            "Invalid price factor",
        )
    for (sku, list_id), price in prices.items():
        require(sku in products and list_id in lists, "Unknown price reference")
        require(integer(price["unit_price_cents"], 1), "Invalid price cents")
        require(
            price["currency"] == "USD" and integer(price["version"], 1), "Invalid price metadata"
        )
        require(instant(price["updated_at"]) <= now, "Future price update")
        require(
            instant(price["valid_from"]) <= now < instant(price["valid_until"]),
            "Price not valid at snapshot",
        )
    require(
        set(prices) == {(sku, list_id) for sku in products for list_id in lists},
        "Missing product/list prices",
    )
    for (sku, list_id), price in prices.items():
        general = prices[sku, "general"]["unit_price_cents"]
        factor = lists[list_id]["retail_factor_basis_points"]
        require(
            price["unit_price_cents"] == (general * factor + 5000) // 10_000,
            "Segment price does not match declared synthetic rule",
        )

    for customer_id, customer in customers.items():
        require(
            customer_id.startswith("DEMO-C")
            and customer["display_name"].startswith("Cliente ficticio"),
            "Non-demo customer",
        )
        require(
            not {"email", "phone", "address", "national_id", "diagnosis", "birth_date"}
            & customer.keys(),
            "Personal data fields are not part of the fixture",
        )
        require(
            customer["preferred_branch_id"] in branches and customer["segment"] in lists,
            "Unknown customer reference",
        )
        status = customer["membership_status"]
        if customer["segment"] == "general":
            require(
                status == "none"
                and customer["membership_valid_from"] is None
                and customer["membership_valid_until"] is None,
                "Invalid general membership",
            )
        else:
            start, end = (
                instant(customer["membership_valid_from"]),
                instant(customer["membership_valid_until"]),
            )
            require(start < end, "Invalid membership dates")
            require(
                (status == "active" and start <= now < end) or (status == "expired" and end <= now),
                "Membership state/date mismatch",
            )

    for promotion_id, promotion in promotions.items():
        require(
            set(promotion["sku_ids"]) <= products.keys() and promotion["sku_ids"],
            "Unknown promotion SKU",
        )
        require(
            set(promotion["branch_ids"]) <= branches.keys() and promotion["branch_ids"],
            "Unknown promotion branch",
        )
        require(
            set(promotion["price_list_ids"]) <= lists.keys() and promotion["price_list_ids"],
            "Unknown promotion list",
        )
        require(
            instant(promotion["valid_from"]) < instant(promotion["valid_until"]),
            "Invalid promotion dates",
        )
        require(
            integer(promotion["minimum_quantity"], 1)
            and integer(promotion["minimum_subtotal_cents"]),
            "Invalid promotion minimum",
        )
        benefit = promotion["benefit"]
        if benefit["kind"] == "percent":
            require(
                integer(benefit["basis_points"], 1) and benefit["basis_points"] <= 10_000,
                "Invalid discount rate",
            )
        else:
            require(benefit["kind"] == "buy_x_pay_y", "Unknown benefit")
            require(
                integer(benefit["pay_quantity"], 1)
                and integer(benefit["buy_quantity"], 2)
                and benefit["pay_quantity"] < benefit["buy_quantity"],
                "Invalid buy/pay quantities",
            )
        require(integer(promotion["priority"], 1), "Invalid promotion priority")
        for compatible in promotion["combinable_with"]:
            require(
                compatible in promotions and compatible != promotion_id,
                "Unknown compatible promotion",
            )
            require(
                promotion_id in promotions[compatible]["combinable_with"], "Asymmetric combination"
            )

    lines_by_purchase = defaultdict(list)
    for line in data["purchase_lines"]:
        require(
            line["purchase_id"] in purchases and line["sku"] in products,
            "Unknown purchase line reference",
        )
        require(
            integer(line["quantity"], 1) and line["quantity"] <= 10_000, "Invalid line quantity"
        )
        require(
            line["sell_unit"] == products[line["sku"]]["sell_unit"], "Sale/package unit mismatch"
        )
        require(
            all(
                integer(line[field])
                for field in ["unit_price_cents", "subtotal_cents", "discount_cents", "total_cents"]
            ),
            "Invalid line money",
        )
        purchase = purchases[line["purchase_id"]]
        require(purchase["price_list_id"] in lists, "Unknown purchase price list")
        price = prices[line["sku"], purchase["price_list_id"]]
        when = instant(purchase["purchased_at"])
        require(
            instant(price["valid_from"]) <= when < instant(price["valid_until"]),
            "Missing historical price",
        )
        require(
            line["unit_price_cents"] == price["unit_price_cents"], "Incorrect historical unit price"
        )
        require(
            line["subtotal_cents"] == line["unit_price_cents"] * line["quantity"],
            "Wrong line subtotal",
        )
        require(
            line["total_cents"] == line["subtotal_cents"] - line["discount_cents"],
            "Wrong line total",
        )
        selected = line["promotion_ids"]
        require(
            len(selected) == len(set(selected)) and set(selected) <= promotions.keys(),
            "Invalid line promotions",
        )
        remainder = line["subtotal_cents"]
        for promotion_id in sorted(selected, key=lambda key: promotions[key]["priority"]):
            promotion = promotions[promotion_id]
            require(
                instant(promotion["valid_from"]) <= when < instant(promotion["valid_until"]),
                "Inactive historical promotion",
            )
            require(
                line["sku"] in promotion["sku_ids"]
                and purchase["branch_id"] in promotion["branch_ids"]
                and purchase["price_list_id"] in promotion["price_list_ids"],
                "Ineligible historical promotion",
            )
            require(
                line["quantity"] >= promotion["minimum_quantity"]
                and line["subtotal_cents"] >= promotion["minimum_subtotal_cents"],
                "Promotion minimum not met",
            )
            require(
                set(selected) - {promotion_id} <= set(promotion["combinable_with"]),
                "Incompatible historical promotions",
            )
            benefit = promotion["benefit"]
            if benefit["kind"] == "percent":
                discount = (remainder * benefit["basis_points"] + 5000) // 10_000
            else:
                free_units = (line["quantity"] // benefit["buy_quantity"]) * (
                    benefit["buy_quantity"] - benefit["pay_quantity"]
                )
                discount = free_units * line["unit_price_cents"]
            remainder -= min(discount, remainder)
        require(remainder == line["total_cents"], "Discount does not match benefits")
        lines_by_purchase[line["purchase_id"]].append(line)
    for purchase_id, purchase in purchases.items():
        require(
            purchase["customer_id"] in customers and purchase["branch_id"] in branches,
            "Unknown purchase reference",
        )
        require(
            purchase["status"] == "completed" and purchase["currency"] == "USD",
            "Invalid historical purchase",
        )
        require(instant(purchase["purchased_at"]) <= now, "Purchase after snapshot")
        customer = customers[purchase["customer_id"]]
        list_id = customer["segment"]
        if list_id != "general":
            when = instant(purchase["purchased_at"])
            if (
                not instant(customer["membership_valid_from"])
                <= when
                < instant(customer["membership_valid_until"])
            ):
                list_id = "general"
        require(purchase["price_list_id"] == list_id, "Customer/list mismatch at time of purchase")
        lines = lines_by_purchase[purchase_id]
        require(bool(lines), "Purchase without lines")
        for field in ["subtotal_cents", "discount_cents", "total_cents"]:
            require(
                integer(purchase[field]) and purchase[field] == sum(line[field] for line in lines),
                "Wrong purchase total",
            )

    validate_reservations(data, products, branches, customers, proposals, prices, inventory, now)


def validate_reservations(data, products, branches, customers, proposals, prices, inventory, now):
    events = defaultdict(list)
    for event in data["reservation_events"]:
        require(event["proposal_id"] in proposals, "Event without proposal")
        events[event["proposal_id"]].append(event)
    held = Counter()
    hold_ids = set()
    for proposal_id, proposal in proposals.items():
        require(
            proposal["customer_id"] in customers
            and proposal["sku"] in products
            and proposal["branch_id"] in branches,
            "Unknown proposal reference",
        )
        require(
            integer(proposal["quantity"], 1) and proposal["quantity"] <= 10_000,
            "Invalid reservation quantity",
        )
        require(proposal["operation_id"] == proposal_id, "Unstable operation ID")
        require(
            proposal["currency"] == "USD" and integer(proposal["offer_version_at_quote"], 1),
            "Invalid proposal metadata",
        )
        price_key = (proposal["sku"], proposal["price_list_id"])
        require(
            price_key in prices
            and proposal["unit_price_cents"] == prices[price_key]["unit_price_cents"],
            "Invalid proposal price",
        )
        require(
            proposal["total_cents"] == proposal["quantity"] * proposal["unit_price_cents"],
            "Wrong proposal total",
        )
        created, expires = instant(proposal["created_at"]), instant(proposal["expires_at"])
        require(
            created <= now and (expires - created).total_seconds() == 300,
            "Invalid proposal timeline",
        )
        status = proposal["status"]
        expected = ["proposed"]
        if status in {"executing", "executed", "failed", "uncertain"}:
            expected.append("approved")
        if status not in {"pending", "executing"}:
            require(
                status in {"executed", "failed", "uncertain", "expired", "rejected"},
                "Unknown proposal status",
            )
            expected.append(status)
        ordered = sorted(events[proposal_id], key=lambda event: event["sequence"])
        require(
            [event["sequence"] for event in ordered] == list(range(1, len(expected) + 1)),
            "Invalid event sequence",
        )
        require([event["kind"] for event in ordered] == expected, "Events/status mismatch")
        times = [instant(event["occurred_at"]) for event in ordered]
        require(
            times == sorted(times) and times[0] == created and times[-1] <= now,
            "Invalid event times",
        )
        require(
            all(event["actor_id"] == proposal["actor_id"] for event in ordered),
            "Unknown fixture actor",
        )
        require(
            status != "pending" or now < expires, "Pending proposal already expired in snapshot"
        )
        require(status != "expired" or times[-1] >= expires, "Expired before deadline")
        require("approved" not in expected or times[1] < expires, "Approval after expiration")
        require(
            proposal["reconciliation_required"] == (status in {"uncertain", "executing"}),
            "Unsafe reconciliation flag",
        )
        require(
            proposal["error_code"]
            == {"failed": "offer_changed", "uncertain": "provider_outcome_unknown"}.get(status),
            "Error/status mismatch",
        )
        conditions = proposal["conditions"]
        require(
            conditions["human_approval_required"] is True
            and conditions["partial_fulfillment"] is False
            and conditions["pickup_branch_id"] == proposal["branch_id"]
            and conditions["hold_seconds_after_execution"] == 3600,
            "Invalid reservation conditions",
        )
        receipt = proposal["receipt"]
        if status == "executed":
            require(
                receipt is not None and receipt["status"] == "held",
                "Executed without confirmed hold",
            )
            require(receipt["held_quantity"] == proposal["quantity"], "Hold quantity mismatch")
            hold_expires = instant(receipt["hold_expires_at"])
            require(
                hold_expires > now and (hold_expires - times[-1]).total_seconds() == 3600,
                "Expired/invalid active hold",
            )
            require(receipt["reservation_id"] not in hold_ids, "Duplicate reservation receipt")
            hold_ids.add(receipt["reservation_id"])
            held[proposal["sku"], proposal["branch_id"]] += proposal["quantity"]
        else:
            require(receipt is None, "Unconfirmed action must not have a fabricated receipt")
    require(
        set(inventory) == {(sku, branch) for sku in products for branch in branches},
        "Missing inventory rows",
    )
    for key, stock in inventory.items():
        require(key[0] in products and key[1] in branches, "Unknown stock reference")
        require(
            all(integer(stock[field]) for field in ["on_hand", "reserved", "available"]),
            "Invalid stock count",
        )
        require(
            stock["available"] == stock["on_hand"] - stock["reserved"], "Stock does not reconcile"
        )
        require(stock["reserved"] == held[key], "Reserved stock does not match confirmed holds")
        require(
            integer(stock["version"], 1) and instant(stock["observed_at"]) <= now,
            "Invalid stock metadata",
        )
