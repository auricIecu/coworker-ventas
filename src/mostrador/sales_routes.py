"""Scoped API and bundled UI for the synthetic, human-reviewed workspace."""

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from mostrador.backoffice import Reviewer
from mostrador.bedrock import BedrockInterpreter
from mostrador.domain import DomainError
from mostrador.sales_context import Conversation
from mostrador.sales_interpretation import OfflineInterpreter
from mostrador.sales_workspace import SalesWorkspace


class SyntheticConversation(Conversation):
    synthetic: Literal[True]


def install_sales_routes(app, identity, path, decision_type):
    mode = os.getenv("SALES_AI_MODE", "offline")
    if mode not in {"offline", "bedrock"}:
        raise ValueError("SALES_AI_MODE must be offline or bedrock")
    interpreter = BedrockInterpreter() if mode == "bedrock" else OfflineInterpreter()
    workspace = SalesWorkspace(path + ".workspace.sqlite", interpreter=interpreter)
    app.state.sales_workspace = workspace
    actor_type = Annotated[Reviewer, Depends(identity)]

    @app.get("/workspace")
    def view(actor: actor_type):
        return workspace.view(actor)

    @app.post("/workspace/analyze")
    def analyze(actor: actor_type):
        return workspace.run(actor)

    @app.post("/workspace/demo/burst")
    def burst(actor: actor_type):
        return workspace.add_burst(actor)

    @app.post("/workspace/conversations")
    def conversation(body: SyntheticConversation, actor: actor_type):
        try:
            return workspace.add_conversation(
                Conversation.model_validate(body.model_dump(exclude={"synthetic"})), actor
            )
        except ValidationError:
            raise DomainError("invalid_synthetic_source", 422) from None

    @app.post("/workspace/recommendations/{identifier}/decision")
    def decide(identifier: str, body: decision_type, actor: actor_type):
        return workspace.decide(identifier, body.decision, actor)

    @app.get("/workspace/recommendations/{identifier}/events")
    def events(identifier: str, actor: actor_type):
        return workspace.events(identifier, actor)

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    return workspace
