from concurrent.futures import ThreadPoolExecutor

import pytest

from mostrador.bootstrap import demo_adapters
from mostrador.domain import Actor, DomainError
from mostrador.service import Copilot


@pytest.fixture
def setup(tmp_path):
    adapters = demo_adapters(str(tmp_path / "demo.sqlite"))
    clock = [1_800_000_000]
    service = Copilot(adapters, clock=lambda: clock[0])
    return service, adapters, clock


CLERK = Actor("clerk-a", "clerk")
OTHER = Actor("clerk-b", "clerk")
SUPERVISOR = Actor("supervisor", "supervisor")
VIEWER = Actor("viewer", "viewer")


def prepare(service, actor=CLERK, key="request-one", quantity=2):
    return service.propose(actor, "DEMO-001", "centro", quantity, key)


def test_prepare_does_not_reserve_and_approval_is_idempotent(setup):
    service, adapters, _ = setup
    proposal = prepare(service)
    assert proposal.status == "pending"
    assert proposal.quote.total_cents == 700
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8
    result = service.decide(CLERK, proposal.id, "approve")
    assert result.status == "executed"
    assert result.receipt["reservation_id"]
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 6
    assert service.decide(CLERK, proposal.id, "approve").receipt == result.receipt
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 6
    assert [e["kind"] for e in service.events(CLERK, proposal.id)] == [
        "proposed",
        "approved",
        "executed",
    ]


def test_reject_never_reserves(setup):
    service, adapters, _ = setup
    result = service.decide(CLERK, prepare(service).id, "reject")
    assert result.status == "rejected"
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8
    with pytest.raises(DomainError):
        service.decide(CLERK, result.id, "approve")


def test_stock_changed_after_preview_refuses_the_old_proposal(setup):
    service, adapters, _ = setup
    old = prepare(service)
    newer = prepare(service, key="other-request", quantity=1)
    service.decide(CLERK, newer.id, "approve")
    result = service.decide(CLERK, old.id, "approve")
    assert result.status == "failed"
    assert result.error_code == "offer_changed"
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 7


def test_identity_and_ownership_are_enforced(setup):
    service, _, _ = setup
    with pytest.raises(DomainError, match="permission"):
        prepare(service, VIEWER)
    proposal = prepare(service)
    with pytest.raises(DomainError, match="permission"):
        service.decide(OTHER, proposal.id, "approve")
    with pytest.raises(DomainError, match="permission"):
        service.events(OTHER, proposal.id)
    assert service.decide(SUPERVISOR, proposal.id, "approve").status == "executed"


def test_expired_proposal_cannot_reserve(setup):
    service, adapters, clock = setup
    proposal = prepare(service)
    clock[0] += 300
    assert service.decide(CLERK, proposal.id, "approve").status == "expired"
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8


def test_idempotency_key_cannot_change_the_approved_payload(setup):
    service, _, _ = setup
    proposal = prepare(service)
    assert prepare(service).id == proposal.id
    with pytest.raises(DomainError, match="idempotency"):
        prepare(service, quantity=3)
    assert prepare(service, OTHER).id != proposal.id


def test_concurrent_approval_dispatches_one_reservation(setup):
    service, adapters, _ = setup
    proposal = prepare(service)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.decide(CLERK, proposal.id, "approve"), range(4)))
    assert all(r.status in {"executing", "executed"} for r in results)
    assert service.get(CLERK, proposal.id).status == "executed"
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 6
    assert len([e for e in service.events(CLERK, proposal.id) if e["kind"] == "approved"]) == 1


def test_unknown_provider_result_is_not_retried(setup):
    service, adapters, _ = setup
    proposal = prepare(service)
    original = adapters.commerce.reserve

    def lost_response(quote, operation_id):
        original(quote, operation_id)
        raise TimeoutError("private upstream detail must not reach the API")

    adapters.commerce.reserve = lost_response
    result = service.decide(CLERK, proposal.id, "approve")
    assert result.status == "uncertain"
    assert result.error_code == "provider_outcome_unknown"
    assert service.decide(CLERK, proposal.id, "approve").status == "uncertain"
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 6


def test_workflow_survives_a_new_service_instance(setup):
    service, adapters, clock = setup
    proposal = prepare(service)
    restored = Copilot(demo_adapters(adapters.store.path), clock=lambda: clock[0])
    assert restored.get(CLERK, proposal.id).status == "pending"
    assert restored.decide(CLERK, proposal.id, "approve").status == "executed"


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, 10001])
def test_domain_rejects_invalid_quantities(setup, quantity):
    with pytest.raises(DomainError):
        prepare(setup[0], quantity=quantity)


def test_insufficient_stock_and_missing_sku_do_not_create_proposals(setup):
    service, _, _ = setup
    with pytest.raises(DomainError, match="insufficient_stock"):
        prepare(service, quantity=9)
    with pytest.raises(DomainError, match="not_found"):
        service.propose(CLERK, "UNKNOWN", "centro", 1, "missing")
