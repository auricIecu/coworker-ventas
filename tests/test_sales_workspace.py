import json

import pytest

from mostrador.backoffice import Reviewer
from mostrador.bedrock import BedrockInterpreter
from mostrador.domain import DomainError
from mostrador.sales_context import load_sources
from mostrador.sales_workspace import OfflineInterpreter, SalesWorkspace, validate_interpretations

ACTOR = Reviewer("demo-jefe-zona", "operator", ("gye-centro-demo", "gye-norte-demo"))
QUITO = Reviewer("demo-encargado-quito", "operator", ("uio-demo",))


class InvalidThenValidClient:
    def __init__(self, invalid_count, kind):
        self.invalid_count, self.kind = invalid_count, kind
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        payload = json.loads(kwargs["messages"][0]["content"][0]["text"])
        reply = OfflineInterpreter().infer(payload)
        text = json.dumps(reply)
        if self.calls <= self.invalid_count:
            if self.kind == "json":
                text = "not JSON"
            elif self.kind == "references":
                reply["items"][0]["document_ids"] = ["invented-document"]
                text = json.dumps(reply)
        return {
            "stopReason": "end_turn",
            "output": {"message": {"content": [{"text": text}]}},
        }


@pytest.mark.parametrize("kind", ["json", "references"])
def test_invalid_bedrock_batch_gets_one_retry_before_caching(tmp_path, kind):
    client = InvalidThenValidClient(1, kind)
    interpreter = BedrockInterpreter(client=client, sleep=lambda _: None)
    ws = SalesWorkspace(str(tmp_path / "retry.sqlite"), interpreter=interpreter)
    result = ws.run(ACTOR)
    assert result["analysis_status"] == "ready"
    assert result["last_run"]["model_calls"] == 6  # Five batches plus one retry.
    proposal = next(r for r in result["recommendations"] if r["sku"] == "SC-001")
    assert proposal["suggested_units"] == 500
    assert ws.run(ACTOR)["last_run"]["model_calls"] == 0
    assert client.calls == 6


@pytest.mark.parametrize("kind", ["json", "references"])
def test_two_invalid_bedrock_replies_stop_without_caching_or_fallback(tmp_path, kind):
    client = InvalidThenValidClient(2, kind)
    interpreter = BedrockInterpreter(client=client, sleep=lambda _: None)
    ws = SalesWorkspace(str(tmp_path / "invalid.sqlite"), interpreter=interpreter)
    with pytest.raises(DomainError, match="^model_invalid_response$"):
        ws.run(ACTOR)
    assert client.calls == 2
    assert ws.view(ACTOR)["recommendations"] == []
    assert ws.view(ACTOR)["mode"] == "bedrock"
    assert ws.state()["status"] == "analysis_failed"
    with ws.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM interpretation_cache").fetchone()[0] == 0
    assert ws.run(ACTOR)["analysis_status"] == "ready"


@pytest.mark.parametrize("code", ["bedrock_unavailable", "aws_session_expired"])
def test_bedrock_service_errors_are_not_retried(tmp_path, code):
    class UnavailableInterpreter:
        mode, model_id, calls = "bedrock", "test-model", 0

        def infer(self, payload):
            self.calls += 1
            raise DomainError(code, 503)

    interpreter = UnavailableInterpreter()
    ws = SalesWorkspace(str(tmp_path / "unavailable.sqlite"), interpreter=interpreter)
    with pytest.raises(DomainError, match=f"^{code}$"):
        ws.run(ACTOR)
    assert interpreter.calls == 1


def test_conversations_to_grounded_recommendations_and_human_decision(tmp_path):
    ws = SalesWorkspace(str(tmp_path / "workspace.sqlite"), interpreter=OfflineInterpreter())
    assert ws.view(ACTOR)["analysis_status"] == "not_analyzed"
    before = ws.run(ACTOR)
    item = next(
        r
        for r in before["recommendations"]
        if r["sku"] == "SC-001" and r["branch_id"] == "gye-centro-demo"
    )
    assert item["evidence"]["recent_conversations"] == 2
    assert item["suggested_units"] == 500
    assert item["promotion_plan"] is None
    old_id = item["id"]
    ws.add_burst(ACTOR)
    with pytest.raises(DomainError, match="evidence_changed"):
        ws.decide(old_id, "approve", ACTOR)
    after = ws.run(ACTOR)
    pending = [r for r in after["recommendations"] if r["status"] == "pending"]
    item = next(r for r in pending if r["sku"] == "SC-001" and r["branch_id"] == "gye-centro-demo")
    assert item["evidence"]["recent_conversations"] == 8
    assert item["evidence"]["sold_units"] == 560
    assert item["suggested_units"] == 500
    assert item["promotion_plan"]["duration_days"] == 7
    assert {d["id"] for d in item["grounding"]["documents"]} == {
        "PROC-REPLENISH",
        "DOC-CAMPAIGN-GYE",
    }
    assert len(item["grounding"]["conversations"]) == 10
    assert item["grounding"]["missing_information"]
    assert item["grounding"]["required_approvals"]
    approved = ws.decide(item["id"], "approve", ACTOR)
    assert approved["status"] == "approved"
    assert approved["execution_status"] == "not_configured"
    assert ws.decide(item["id"], "approve", ACTOR)["status"] == "approved"
    assert len(ws.events(item["id"], ACTOR)) == 2
    assert ws.add_burst(ACTOR)["source_revision"] == after["source_revision"]


def test_scope_and_ambiguity_are_preserved(tmp_path):
    ws = SalesWorkspace(str(tmp_path / "workspace.sqlite"), interpreter=OfflineInterpreter())
    data = ws.run(ACTOR)
    bad = {i["conversation_id"]: i for i in data["interpretations"] if i["status"] != "matched"}
    assert bad["c-037"]["status"] == "ambiguous"
    assert bad["c-039"]["status"] == "ambiguous"
    assert bad["c-040"]["status"] == "irrelevant"
    assert all(c["branch_id"] in ACTOR.branches for c in data["conversations"])
    foreign = ws.view(QUITO)["recommendations"][0]
    assert foreign["promotion_plan"]["duration_days"] == 3
    with pytest.raises(DomainError, match="recommendation_not_found"):
        ws.decide(foreign["id"], "approve", ACTOR)


def test_repeated_analysis_uses_persistent_cache_and_document_change_invalidates_it(tmp_path):
    class CountingInterpreter(OfflineInterpreter):
        def __init__(self):
            self.calls = 0

        def infer(self, payload):
            self.calls += 1
            return super().infer(payload)

    model = CountingInterpreter()
    sources = load_sources()
    path = str(tmp_path / "workspace.sqlite")
    ws = SalesWorkspace(path, interpreter=model, sources=sources)
    ws.run(ACTOR)
    count = model.calls
    reopened = SalesWorkspace(path, interpreter=model, sources=sources)
    result = reopened.run(ACTOR)
    assert model.calls == count
    assert result["last_run"]["model_calls"] == 0
    sources.documents[0].body += " Revisar las condiciones actualizadas."
    reopened.run(ACTOR)
    assert model.calls > count


def test_invalid_model_ids_and_cross_branch_documents_fail_closed():
    sources = load_sources()
    conv = sources.conversations[:1]
    for mutation in ("sku", "doc", "duplicate", "missing"):
        item = {
            "conversation_id": conv[0].id,
            "status": "matched",
            "sku": "SC-001",
            "branch_id": "gye-centro-demo",
            "reason": "Consulta explícita",
            "document_ids": ["PROC-REPLENISH"],
        }
        if mutation == "sku":
            item["sku"] = "invented"
        if mutation == "doc":
            item["document_ids"] = ["DOC-CAMPAIGN-UIO"]
        rows = [] if mutation == "missing" else [item, item] if mutation == "duplicate" else [item]
        with pytest.raises(DomainError, match="model_invalid_response"):
            validate_interpretations({"items": rows}, conv, sources)


def test_abstention_discards_model_attributions_and_never_creates_a_signal():
    sources = load_sources()
    conv = sources.conversations[:1]
    row = {
        "conversation_id": conv[0].id,
        "status": "ambiguous",
        "sku": "SC-001",
        "branch_id": "uio-demo",
        "reason": "Falta presentación",
        "document_ids": ["invented"],
    }
    result = validate_interpretations({"items": [row]}, conv, sources)[0]
    assert result.status == "ambiguous"
    assert result.sku is None and result.branch_id is None and result.document_ids == []


def test_missing_document_blocks_promotion_and_expired_document_cannot_replace_it(tmp_path):
    sources = load_sources()
    sources.documents = [
        d for d in sources.documents if d.kind == "procedure" or d.id == "DOC-EXPIRED-SC001"
    ]
    ws = SalesWorkspace(
        str(tmp_path / "workspace.sqlite"), interpreter=OfflineInterpreter(), sources=sources
    )
    data = ws.run(ACTOR)
    promo = next(r for r in data["recommendations"] if r["sku"] == "SC-002")
    assert promo["approvable"] is False
    assert promo["grounding"]["blockers"]
    with pytest.raises(DomainError, match="missing_required_context"):
        ws.decide(promo["id"], "approve", ACTOR)
    assert ws.decide(promo["id"], "reject", ACTOR)["status"] == "rejected"


def test_successful_reanalysis_renews_expired_pending_but_never_decided_proposals(tmp_path):
    ws = SalesWorkspace(str(tmp_path / "workspace.sqlite"), interpreter=OfflineInterpreter())
    now = [2_000_000_000]
    ws.store.clock = lambda: now[0]
    initial = ws.run(ACTOR)["recommendations"]
    approved = initial[0]
    ws.decide(approved["id"], "approve", ACTOR)
    now[0] += 901
    with pytest.raises(DomainError, match="recommendation_expired"):
        ws.decide(initial[1]["id"], "approve", ACTOR)
    ws.run(ACTOR)
    assert ws.decide(initial[1]["id"], "approve", ACTOR)["status"] == "approved"
    assert [e["kind"] for e in ws.events(initial[1]["id"], ACTOR)] == [
        "proposed",
        "revalidated",
        "approved",
    ]
    assert len(ws.events(approved["id"], ACTOR)) == 2


def test_provider_failure_blocks_approval_and_does_not_fallback(tmp_path):
    model = OfflineInterpreter()
    ws = SalesWorkspace(str(tmp_path / "workspace.sqlite"), interpreter=model)
    item = ws.run(ACTOR)["recommendations"][0]
    assert ws.state()["last_run"]["model_calls"] == 0
    # Invalidate interpretation cache without changing source revision.
    with ws.store.connect() as db:
        db.execute("DELETE FROM interpretation_cache")

    def fail(payload):
        raise DomainError("bedrock_unavailable", 503)

    model.infer = fail
    with pytest.raises(DomainError, match="bedrock_unavailable"):
        ws.run(ACTOR)
    assert ws.view(ACTOR)["analysis_status"] == "analysis_failed"
    assert all(not r["approvable"] for r in ws.view(ACTOR)["recommendations"])
    with pytest.raises(DomainError, match="analysis_required"):
        ws.decide(item["id"], "approve", ACTOR)
