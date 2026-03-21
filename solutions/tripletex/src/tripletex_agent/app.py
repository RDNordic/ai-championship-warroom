"""FastAPI application for the Tripletex challenge."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

from .config import AppSettings, configure_logging, load_local_env
from .models import HealthResponse, SolveRequest, SolveResponse
from .service import SolverService, build_default_service
from .solve_logging import SolveRequestContext


def create_app(service: SolverService | None = None) -> FastAPI:
    load_local_env()
    settings = AppSettings.load()
    configure_logging(settings.log_level)
    app = FastAPI(title="Tripletex AI Accounting Agent", version="0.1.0")
    app.state.solver_service = service or build_default_service()
    app.state.log_path = settings.solve_event_log_path

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

    @app.get("/logs", response_class=PlainTextResponse)
    async def logs(
        request: Request,
        tail: int = Query(default=0, description="Return only last N lines (0=all)"),
        trace_id: str = Query(default="", description="Filter by trace_id"),
    ) -> str:
        log_path: Path = request.app.state.log_path
        if not log_path.exists():
            return "No logs yet.\n"

        lines = log_path.read_text(encoding="utf-8").splitlines()

        if trace_id:
            lines = [l for l in lines if trace_id in l]

        if tail > 0:
            lines = lines[-tail:]

        return "\n".join(lines) + "\n"

    @app.delete("/logs", response_class=PlainTextResponse)
    async def clear_logs(request: Request) -> str:
        log_path: Path = request.app.state.log_path
        if log_path.exists():
            log_path.write_text("", encoding="utf-8")
        return "Logs cleared.\n"

    return app


app = create_app()
