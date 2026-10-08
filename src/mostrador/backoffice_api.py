"""Demo-only sales back office with optional periodic snapshot analysis."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from mostrador.agents.auditor import InsightStore
from mostrador.agents_api import create_agents_router
from mostrador.backoffice import Reviewer, Snapshot, load_demo
from mostrador.backoffice_store import RecommendationStore
from mostrador.domain import DomainError
from mostrador.sales_routes import install_sales_routes


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


def create_app(
    *,
    db_path: str | None = None,
    snapshot_path: Path | None = None,
    demo: bool = False,
    scan_interval: int | None = None,
) -> FastAPI:
    if not demo and os.getenv("COPILOT_MODE") != "demo":
        raise RuntimeError("Back office requires COPILOT_MODE=demo; real providers pending")
    interval = (
        scan_interval
        if scan_interval is not None
        else int(os.getenv("SALES_SCAN_INTERVAL_SECONDS", "0"))
    )
    if interval < 0 or (0 < interval < 10):
        raise ValueError("Scan interval must be 0 (manual) or at least 10 seconds")
    configured_path = snapshot_path or os.getenv("SALES_SNAPSHOT_PATH")
    path = Path(configured_path) if configured_path else None
    database_path = db_path or os.getenv("COPILOT_DB_PATH", ".local/sales.sqlite")
    store = RecommendationStore(database_path)
    health = {"analysis_status": "not_run", "snapshot_id": None}
    scan_lock = Lock()

    def snapshot():
        try:
            if path and path.stat().st_size > 5_000_000:
                raise ValueError("Snapshot too large")
            return Snapshot.model_validate_json(path.read_text()) if path else load_demo()
        except (OSError, ValueError):
            health["analysis_status"] = "source_unavailable"
            raise DomainError("source_unavailable", 503) from None

    def scan():
        with scan_lock:
            source = snapshot()
            proposals = store.record(source)
            health.update(analysis_status="ok", snapshot_id=source.fingerprint())
            return {
                "snapshot_id": source.fingerprint(),
                "as_of": source.as_of.isoformat(),
                "recommendations": proposals,
                "analysis_mode": "deterministic_demo",
            }

    async def periodic_scan():
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(scan)
                # After the first explicit analysis, new synthetic sources can be
                # analyzed in the background. No external action is ever executed.
                state = workspace.state()
                if state.get("revision") and state["revision"] != workspace.revision(
                    workspace.sources()
                ):
                    await asyncio.to_thread(
                        workspace.run,
                        Reviewer(
                            "demo-background",
                            "operator",
                            tuple(b.id for b in workspace.base.operations.branches),
                        ),
                    )
            except Exception:
                health["analysis_status"] = "analysis_failed"

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.to_thread(scan)
        except DomainError:
            pass
        task = asyncio.create_task(periodic_scan()) if interval else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Sales Coworker — Back Office",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Fuentes sintéticas, interpretación opcional con Bedrock y revisión humana. "
            "Sin ejecución comercial."
        ),
    )
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        identities = {
            "demo-encargado": Reviewer("demo-encargado", "operator", ("gye-centro-demo",)),
            "demo-jefe-zona": Reviewer(
                "demo-jefe-zona", "operator", ("gye-centro-demo", "gye-norte-demo")
            ),
            "demo-encargado-quito": Reviewer("demo-encargado-quito", "operator", ("uio-demo",)),
            "demo-viewer": Reviewer("demo-viewer", "viewer", ("gye-centro-demo",)),
        }
        if credentials is None or credentials.credentials not in identities:
            raise DomainError("invalid_credentials", 401)
        return identities[credentials.credentials]

    current_actor = Annotated[Reviewer, Depends(identity)]

    @app.exception_handler(DomainError)
    async def domain_error(_request, error):
        return JSONResponse(
            {"error": error.code},
            status_code=error.status,
            headers={"WWW-Authenticate": "Bearer"} if error.status == 401 else None,
        )

    @app.get("/health")
    def health_check():
        return {
            "mode": "demo",
            "analysis_mode": "deterministic_demo",
            "scan_interval_seconds": interval,
            "execution": "not_configured",
            **health,
        }

    @app.post("/analysis/run")
    def run_analysis(actor: current_actor):
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)
        result = scan()
        result["recommendations"] = [
            r for r in result["recommendations"] if r["branch_id"] in actor.branches
        ]
        return result

    @app.get("/recommendations")
    def recommendations(actor: current_actor):
        return store.list(actor)

    @app.get("/recommendations/{identifier}")
    def recommendation(identifier: str, actor: current_actor):
        return store.get(identifier, actor)

    @app.get("/recommendations/{identifier}/events")
    def events(identifier: str, actor: current_actor):
        return store.events(identifier, actor)

    @app.post("/recommendations/{identifier}/decision")
    def decide(identifier: str, body: Decision, actor: current_actor):
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)
        return store.decide(identifier, body.decision, actor, snapshot())

    workspace = install_sales_routes(app, identity, database_path, Decision)

    # --- Agent HQ routes ---
    insight_store = InsightStore(database_path.replace(".sqlite", "_insights.sqlite"))
    agents_router = create_agents_router(identity, insight_store)
    app.include_router(agents_router)

    return app
