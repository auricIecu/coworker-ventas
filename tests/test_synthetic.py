import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from mostrador.synthetic import build_dataset, render_dataset
from mostrador.synthetic_checks import validate_dataset


def test_snapshot_is_reproducible_and_matches_committed_json():
    data = build_dataset()
    assert data == build_dataset()
    assert json.loads(Path("data/synthetic/dataset.json").read_text()) == data
    assert render_dataset(data).endswith("\n")
    assert data["metadata"]["synthetic"] is True
    assert data["metadata"]["as_of"] == "2026-10-08T14:00:00Z"


def test_all_five_workflows_have_data_and_related_records():
    data = build_dataset()
    validate_dataset(data)
    assert len(data["products"]) == 30
    assert len(data["branches"]) == 3
    assert len(data["price_lists"]) == 3
    assert len(data["prices"]) == 90
    assert len(data["inventory"]) == 90
    assert len(data["customers"]) == 12
    assert len(data["purchases"]) == 30
    assert len(data["purchase_lines"]) == 60
    assert len(data["promotions"]) == 8
    assert {row["status"] for row in data["reservation_proposals"]} == {
        "pending",
        "executing",
        "executed",
        "rejected",
        "expired",
        "failed",
        "uncertain",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_sku",
        "unknown_branch",
        "negative_stock",
        "wrong_available",
        "wrong_total",
        "invalid_customer",
        "invalid_price",
        "invalid_quantity",
        "expired_active_hold",
        "incompatible_symmetry",
        "invalid_timeline",
    ],
)
def test_validator_rejects_corrupted_data(mutation):
    data = deepcopy(build_dataset())
    if mutation == "duplicate_sku":
        data["products"][1]["sku"] = data["products"][0]["sku"]
    elif mutation == "unknown_branch":
        data["inventory"][0]["branch_id"] = "does-not-exist"
    elif mutation == "negative_stock":
        data["inventory"][0]["on_hand"] = -1
    elif mutation == "wrong_available":
        data["inventory"][0]["available"] += 1
    elif mutation == "wrong_total":
        data["purchases"][0]["total_cents"] += 1
    elif mutation == "invalid_customer":
        data["purchases"][0]["customer_id"] = "real-person"
    elif mutation == "invalid_price":
        data["prices"][0]["unit_price_cents"] = 3.5
    elif mutation == "invalid_quantity":
        data["purchase_lines"][0]["quantity"] = True
    elif mutation == "expired_active_hold":
        data["reservation_proposals"][2]["receipt"]["hold_expires_at"] = "2026-10-07T14:00:00Z"
    elif mutation == "incompatible_symmetry":
        data["promotions"][0]["combinable_with"] = []
    elif mutation == "invalid_timeline":
        data["reservation_proposals"][0]["expires_at"] = "2026-10-07T14:00:00Z"
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_customer_history_has_a_known_total_and_no_history_is_not_an_error():
    data = build_dataset()
    purchases = [p for p in data["purchases"] if p["customer_id"] == "DEMO-C001"]
    assert len(purchases) == 3
    assert sum(p["total_cents"] for p in purchases) == 2933
    assert not [p for p in data["purchases"] if p["customer_id"] == "DEMO-C011"]


def test_golden_scenarios_cover_requested_capabilities():
    data = build_dataset()
    assert {s["capability"] for s in data["scenarios"]} == {
        "product_search",
        "price_stock",
        "reservation",
        "customer_360",
        "promotion",
    }
    assert len(data["scenarios"]) >= 20
    assert all(s["input"] and s["expected"] and s["question"] for s in data["scenarios"])


def test_cli_exports_validates_and_refuses_to_overwrite(tmp_path):
    output = tmp_path / "dataset.json"
    cmd = [sys.executable, "-m", "mostrador.synthetic"]
    exported = subprocess.run([*cmd, "--output", str(output)], capture_output=True, text=True)
    assert exported.returncode == 0, exported.stderr
    checked = subprocess.run([*cmd, "--check", str(output)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert "31 scenarios" in checked.stdout
    before = output.read_bytes()
    repeated = subprocess.run([*cmd, "--output", str(output)], capture_output=True, text=True)
    assert repeated.returncode != 0
    assert output.read_bytes() == before


def test_existing_api_seed_is_not_replaced_by_dataset(tmp_path):
    from mostrador.bootstrap import demo_adapters

    adapters = demo_adapters(str(tmp_path / "unchanged.sqlite"))
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8
    snapshot = next(
        row
        for row in build_dataset()["inventory"]
        if row["sku"] == "DEMO-001" and row["branch_id"] == "centro"
    )
    assert snapshot["available"] == 6
