"""FastAPI application for the Tripletex challenge."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request

from .config import AppSettings, configure_logging, load_local_env
from .models import HealthResponse, SolveRequest, SolveResponse
from .service import SolverService, build_default_service
from .solve_logging import SolveRequestContext


def create_app(service: SolverService | None = None) -> FastAPI:
    load_local_env()
    configure_logging(AppSettings.load().log_level)
    app = FastAPI(title="Tripletex AI Accounting Agent", version="0.1.0")
    app.state.solver_service = service or build_default_service()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/solve", response_model=SolveResponse)
    async def solve(payload: SolveRequest, request: Request) -> SolveResponse:
        solver_service: SolverService = request.app.state.solver_service
        context = SolveRequestContext(
            trace_id=request.headers.get("x-request-id") or str(uuid4()),
            client_host=request.client.host if request.client else None,
            forwarded_for=request.headers.get("x-forwarded-for"),
            user_agent=request.headers.get("user-agent"),
            request_id=request.headers.get("x-request-id"),
            cf_ray=request.headers.get("cf-ray"),
        )
        return await solver_service.solve(payload, context=context)

    return app


app = create_app()
