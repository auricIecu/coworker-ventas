from dataclasses import dataclass


class DomainError(Exception):
    """Business rejection. Commerce adapters must guarantee no side effect occurred."""

    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Actor:
    id: str
    role: str


@dataclass(frozen=True)
class Offer:
    sku: str
    branch_id: str
    title: str
    sell_unit: str
    available: int
    unit_price_cents: int
    version: int
    currency: str = "USD"
    source: str = "synthetic-demo"


@dataclass(frozen=True)
class Quote:
    offer: Offer
    quantity: int
    observed_at: int

    @property
    def total_cents(self) -> int:
        return self.offer.unit_price_cents * self.quantity

    @property
    def available(self) -> int:
        return self.offer.available


@dataclass(frozen=True)
class Proposal:
    id: str
    actor_id: str
    idempotency_key: str
    quote: Quote
    status: str
    created_at: int
    expires_at: int
    receipt: dict | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class SearchIntent:
    query: str


def validate_quantity(quantity: int) -> None:
    if type(quantity) is not int or not 1 <= quantity <= 10_000:
        raise DomainError("invalid_quantity", 422)
