"""Adapters are trusted application code, not model-generated executable plugins."""

from dataclasses import dataclass
from typing import Protocol

from mostrador.domain import Actor, Offer, Proposal, Quote, SearchIntent


class Commerce(Protocol):
    def search(self, query: str) -> list[Offer]: ...
    def quote(self, sku: str, branch_id: str, quantity: int) -> Quote: ...
    def reserve(self, quote: Quote, operation_id: str) -> dict:
        """Atomic version/stock validation; durable idempotency by operation_id.

        DomainError guarantees no write. Any ambiguous outcome must raise another exception.
        """
        ...


class WorkflowStore(Protocol):
    def find(self, actor_id: str, key: str) -> Proposal | None: ...
    def create(self, proposal: Proposal) -> Proposal: ...
    def get(self, proposal_id: str) -> Proposal: ...
    def claim(
        self, proposal_id: str, actor: Actor, decision: str, now: int
    ) -> tuple[Proposal, bool]: ...
    def finish(
        self,
        proposal_id: str,
        actor: Actor,
        status: str,
        now: int,
        receipt: dict | None = None,
        error_code: str | None = None,
    ) -> Proposal: ...
    def events(self, proposal_id: str) -> list[dict]: ...


class Identity(Protocol):
    def authenticate(self, token: str) -> Actor: ...


class Assistant(Protocol):
    def interpret(self, message: str) -> SearchIntent:
        """Read-only intent; never approvals, raw SQL, prices or executable tool calls."""
        ...


@dataclass
class Adapters:
    commerce: Commerce
    store: WorkflowStore
    identity: Identity
    assistant: Assistant
    is_demo: bool = False
