import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mostrador.backoffice import Reviewer, Snapshot, analyze, load_demo
from mostrador.backoffice_api import create_app
from mostrador.backoffice_store import RecommendationStore
from mostrador.domain import DomainError

OPERATOR = {"Authorization": "Bearer demo-encargado"}
REVIEWER = Reviewer("demo-encargado", "operator", ("gye-centro-demo",))
VIEWER = {"Authorization": "Bearer demo-viewer"}


def test_analysis_crosses_conversations_sales_stock_and_promotions():
    snapshot = load_demo()
    result = analyze(snapshot)
    assert {(r["sku"], r["kind"]) for r in result if r["branch_id"] == "gye-centro-demo"} == {
        ("SC-001", "replenish"),
        ("SC-002", "review_promotion"),
    }
    replenish = next(r for r in result if r["kind"] == "replenish")
    assert replenish["evidence"]["recent_conversations"] == 8
    assert replenish["evidence"]["previous_conversations"] == 2
    assert replenish["evidence"]["sold_units"] == 560
    assert replenish["evidence"]["available_units"] == 180
    assert replenish["evidence"]["stock_percent_of_reference"] == 18
    assert replenish["evidence"]["days_cover"] == 2.25
    assert replenish["suggested_units"] == 500
    assert replenish["promotion_plan"]["duration_days"] == 7
    assert (
        replenish["promotion_plan"]["activation_condition"] == "stock_replenished_and_revalidated"
    )
    assert replenish["evidence"]["active_promotion_ids"] == []
    # No recomendar impulsar demanda donde primero hace falta stock.
    assert not any(
        r["sku"] == "SC-001"
        and r["branch_id"] == "gye-centro-demo"
        and r["kind"] == "review_promotion"
        for r in result
    )


def test_repeated_messages_do_not_inflate_customer_interest():
    data = load_demo().model_dump()
    signal = next(s for s in data["signals"] if s["id"] == "sig-001")
    data["signals"].extend([{**signal, "id": f"repeat-{i}"} for i in range(20)])
    result = next(r for r in analyze(Snapshot.model_validate(data)) if r["sku"] == "SC-001")
    assert result["evidence"]["recent_conversations"] == 8


def test_no_baseline_does_not_claim_measured_growth():
    data = load_demo().model_dump()
    start = data["as_of"] - timedelta(days=7)
    data["signals"] = [s for s in data["signals"] if s["occurred_at"] >= start]
    result = analyze(Snapshot.model_validate(data))
    replenish = next(r for r in result if r["sku"] == "SC-001")
    assert replenish["kind"] == "replenish"
    assert replenish["suggested_units"] == 500
    assert replenish["promotion_plan"] is None
    assert next(r for r in result if r["sku"] == "SC-002")["kind"] == "review_demand"
    assert all(r["evidence"]["growth_ratio"] is None for r in result)


@pytest.mark.parametrize("days,available,expected", [(1, 150, 550), (3, 100, 134)])
def test_replenishment_uses_at_least_seven_days_of_sales(days, available, expected):
    data = load_demo().model_dump()
    data["window_days"] = days
    data["signals"] = []
    data["movements"] = [
        {
            **data["movements"][0],
            "occurred_at": data["as_of"] - timedelta(hours=12),
            "units": 100,
        }
    ]
    data["stock"][0].update(available_units=available, target_units=100)
    result = analyze(Snapshot.model_validate(data))
    assert len(result) == 1
    assert result[0]["kind"] == "replenish"
    assert result[0]["suggested_units"] == expected


def test_overlapping_scans_cannot_supersede_newer_evidence(tmp_path, monkeypatch):
    import mostrador.backoffice_api as api

    original = load_demo()
    data = original.model_dump()
    data["stock"][0]["available_units"] = 100
    changed = Snapshot.model_validate(data)
    current = [original]
    monkeypatch.setattr(api, "load_demo", lambda: current[0])
    with TestClient(create_app(db_path=str(tmp_path / "overlap.sqlite"), demo=True)) as client:
        reached_record, release, second_started = Event(), Event(), Event()
        record = RecommendationStore.record

        def delayed_record(store, source):
            if source.fingerprint() == original.fingerprint():
                reached_record.set()
                assert release.wait(5)
            return record(store, source)

        monkeypatch.setattr(RecommendationStore, "record", delayed_record)

        def second_scan():
            second_started.set()
            return client.post("/analysis/run", headers=OPERATOR)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, "/analysis/run", headers=OPERATOR)
            try:
                assert reached_record.wait(5)
                current[0] = changed
                second = pool.submit(second_scan)
                assert second_started.wait(5)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.2)
            finally:
                release.set()
            assert first.result(timeout=5).status_code == 200
            assert second.result(timeout=5).status_code == 200
        assert client.get("/health").json()["snapshot_id"] == changed.fingerprint()
        pending = [
            r
            for r in client.get("/recommendations", headers=OPERATOR).json()
            if r["status"] == "pending"
        ]
        assert len(pending) == 2
        assert all(r["snapshot_id"] == changed.fingerprint() for r in pending)


def test_stale_stock_blocks_commercial_advice():
    data = load_demo().model_dump()
    data["stock"][0]["observed_at"] -= timedelta(hours=2)
    result = [
        r
        for r in analyze(Snapshot.model_validate(data))
        if r["sku"] == "SC-001" and r["branch_id"] == "gye-centro-demo"
    ]
    assert len(result) == 1
    assert result[0]["kind"] == "refresh_data"
    assert result[0]["suggested_units"] is None


def test_expired_promotion_is_not_active():
    data = load_demo().model_dump()
    data["promotions"][0]["ends_at"] = data["as_of"]
    result = analyze(Snapshot.model_validate(data))
    assert any(r["sku"] == "SC-003" and r["kind"] == "review_promotion" for r in result)


def test_windows_are_non_overlapping_and_exclude_cutoff():
    data = load_demo().model_dump()
    prototype = next(s for s in data["signals"] if s["id"] == "sig-001")
    data["signals"].extend(
        [
            {
                **prototype,
                "id": "boundary-start",
                "conversation_id": "boundary-start",
                "occurred_at": data["as_of"] - timedelta(days=7),
            },
            {
                **prototype,
                "id": "boundary-end",
                "conversation_id": "boundary-end",
                "occurred_at": data["as_of"],
            },
        ]
    )
    result = next(r for r in analyze(Snapshot.model_validate(data)) if r["sku"] == "SC-001")
    assert result["evidence"]["recent_conversations"] == 9
    assert result["evidence"]["previous_conversations"] == 2


@pytest.mark.parametrize("change", ["negative_stock", "unknown_sku", "duplicate", "future", "real"])
def test_invalid_or_live_data_is_rejected(change):
    data = load_demo().model_dump()
    if change == "negative_stock":
        data["stock"][0]["available_units"] = -1
    elif change == "unknown_sku":
        data["signals"][0]["sku"] = "UNKNOWN"
    elif change == "duplicate":
        data["movements"].append(data["movements"][0])
    elif change == "future":
        data["signals"][0]["occurred_at"] = data["as_of"] + timedelta(seconds=1)
    else:
        data["synthetic"] = False
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)


def test_run_is_idempotent_and_approval_is_not_execution(tmp_path):
    snapshot = load_demo()
    store = RecommendationStore(str(tmp_path / "backoffice.sqlite"))
    first = store.record(snapshot)
    assert store.record(snapshot) == first
    assert all(item["status"] == "pending" for item in first)
    manager = REVIEWER
    recommendation = first[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: store.decide(recommendation["id"], "approve", manager, snapshot), range(4)
            )
        )
    assert all(
        r["status"] == "approved" and r["execution_status"] == "not_configured" for r in results
    )
    reopened = RecommendationStore(store.path)
    assert reopened.get(recommendation["id"], REVIEWER)["status"] == "approved"
    assert [e["kind"] for e in reopened.events(recommendation["id"], REVIEWER)] == [
        "proposed",
        "approved",
    ]
    with pytest.raises(DomainError, match="decision_conflict"):
        reopened.decide(recommendation["id"], "reject", manager, snapshot)


def test_new_evidence_requires_new_approval(tmp_path):
    snapshot = load_demo()
    store = RecommendationStore(str(tmp_path / "backoffice.sqlite"))
    pending = store.record(snapshot)[0]
    data = snapshot.model_dump()
    data["stock"][0]["available_units"] = 10
    changed = Snapshot.model_validate(data)
    with pytest.raises(DomainError, match="evidence_changed"):
        store.decide(pending["id"], "approve", REVIEWER, changed)
    store.record(changed)
    assert store.get(pending["id"], REVIEWER)["status"] == "superseded"
    assert all(r["status"] != "approved" for r in store.list(REVIEWER))


def test_expired_recommendations_cannot_be_approved(tmp_path):
    now = [1000]
    store = RecommendationStore(str(tmp_path / "backoffice.sqlite"), clock=lambda: now[0])
    snapshot = load_demo()
    pending = store.record(snapshot)[0]
    now[0] = 1900
    with pytest.raises(DomainError, match="recommendation_expired"):
        store.decide(pending["id"], "approve", REVIEWER, snapshot)


def test_api_permissions_review_journey_and_no_source_writes(tmp_path):
    source = tmp_path / "snapshot.json"
    original = load_demo().model_dump_json()
    source.write_text(original)
    app = create_app(db_path=str(tmp_path / "api.sqlite"), snapshot_path=source, demo=True)
    with TestClient(app) as client:
        assert client.get("/recommendations").status_code == 401
        assert client.post("/analysis/run", headers=VIEWER).status_code == 403
        run = client.post("/analysis/run", headers=OPERATOR)
        assert run.status_code == 200
        pending = client.get("/recommendations", headers=VIEWER).json()
        assert len(pending) == 2
        path = f"/recommendations/{pending[0]['id']}/decision"
        assert client.post(path, json={"decision": "approve"}, headers=VIEWER).status_code == 403
        assert (
            client.post(
                path, json={"decision": "approve", "role": "manager"}, headers=OPERATOR
            ).status_code
            == 422
        )
        approved = client.post(path, json={"decision": "approve"}, headers=OPERATOR).json()
        assert approved["status"] == "approved"
        assert approved["execution_status"] == "not_configured"
        second = f"/recommendations/{pending[1]['id']}/decision"
        assert (
            client.post(second, json={"decision": "reject"}, headers=OPERATOR).json()["status"]
            == "rejected"
        )
        assert (
            len(client.get(f"/recommendations/{pending[0]['id']}/events", headers=OPERATOR).json())
            == 2
        )
    assert source.read_text() == original


def test_invalid_snapshot_does_not_offer_old_evidence_as_current(tmp_path):
    source = tmp_path / "snapshot.json"
    source.write_text(load_demo().model_dump_json())
    with TestClient(
        create_app(db_path=str(tmp_path / "api.sqlite"), snapshot_path=source, demo=True)
    ) as client:
        pending = client.get("/recommendations", headers=OPERATOR).json()[0]
        source.write_text(json.dumps({"broken": True}))
        assert client.post("/analysis/run", headers=OPERATOR).status_code == 503
        assert (
            client.post(
                f"/recommendations/{pending['id']}/decision",
                json={"decision": "approve"},
                headers=OPERATOR,
            ).status_code
            == 503
        )


def test_demo_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("COPILOT_MODE", raising=False)
    with pytest.raises(RuntimeError, match="demo"):
        create_app(db_path=str(tmp_path / "api.sqlite"))


def test_scope_is_enforced_on_lists_details_events_and_decisions(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path / "scope.sqlite"), demo=True)) as client:
        jefe = {"Authorization": "Bearer demo-jefe-zona"}
        quito = {"Authorization": "Bearer demo-encargado-quito"}
        own = client.get("/recommendations", headers=OPERATOR).json()
        zone = client.get("/recommendations", headers=jefe).json()
        other = client.get("/recommendations", headers=quito).json()
        assert {r["branch_id"] for r in own} == {"gye-centro-demo"}
        assert {r["branch_id"] for r in zone} == {"gye-centro-demo", "gye-norte-demo"}
        assert {r["branch_id"] for r in other} == {"uio-demo"}
        run = client.post("/analysis/run", headers=OPERATOR).json()
        assert {r["branch_id"] for r in run["recommendations"]} == {"gye-centro-demo"}
        path = f"/recommendations/{other[0]['id']}"
        assert client.get(path, headers=OPERATOR).status_code == 404
        assert client.get(path + "/events", headers=jefe).status_code == 404
        assert (
            client.post(
                path + "/decision", headers=OPERATOR, json={"decision": "approve"}
            ).status_code
            == 404
        )
        assert (
            client.post(path + "/decision", headers=quito, json={"decision": "approve"}).status_code
            == 200
        )


def test_store_does_not_allow_direct_cross_branch_approval(tmp_path):
    store = RecommendationStore(str(tmp_path / "scope.sqlite"))
    snapshot = load_demo()
    foreign = next(r for r in store.record(snapshot) if r["branch_id"] == "uio-demo")
    with pytest.raises(DomainError, match="recommendation_not_found"):
        store.decide(foreign["id"], "approve", REVIEWER, snapshot)


def test_periodic_analysis_detects_new_snapshot_without_manual_request(tmp_path):
    import time

    source = tmp_path / "snapshot.json"
    original = load_demo()
    source.write_text(original.model_dump_json())
    app = create_app(
        db_path=str(tmp_path / "periodic.sqlite"), snapshot_path=source, demo=True, scan_interval=10
    )
    with TestClient(app) as client:
        old = client.get("/recommendations", headers=OPERATOR).json()
        data = original.model_dump()
        data["stock"][0]["available_units"] = 100
        changed = Snapshot.model_validate(data)
        source.write_text(changed.model_dump_json())
        deadline = time.monotonic() + 15
        while client.get("/health").json()["snapshot_id"] != changed.fingerprint():
            assert time.monotonic() < deadline, "Periodic analysis did not run"
            time.sleep(0.1)
        result = client.get("/recommendations", headers=OPERATOR).json()
        new = next(r for r in result if r["sku"] == "SC-001" and r["status"] == "pending")
        assert new["suggested_units"] == 580
        assert all(
            next(r for r in result if r["id"] == item["id"])["status"] == "superseded"
            for item in old
        )
