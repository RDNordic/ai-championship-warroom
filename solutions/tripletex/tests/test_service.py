from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripletex_agent.models import SolveRequest
from tripletex_agent.service import SolverService
from tripletex_agent.solve_logging import SolveEventLogger, SolveRequestContext
from tripletex_agent.task_plan import EntityPayload, Operation, TaskFamily, TaskPlan
from tripletex_agent.workflows.base import WorkflowResult


class StaticPlanner:
    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan

    def plan(self, prompt: str, attachments: list[object]) -> TaskPlan:
        del prompt, attachments
        return self._plan


class StaticRegistry:
    def __init__(self, workflow) -> None:  # noqa: ANN001
        self._workflow = workflow

    def for_plan(self, plan: TaskPlan):  # noqa: ANN001
        del plan
        return self._workflow


class StaticClient:
    async def __aenter__(self) -> StaticClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class SuccessfulWorkflow:
    async def execute(self, *, plan: TaskPlan, client: StaticClient) -> WorkflowResult:
        del plan, client
        return WorkflowResult(
            name="customer_create",
            intended_operations=["POST /customer"],
            resource_ids=[101],
            details={"entity": "customer"},
        )


class FailingWorkflow:
    async def execute(self, *, plan: TaskPlan, client: StaticClient) -> WorkflowResult:
        del plan, client
        raise RuntimeError("boom")


def _request() -> SolveRequest:
    return SolveRequest.model_validate(
        {
            "prompt": "Create a customer named ACME AS",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "secret-token",
            },
        }
    )


def _context() -> SolveRequestContext:
    return SolveRequestContext(
        trace_id="trace-123",
        client_host="127.0.0.1",
        forwarded_for="203.0.113.5",
        user_agent="pytest",
        request_id="req-123",
        cf_ray="ray-1",
    )


def _plan() -> TaskPlan:
    return TaskPlan(
        task_family=TaskFamily.CUSTOMERS_PRODUCTS,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(entity_type="customer", fields={"name": "ACME AS"})
        ],
        confidence=0.9,
    )


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_solver_service_records_received_planned_and_completed_events(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    service = SolverService(
        planner=StaticPlanner(_plan()),
        workflows=StaticRegistry(SuccessfulWorkflow()),
        client_factory=lambda credentials: StaticClient(),
        event_logger=SolveEventLogger(log_path),
    )

    response = await service.solve(_request(), context=_context())

    assert response.status == "completed"
    events = _read_events(log_path)
    assert [event["event"] for event in events] == ["received", "planned", "completed"]
    assert events[0]["request"]["prompt"] == "Create a customer named ACME AS"
    assert events[1]["workflow"] == "SuccessfulWorkflow"
    assert events[2]["result"]["resource_ids"] == [101]
    assert "secret-token" not in log_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_solver_service_records_failed_events(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    service = SolverService(
        planner=StaticPlanner(_plan()),
        workflows=StaticRegistry(FailingWorkflow()),
        client_factory=lambda credentials: StaticClient(),
        event_logger=SolveEventLogger(log_path),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.solve(_request(), context=_context())

    events = _read_events(log_path)
    assert [event["event"] for event in events] == ["received", "planned", "failed"]
    assert events[-1]["error"]["type"] == "RuntimeError"
    assert events[-1]["error"]["message"] == "boom"
