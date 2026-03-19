"""FastAPI application for the Tripletex challenge."""

from __future__ import annotations

from fastapi import FastAPI, Request

from .models import HealthResponse, SolveRequest, SolveResponse
from .service import SolverService, build_default_service


def create_app(service: SolverService | None = None) -> FastAPI:
    app = FastAPI(title="Tripletex AI Accounting Agent", version="0.1.0")
    app.state.solver_service = service or build_default_service()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/solve", response_model=SolveResponse)
    async def solve(payload: SolveRequest, request: Request) -> SolveResponse:
        solver_service: SolverService = request.app.state.solver_service
        return await solver_service.solve(payload)

    return app


app = create_app()
