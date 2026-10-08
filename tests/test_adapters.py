from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from mostrador.bootstrap import demo_adapters
from mostrador.domain import Actor, DomainError
from mostrador.service import Copilot


@pytest.fixture
def adapters(tmp_path):
    return demo_adapters(str(tmp_path / "contracts.sqlite"))


def test_provider_itself_deduplicates_operation_ids(adapters):
    quote = adapters.commerce.quote("DEMO-001", "centro", 2)
    receipt = adapters.commerce.reserve(quote, "operation-1")
    assert adapters.commerce.reserve(quote, "operation-1") == receipt
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 6
    with pytest.raises(DomainError, match="idempotency_conflict"):
        adapters.commerce.reserve(replace(quote, quantity=1), "operation-1")


def test_price_change_rejects_old_quote_even_if_stock_is_unchanged(adapters):
    quote = adapters.commerce.quote("DEMO-001", "centro", 2)
    with adapters.commerce.database.connect(write=True) as db:
        db.execute("UPDATE offers SET unit_price_cents = 400 WHERE branch_id = 'centro'")
    with pytest.raises(DomainError, match="offer_changed"):
        adapters.commerce.reserve(quote, "operation-2")
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8


def test_two_competing_reservations_cannot_oversell(adapters):
    quote = adapters.commerce.quote("DEMO-001", "centro", 6)

    def reserve(operation_id):
        try:
            adapters.commerce.reserve(quote, operation_id)
            return "executed"
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ["first", "second"]))
    assert sorted(outcomes) == ["executed", "offer_changed"]
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 2


def test_concurrent_proposals_share_id_and_one_audit_event(adapters):
    service = Copilot(adapters)
    actor = Actor("one", "clerk")
    with ThreadPoolExecutor(max_workers=4) as pool:
        proposals = list(
            pool.map(
                lambda _: service.propose(actor, "DEMO-001", "centro", 2, "same-key"),
                range(4),
            )
        )
    assert len({proposal.id for proposal in proposals}) == 1
    assert len(service.events(actor, proposals[0].id)) == 1


def test_assistant_cannot_inject_a_write_intent(adapters):
    class UnsafeAssistant:
        def interpret(self, message):
            return {"tool": "reserve", "arguments": {"quantity": 1}}

    adapters.assistant = UnsafeAssistant()
    with pytest.raises(DomainError, match="unsupported_intent"):
        Copilot(adapters).assist(Actor("one", "clerk"), "reserve")
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8


def test_demo_restart_does_not_restore_consumed_stock(adapters):
    quote = adapters.commerce.quote("DEMO-001", "centro", 2)
    adapters.commerce.reserve(quote, "persisted")
    restored = demo_adapters(adapters.store.path)
    assert restored.commerce.quote("DEMO-001", "centro", 1).available == 6


def test_failed_local_transaction_rolls_back(adapters):
    with pytest.raises(RuntimeError):
        with adapters.commerce.database.connect(write=True) as db:
            db.execute("UPDATE offers SET available = 0")
            raise RuntimeError("simulated failure")
    assert adapters.commerce.quote("DEMO-001", "centro", 1).available == 8
