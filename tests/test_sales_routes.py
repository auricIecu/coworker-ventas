from fastapi.testclient import TestClient

from mostrador.backoffice_api import create_app


def test_workspace_http_journey_and_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_AI_MODE", "offline")
    app = create_app(demo=True, db_path=str(tmp_path / "api.sqlite"), scan_interval=0)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/workspace").status_code == 401
        client.headers["Authorization"] = "Bearer demo-viewer"
        assert client.post("/workspace/analyze").status_code == 403
        client.headers["Authorization"] = "Bearer demo-jefe-zona"
        assert client.get("/workspace").json()["analysis_status"] == "not_analyzed"
        assert client.post("/workspace/analyze").json()["analysis_status"] == "ready"
        assert client.post("/workspace/demo/burst").json()["analysis_status"] == "sources_changed"
        state = client.post("/workspace/analyze").json()
        proposal = next(r for r in state["recommendations"] if r["status"] == "pending")
        result = client.post(
            f"/workspace/recommendations/{proposal['id']}/decision", json={"decision": "approve"}
        )
        assert result.json()["status"] == "approved"
        assert len(client.get(f"/workspace/recommendations/{proposal['id']}/events").json()) == 2
        conversation = state["conversations"][0]
        assert client.post("/workspace/conversations", json=conversation).status_code == 422
        assert (
            client.post(
                "/workspace/conversations", json={**conversation, "synthetic": False}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/workspace/conversations", json={**conversation, "synthetic": True}
            ).status_code
            == 200
        )
        invalid = {
            **conversation,
            "synthetic": True,
            "id": "future",
            "occurred_at": "2099-01-01T00:00:00Z",
        }
        assert client.post("/workspace/conversations", json=invalid).status_code == 422
        client.headers["Authorization"] = "Bearer demo-encargado-quito"
        assert client.post("/workspace/demo/burst").status_code == 403
        assert client.get(f"/workspace/recommendations/{proposal['id']}/events").status_code == 404
