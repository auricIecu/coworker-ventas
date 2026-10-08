import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from mostrador.agents.auditor import Auditor, InsightStore
from mostrador.agents.profiler import CustomerProfiler
from mostrador.agents.stock_observer import StockObserver
from mostrador.agents_api import _load_historical, _load_operations
from mostrador.backoffice_api import create_app
from mostrador.domain import DomainError


def observation():
    data = _load_operations()
    data["movements"] += _load_historical()
    return StockObserver(data).run()


def test_agents_routes_auth_run_and_durable_decisions(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_AI_MODE", "offline")
    with TestClient(
        create_app(demo=True, db_path=str(tmp_path / "app.sqlite"), scan_interval=0)
    ) as c:
        assert c.post("/agents/run").status_code == 401
        c.headers["Authorization"] = "Bearer demo-viewer"
        assert c.post("/agents/run").status_code == 403
        c.headers["Authorization"] = "Bearer demo-jefe-zona"
        response = c.post("/agents/run")
        assert response.status_code == 200, response.text
        items = response.json()["insights"]
        assert items and all(r["branch_id"].startswith("gye-") for r in items)
        item = next(
            r for r in items if r["sku"] == "SC-001" and r["branch_id"] == "gye-centro-demo"
        )
        assert isinstance(item["expires_at"], int)
        url = f"/agents/insights/{item['id']}/decision"
        result = c.post(url, json={"decision": "approve"})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "executed"
        assert result.json()["execution"]["channel"] == "simulated_dashboard"
        assert c.post(url, json={"decision": "approve"}).status_code == 200
        events = c.get(f"/agents/insights/{item['id']}/events").json()
        assert [e["kind"] for e in events] == ["proposed", "approved", "executed"]
        rerun = c.post("/agents/run").json()["insights"]
        assert next(r for r in rerun if r["id"] == item["id"])["status"] == "executed"
        c.headers["Authorization"] = "Bearer demo-encargado-quito"
        assert c.get(f"/agents/insights/{item['id']}").status_code == 404
        assert c.post(url, json={"decision": "reject"}).status_code == 404
        assert c.get("/openapi.json").status_code == 200


def test_store_decision_does_not_open_nested_write_transaction(tmp_path):
    store = InsightStore(str(tmp_path / "insights.sqlite"))
    item = Auditor(store).run(observation(), [])[0]
    assert store.decide(item.id, "reject", "operator")["status"] == "rejected"
    assert store.decide(item.id, "reject", "operator")["status"] == "rejected"


def test_observer_default_date_is_timezone_aware():
    assert StockObserver({}).as_of.tzinfo is not None


def test_customer_with_only_purchases_keeps_profile_and_branch():
    profiles = CustomerProfiler(
        {
            "movements": [
                {
                    "customer_id": "buyer-only",
                    "kind": "sale",
                    "sku": "SC-001",
                    "units": 2,
                    "branch_id": "uio-demo",
                    "occurred_at": "2026-10-02T12:00:00Z",
                }
            ]
        }
    ).run()
    assert len(profiles) == 1
    assert profiles[0].branch_ids == ["uio-demo"]
    assert profiles[0].total_mentions == 0
    assert profiles[0].total_purchases == 2


def test_profile_revision_tracks_values_and_purchases_are_not_conversation_mentions():
    data = {
        "products": [{"sku": "SC-001", "title": "Demo"}],
        "conversations": [
            {
                "id": "c1",
                "customer_id": "anon",
                "branch_id": "gye-centro-demo",
                "channel": "web",
                "occurred_at": "2026-10-02T12:00:00Z",
                "signals": [{"sku": "SC-001"}],
            }
        ],
        "movements": [
            {
                "id": "s1",
                "customer_id": "anon",
                "sku": "SC-001",
                "kind": "sale",
                "units": 3,
                "occurred_at": "2026-10-03T12:00:00Z",
            }
        ],
    }
    old = CustomerProfiler(data).run()[0]
    assert old.total_mentions == 1
    assert old.total_purchases == 3
    data["movements"][0]["units"] = 4
    assert CustomerProfiler(data).run()[0].profile_revision != old.profile_revision


def test_changed_evidence_gets_new_insight_and_stale_pending_is_not_approvable(tmp_path):
    store = InsightStore(str(tmp_path / "insights.sqlite"))
    auditor = Auditor(store)
    initial = observation()
    old = auditor.run(initial, [])[0]
    changed = copy.deepcopy(initial)
    changed.signals[0] = replace(changed.signals[0], available_units=170)
    new = auditor.run(changed, [])[0]
    assert new.id != old.id
    with pytest.raises(DomainError):
        store.decide(old.id, "approve", "operator")


def test_existing_campaign_and_stale_stock_do_not_generate_new_campaign(tmp_path):
    auditor = Auditor(InsightStore(str(tmp_path / "insights.sqlite")))
    obs = observation()
    items = auditor.run(obs, [])
    assert not any(
        r.sku == "SC-003" and r.branch_id == "gye-centro-demo" and r.campaign_draft for r in items
    )
    for signal in obs.signals:
        signal.observed_at = "2026-10-01T14:00:00Z"
    assert auditor.run(obs, []) == []


def test_missing_inventory_invalidates_previous_pending_insights(tmp_path):
    store = InsightStore(str(tmp_path / "insights.sqlite"))
    auditor = Auditor(store)
    obs = observation()
    old = auditor.run(obs, [])[0]
    obs.signals = []
    assert auditor.run(obs, []) == []
    assert store.get(old.id)["status"] == "superseded"
    with pytest.raises(DomainError, match="decision_conflict"):
        store.decide(old.id, "approve", "operator")
