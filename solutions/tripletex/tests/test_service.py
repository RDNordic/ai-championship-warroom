from __future__ import annotations

from tripletex_agent.models import SolveRequest, SolveResponse, TripletexCredentials
from tripletex_agent.service import SolverService
from tripletex_agent.solve_logging import SolveRequestContext
from tripletex_agent.workflows.base import WorkflowResult


class _IncompleteExecutor:
    async def execute(self, *, prompt, attachments, tripletex_client):  # noqa: ANN001
        del prompt, attachments, tripletex_client
        return WorkflowResult(
            name="unified_executor",
            completed=False,
            details={"error": "Invalid API plan"},
        )


class _DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return None


def _dummy_client_factory(credentials: TripletexCredentials) -> _DummyClient:
    del credentials
    return _DummyClient()


async def test_solver_service_returns_completed_on_executor_failure() -> None:
    service = SolverService(
        llm_executor=_IncompleteExecutor(),
        client_factory=_dummy_client_factory,
        event_logger=None,
    )
    request = SolveRequest(
        prompt="Create a customer named ACME AS",
        files=[],
        tripletex_credentials=TripletexCredentials(
            base_url="https://tx-proxy.ainm.no/v2",
            session_token="secret-token",
        ),
    )

    response = await service.solve(
        request,
        context=SolveRequestContext(trace_id="trace-1"),
    )

    assert response == SolveResponse(status="completed")
