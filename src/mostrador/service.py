import time
from collections.abc import Callable
from uuid import uuid4

from mostrador.domain import Actor, DomainError, Proposal, SearchIntent, validate_quantity
from mostrador.ports import Adapters


class Copilot:
    def __init__(self, adapters: Adapters, clock: Callable[[], float] = time.time):
        self.adapters = adapters
        self.clock = clock

    @staticmethod
    def authorize(actor: Actor, proposal: Proposal | None = None, write: bool = False):
        if actor.role not in {"clerk", "supervisor", "viewer"}:
            raise DomainError("permission_denied", 403)
        if write and actor.role == "viewer":
            raise DomainError("permission_denied", 403)
        if proposal and actor.id != proposal.actor_id and actor.role != "supervisor":
            raise DomainError("permission_denied", 403)

    def search(self, actor: Actor, query: str):
        self.authorize(actor)
        return self.adapters.commerce.search(query)

    def assist(self, actor: Actor, message: str):
        self.authorize(actor)
        intent = self.adapters.assistant.interpret(message)
        if not isinstance(intent, SearchIntent) or not 1 <= len(intent.query.strip()) <= 200:
            raise DomainError("unsupported_intent", 422)
        return {
            "intent": "search",
            "offers": self.search(actor, intent.query),
            "notice": "Consulta comercial. No ofrece consejo clínico ni ejecuta reservas.",
            "demo": self.adapters.is_demo,
        }

    def propose(self, actor: Actor, sku: str, branch_id: str, quantity: int, key: str):
        self.authorize(actor, write=True)
        validate_quantity(quantity)
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 128:
            raise DomainError("invalid_idempotency_key", 422)
        existing = self.adapters.store.find(actor.id, key)
        if existing is None:
            quote = self.adapters.commerce.quote(sku, branch_id, quantity)
            now = int(self.clock())
            existing = self.adapters.store.create(
                Proposal(
                    str(uuid4()),
                    actor.id,
                    key,
                    quote,
                    "pending",
                    now,
                    now + 300,
                )
            )
        actual = (existing.quote.offer.sku, existing.quote.offer.branch_id, existing.quote.quantity)
        if actual != (sku, branch_id, quantity):
            raise DomainError("idempotency_conflict")
        return existing

    def get(self, actor: Actor, proposal_id: str):
        proposal = self.adapters.store.get(proposal_id)
        self.authorize(actor, proposal)
        return proposal

    def events(self, actor: Actor, proposal_id: str):
        self.get(actor, proposal_id)
        return self.adapters.store.events(proposal_id)

    def decide(self, actor: Actor, proposal_id: str, decision: str):
        self.authorize(actor, self.get(actor, proposal_id), write=True)
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_decision", 422)
        proposal, claimed = self.adapters.store.claim(
            proposal_id,
            actor,
            decision,
            int(self.clock()),
        )
        if not claimed:
            return proposal
        try:
            receipt = self.adapters.commerce.reserve(proposal.quote, proposal.id)
        except DomainError as error:
            return self.adapters.store.finish(
                proposal.id,
                actor,
                "failed",
                int(self.clock()),
                error_code=error.code,
            )
        except Exception:
            # The provider may have committed the reservation before losing the response.
            # Never retry automatically or leak upstream error bodies/secrets.
            return self.adapters.store.finish(
                proposal.id,
                actor,
                "uncertain",
                int(self.clock()),
                error_code="provider_outcome_unknown",
            )
        return self.adapters.store.finish(
            proposal.id,
            actor,
            "executed",
            int(self.clock()),
            receipt=receipt,
        )
