from __future__ import annotations

import httpx
import pytest

from tripletex_agent.app import create_app
from tripletex_agent.models import SolveResponse


class StaticSolverService:
    def __init__(self) -> None:
        self.last_context = None

    async def solve(self, request, *, context=None) -> SolveResponse:  # noqa: ANN001
        del request
        self.last_context = context
        return SolveResponse(status="completed")


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    app = create_app(service=StaticSolverService())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_solve_endpoint_returns_completed() -> None:
    service = StaticSolverService()
    app = create_app(service=service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/solve",
            json={
                "prompt": "Create a customer named ACME AS",
                "files": [],
                "tripletex_credentials": {
                    "base_url": "https://tx-proxy.ainm.no/v2",
                    "session_token": "secret-token",
                },
            },
            headers={"x-request-id": "req-123"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "completed"}
        assert service.last_context is not None
        assert service.last_context.trace_id == "req-123"
        assert service.last_context.request_id == "req-123"
