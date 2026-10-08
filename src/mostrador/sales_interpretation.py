"""Validate model output at the boundary; keep offline simulation explicitly separate."""

import unicodedata
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from mostrador.backoffice import Identifier, Record
from mostrador.domain import DomainError
from mostrador.sales_context import applicable_documents


class Interpretation(Record):
    conversation_id: Identifier
    status: Literal["matched", "ambiguous", "irrelevant"]
    sku: Identifier | None
    branch_id: Identifier | None
    reason: Annotated[str, Field(min_length=1, max_length=600)]
    document_ids: Annotated[list[Identifier], Field(max_length=40)]


def validate_interpretations(payload, conversations, sources):
    try:
        if set(payload) != {"items"} or not isinstance(payload["items"], list):
            raise ValueError("Invalid envelope")
        rows = [Interpretation.model_validate(r) for r in payload["items"]]
        by_id = {c.id: c for c in conversations}
        if len(rows) != len(by_id) or {r.conversation_id for r in rows} != set(by_id):
            raise ValueError("Missing or duplicate conversation")
        stock_pairs = {(s.sku, s.branch_id) for s in sources.operations.stock}
        for r in rows:
            conversation = by_id[r.conversation_id]
            if r.status == "matched":
                if conversation.branch_id is None or r.branch_id != conversation.branch_id:
                    raise ValueError("Untrusted branch assignment")
                if (r.sku, r.branch_id) not in stock_pairs:
                    raise ValueError("Unknown product or missing stock")
                eligible = {d.id for d in applicable_documents(sources, r.sku, r.branch_id)}
                if not set(r.document_ids) <= eligible:
                    raise ValueError("Invented, expired or out-of-scope citation")
            else:
                # A model abstention is never actionable, even if it also emits
                # contradictory attributions. Discard them rather than promoting
                # uncertain context to a matched signal.
                r.sku, r.branch_id, r.document_ids = None, None, []
        return rows
    except (ValidationError, ValueError, TypeError, KeyError):
        raise DomainError("model_invalid_response", 502) from None


class OfflineInterpreter:
    """Narrow deterministic fixture interpreter, never presented as an LLM."""

    mode, model_id = "offline", None

    def infer(self, payload):
        items = []
        for c in payload["conversations"]:
            text = " ".join(m["text"] for m in c["messages"] if m["role"] == "customer").lower()
            text = "".join(
                ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
            )
            for word, number in (("quinientos", "500"), ("treinta", "30"), ("cien", "100")):
                text = text.replace(word, number)
            sku = None
            if "vitamina c" in text and "500" in text and "30" in text:
                sku = "SC-001"
            elif "vitamina c" in text and "1 g" in text and "10" in text:
                sku = "SC-004"
            elif "jabon" in text and "100" in text:
                sku = "SC-002"
            elif "panuelos" in text and "100" in text:
                sku = "SC-003"
            malicious = "ignora instrucciones" in text or "aprueba compra" in text
            status = (
                "irrelevant" if malicious else "matched" if sku and c["branch_id"] else "ambiguous"
            )
            matched = status == "matched"
            documents = (
                [
                    d["id"]
                    for d in payload["documents"]
                    if sku in d["skus"] and c["branch_id"] in d["branch_ids"]
                ]
                if matched
                else []
            )
            items.append(
                {
                    "conversation_id": c["id"],
                    "status": status,
                    "sku": sku if matched else None,
                    "branch_id": c["branch_id"] if matched else None,
                    "reason": "Simulación local: producto y sucursal identificados."
                    if matched
                    else "Sin señal comercial utilizable."
                    if malicious
                    else "Falta precisar producto, presentación o sucursal.",
                    "document_ids": documents,
                }
            )
        return {"items": items}
