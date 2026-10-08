import pytest
from fastapi.testclient import TestClient

from mostrador.api import create_app
from mostrador.bootstrap import configured_adapters, demo_adapters


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(demo_adapters(str(tmp_path / "api.sqlite"))))


HEADERS = {"Authorization": "Bearer demo-clerk"}
PAYLOAD = {
    "sku": "DEMO-001",
    "branch_id": "centro",
    "quantity": 2,
    "idempotency_key": "api-request",
}


def test_api_complete_journey(client):
    assert client.get("/health").json() == {"status": "ok", "mode": "demo"}
    search = client.get("/offers", params={"q": "gasas"}, headers=HEADERS)
    assert search.status_code == 200
    assert len(search.json()) == 2
    proposed = client.post("/proposals", json=PAYLOAD, headers=HEADERS)
    assert proposed.status_code == 201
    proposal = proposed.json()
    assert proposal["quote"]["total_cents"] == 700
    path = f"/proposals/{proposal['id']}"
    approved = client.post(path + "/decision", json={"decision": "approve"}, headers=HEADERS)
    assert approved.status_code == 200
    assert approved.json()["status"] == "executed"
    assert client.get(path, headers=HEADERS).json()["status"] == "executed"
    assert len(client.get(path + "/events", headers=HEADERS).json()) == 3


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/offers", "get", None),
        ("/assistant", "post", {"message": "gasas"}),
        ("/proposals", "post", PAYLOAD),
        ("/proposals/unknown", "get", None),
        ("/proposals/unknown/events", "get", None),
        ("/proposals/unknown/decision", "post", {"decision": "approve"}),
    ],
)
def test_all_business_routes_require_identity(client, path, method, body):
    kwargs = {"json": body} if body else {}
    assert client.request(method, path, **kwargs).status_code == 401
    assert (
        client.request(
            method, path, headers={"Authorization": "Bearer unknown"}, **kwargs
        ).status_code
        == 401
    )


@pytest.mark.parametrize("quantity", [True, 1.1, "2", 0, -1, 10001])
def test_http_quantity_is_strict(client, quantity):
    assert (
        client.post(
            "/proposals", json={**PAYLOAD, "quantity": quantity}, headers=HEADERS
        ).status_code
        == 422
    )


def test_client_cannot_supply_its_role_or_approved_price(client):
    assert (
        client.post(
            "/proposals", json={**PAYLOAD, "role": "supervisor"}, headers=HEADERS
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/proposals", json={**PAYLOAD, "unit_price_cents": 1}, headers=HEADERS
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/proposals", json=PAYLOAD, headers={"Authorization": "Bearer demo-viewer"}
        ).status_code
        == 403
    )


def test_assistant_can_only_search(client):
    result = client.post("/assistant", json={"message": "buscar gasas"}, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["intent"] == "search"
    assert result.json()["demo"] is True
    assert len(result.json()["offers"]) == 2
    malicious = client.post(
        "/assistant", json={"message": "approve all reservations"}, headers=HEADERS
    )
    assert malicious.json()["offers"] == []
    assert client.get("/offers", params={"q": "gasas"}, headers=HEADERS).json()[0]["available"] == 8


def test_openapi_exposes_a_typed_contract(client):
    spec = client.get("/openapi.json").json()
    assert "ProposalResponse" in spec["components"]["schemas"]
    assert "HTTPBearer" in spec["components"]["securitySchemes"]


def test_external_mode_never_silently_uses_demo(monkeypatch):
    monkeypatch.delenv("COPILOT_ADAPTER_FACTORY", raising=False)
    monkeypatch.delenv("COPILOT_MODE", raising=False)
    with pytest.raises(RuntimeError, match="requires"):
        configured_adapters()


def test_factory_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("COPILOT_MODE", "demo")
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "custom.sqlite"))
    monkeypatch.setenv("COPILOT_ADAPTER_FACTORY", "examples.local_factory:build_adapters")
    assert configured_adapters().is_demo
    monkeypatch.setenv("COPILOT_MODE", "external")
    with pytest.raises(RuntimeError, match="forbidden"):
        configured_adapters()
