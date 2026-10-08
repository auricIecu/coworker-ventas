import pytest
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError
from fastapi.testclient import TestClient

from mostrador.backoffice_api import create_app
from mostrador.bedrock import BedrockInterpreter


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
        before = client.post("/workspace/analyze").json()
        assert before["analysis_status"] == "ready"
        burst = client.post("/workspace/demo/burst").json()
        assert burst["analysis_status"] == "sources_changed"
        assert len(burst["conversations"]) - len(before["conversations"]) == 6
        assert all(not r["approvable"] for r in burst["recommendations"])
        assert (
            client.post("/workspace/demo/burst").json()["source_revision"]
            == burst["source_revision"]
        )
        state = client.post("/workspace/analyze").json()
        proposal = next(
            r
            for r in state["recommendations"]
            if r["status"] == "pending"
            and r["sku"] == "SC-001"
            and r["branch_id"] == "gye-centro-demo"
        )
        assert proposal["evidence"]["recent_conversations"] == 8
        assert proposal["evidence"]["previous_conversations"] == 2
        assert proposal["evidence"]["available_units"] == 180
        assert proposal["evidence"]["replenishment_target_units"] == 680
        assert proposal["suggested_units"] == 500
        assert len(proposal["grounding"]["conversations"]) == 10
        assert {d["id"] for d in proposal["grounding"]["documents"]} == {
            "PROC-REPLENISH",
            "DOC-CAMPAIGN-GYE",
        }
        result = client.post(
            f"/workspace/recommendations/{proposal['id']}/decision", json={"decision": "approve"}
        )
        assert result.json()["status"] == "approved"
        assert result.json()["execution_status"] == "not_configured"
        assert (
            client.post(
                f"/workspace/recommendations/{proposal['id']}/decision",
                json={"decision": "approve"},
            ).status_code
            == 200
        )
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


@pytest.mark.parametrize("timeout", [ReadTimeoutError, ConnectTimeoutError])
def test_bedrock_timeout_returns_safe_503_and_allows_recovery(tmp_path, monkeypatch, timeout):
    monkeypatch.setenv("SALES_AI_MODE", "offline")
    app = create_app(demo=True, db_path=str(tmp_path / "timeout.sqlite"), scan_interval=0)
    workspace = app.state.sales_workspace

    class TimeoutClient:
        calls = 0

        def converse(self, **kwargs):
            self.calls += 1
            raise timeout(endpoint_url="https://private-endpoint.example")

    provider = TimeoutClient()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers["Authorization"] = "Bearer demo-encargado"
        original = workspace.interpreter
        before = client.post("/workspace/analyze").json()
        workspace.interpreter = BedrockInterpreter(client=provider)
        result = client.post("/workspace/analyze")
        assert result.status_code == 503
        assert result.json() == {"error": "bedrock_timeout"}
        assert provider.calls == 1
        assert workspace.state()["status"] == "analysis_failed"
        state = client.get("/workspace").json()
        assert state["mode"] == "bedrock"
        assert all(not r["approvable"] for r in state["recommendations"])
        assert len(state["recommendations"]) == len(before["recommendations"])
        # An explicit operator switch to offline can still finish the demo.
        workspace.interpreter = original
        recovered = client.post("/workspace/analyze").json()
        assert recovered["analysis_status"] == "ready"
        proposal = next(r for r in recovered["recommendations"] if r["approvable"])
        assert (
            client.post(
                f"/workspace/recommendations/{proposal['id']}/decision",
                json={"decision": "approve"},
            ).json()["status"]
            == "approved"
        )
