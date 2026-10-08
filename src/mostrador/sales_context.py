"""Synthetic source contracts; no connector accepts enterprise data in this demo."""

import hashlib
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from mostrador.backoffice import Identifier, Record, Snapshot


class Message(Record):
    role: Literal["customer", "staff"]
    text: Annotated[str, Field(min_length=1, max_length=1000)]


class Conversation(Record):
    id: Identifier
    branch_id: Identifier | None
    channel: Literal["whatsapp", "web", "store"]
    occurred_at: AwareDatetime
    messages: Annotated[list[Message], Field(min_length=1, max_length=12)]

    def text(self):
        return "\n".join(f"{m.role}: {m.text}" for m in self.messages)


class Conditions(Record):
    requires_stock: bool
    max_duration_days: Annotated[int, Field(strict=True, ge=1, le=30)] | None
    required_approvals: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=200)]],
        Field(min_length=1, max_length=10),
    ]


class Document(Record):
    id: Identifier
    title: Annotated[str, Field(min_length=1, max_length=180)]
    kind: Literal["procedure", "promotion"]
    branch_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    skus: Annotated[list[Identifier], Field(min_length=1, max_length=1000)]
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    conditions: Conditions

    @model_validator(mode="after")
    def valid_dates(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("Invalid document effective window")
        return self


class Sources(Record):
    synthetic: Literal[True] = True
    operations: Snapshot
    conversations: Annotated[list[Conversation], Field(max_length=500)]
    documents: Annotated[list[Document], Field(min_length=1, max_length=40)]
    burst: Annotated[list[Conversation], Field(max_length=20)] = []

    @model_validator(mode="after")
    def relations(self):
        branches = {b.id for b in self.operations.branches}
        skus = {p.sku for p in self.operations.products}
        for rows in (self.conversations, self.burst, self.documents):
            if len({row.id for row in rows}) != len(rows):
                raise ValueError("Duplicate source ID")
        for c in [*self.conversations, *self.burst]:
            if c.branch_id is not None and c.branch_id not in branches:
                raise ValueError("Unknown conversation branch")
            if not self.operations.coverage_start <= c.occurred_at < self.operations.as_of:
                raise ValueError("Conversation outside source coverage")
        for d in self.documents:
            if not set(d.branch_ids) <= branches or not set(d.skus) <= skus:
                raise ValueError("Unknown document scope")
        return self

    def revision(self):
        return hashlib.sha256(self.model_dump_json(exclude={"burst"}).encode()).hexdigest()


def load_sources() -> Sources:
    import json

    root = files("mostrador").joinpath("data/sales")
    operations = json.loads(root.joinpath("operations.json").read_text(encoding="utf-8"))
    sources = {"synthetic": True, "operations": operations}
    for name in ("conversations", "documents", "burst"):
        data = json.loads(root.joinpath(f"{name}.json").read_text(encoding="utf-8"))
        if data.get("synthetic") is not True:
            raise ValueError("Only synthetic sources supported")
        sources[name] = data["conversations" if name == "burst" else name]
    return Sources.model_validate(sources)


def applicable_documents(sources: Sources, sku: str, branch_id: str) -> list[Document]:
    return [
        d
        for d in sources.documents
        if sku in d.skus
        and branch_id in d.branch_ids
        and d.valid_from <= sources.operations.as_of < d.valid_until
    ]
