from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from mostrador.bootstrap import configured_adapters
from mostrador.domain import Actor, DomainError, Offer, Proposal
from mostrador.ports import Adapters
from mostrador.service import Copilot


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalInput(Input):
    sku: str = Field(min_length=1, max_length=80)
    branch_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(strict=True, ge=1, le=10_000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class DecisionInput(Input):
    decision: Literal["approve", "reject"]


class AssistantInput(Input):
    message: str = Field(min_length=1, max_length=200)


class QuoteResponse(BaseModel):
    offer: Offer
    quantity: int
    observed_at: int
    total_cents: int


class ProposalResponse(BaseModel):
    id: str
    actor_id: str
    idempotency_key: str
    quote: QuoteResponse
    status: Literal[
        "pending", "executing", "executed", "rejected", "expired", "failed", "uncertain"
    ]
    created_at: int
    expires_at: int
    receipt: dict | None
    error_code: str | None


class EventResponse(BaseModel):
    sequence: int
    kind: str
    actor_id: str
    timestamp: int


class AssistantResponse(BaseModel):
    intent: Literal["search"]
    offers: list[Offer]
    notice: str
    demo: bool


def serialize(proposal: Proposal) -> dict:
    payload = asdict(proposal)
    payload["quote"]["total_cents"] = proposal.quote.total_cents
    return payload


def create_app(adapters: Adapters | None = None) -> FastAPI:
    adapters = adapters if adapters is not None else configured_adapters()
    service = Copilot(adapters)
    app = FastAPI(
        title="Sales Coworker",
        version="0.1.0",
        description="Arquitectura abierta para asistencia comercial supervisada. "
        "El modo demo usa datos inventados y búsqueda por palabras; no es IA clínica.",
    )
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if credentials is None:
            raise DomainError("missing_credentials", 401)
        return adapters.identity.authenticate(credentials.credentials)

    current_actor = Annotated[Actor, Depends(identity)]

    @app.exception_handler(DomainError)
    async def domain_error(_request, error: DomainError):
        return JSONResponse(
            {"error": error.code},
            status_code=error.status,
            headers={"WWW-Authenticate": "Bearer"} if error.status == 401 else None,
        )

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "mode": "demo" if adapters.is_demo else "external"}

    @app.get("/offers", response_model=list[Offer], tags=["commerce"])
    def offers(actor: current_actor, q: str = Query(default="", max_length=200)):
        return service.search(actor, q)

    @app.post("/assistant", response_model=AssistantResponse, tags=["assistant"])
    def assistant(body: AssistantInput, actor: current_actor):
        return service.assist(actor, body.message)

    @app.post("/proposals", response_model=ProposalResponse, status_code=201, tags=["workflow"])
    def propose(body: ProposalInput, actor: current_actor):
        return serialize(
            service.propose(actor, body.sku, body.branch_id, body.quantity, body.idempotency_key)
        )

    @app.get("/proposals/{proposal_id}", response_model=ProposalResponse, tags=["workflow"])
    def proposal(proposal_id: str, actor: current_actor):
        return serialize(service.get(actor, proposal_id))

    @app.post(
        "/proposals/{proposal_id}/decision", response_model=ProposalResponse, tags=["workflow"]
    )
    def decision(proposal_id: str, body: DecisionInput, actor: current_actor):
        return serialize(service.decide(actor, proposal_id, body.decision))

    @app.get(
        "/proposals/{proposal_id}/events", response_model=list[EventResponse], tags=["workflow"]
    )
    def events(proposal_id: str, actor: current_actor):
        return service.events(actor, proposal_id)

    return app
