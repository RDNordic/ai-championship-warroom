from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripletex_agent.api_call_plan import ApiCallCompletionCheck, ApiCallPlan, ApiCallStep
from tripletex_agent.models import SolveRequest
from tripletex_agent.service import SolverService
from tripletex_agent.solve_logging import SolveEventLogger, SolveRequestContext
from tripletex_agent.task_plan import EntityPayload, Operation, TaskFamily, TaskPlan
from tripletex_agent.workflows import StubWorkflow
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


class StaticApiCallPlanner:
    def __init__(self, api_call_plan: ApiCallPlan | None) -> None:
        self._api_call_plan = api_call_plan
        self.calls: list[tuple[str, str]] = []

    def plan(
        self,
        prompt: str,
        attachments: list[object],
        base_plan: TaskPlan,
    ) -> ApiCallPlan | None:
        del attachments, base_plan
        self.calls.append((prompt, "planned"))
        return self._api_call_plan


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


def _api_call_plan() -> ApiCallPlan:
    return ApiCallPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.CREATE,
        primary_goal="Register a travel expense report",
        steps=[
            ApiCallStep(
                step_id="lookup_employee",
                purpose="Find the employee by email",
                method="GET",
                path="/employee",
                params={"email": "traveler@example.org"},
                save_response_fields_as={"values[0].id": "employee_id"},
            ),
            ApiCallStep(
                step_id="create_report",
                purpose="Create the travel expense report",
                method="POST",
                path="/travelExpense",
                json_body={"employee": {"id": "$employee_id"}},
            ),
        ],
        completion_checks=[
            ApiCallCompletionCheck(
                description="Travel expense report should be created",
                kind="resource_created",
            )
        ],
        assumptions=["Tripletex accepts employee email lookup for this tenant"],
        confidence=0.62,
    )


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


@pytest.mark.asyncio
async def test_solver_service_records_api_call_plan_for_stubbed_workflow(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    travel_plan = TaskPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.UNKNOWN,
        confidence=0.85,
    )
    api_call_planner = StaticApiCallPlanner(_api_call_plan())
    service = SolverService(
        planner=StaticPlanner(travel_plan),
        workflows=StaticRegistry(StubWorkflow(TaskFamily.UNKNOWN)),
        client_factory=lambda credentials: StaticClient(),
        event_logger=SolveEventLogger(log_path),
        api_call_planner=api_call_planner,
    )

    response = await service.solve(_request(), context=_context())

    assert response.status == "completed"
    events = _read_events(log_path)
    assert [event["event"] for event in events] == [
        "received",
        "planned",
        "api_call_plan",
        "completed",
    ]
    assert events[2]["api_call_plan"]["primary_goal"] == "Register a travel expense report"
    assert events[2]["api_call_plan"]["steps"][0]["path"] == "/employee"
    assert api_call_planner.calls == [("Create a customer named ACME AS", "planned")]


@pytest.mark.asyncio
async def test_solver_service_skips_api_call_plan_for_live_workflow(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    api_call_planner = StaticApiCallPlanner(_api_call_plan())
    service = SolverService(
        planner=StaticPlanner(_plan()),
        workflows=StaticRegistry(SuccessfulWorkflow()),
        client_factory=lambda credentials: StaticClient(),
        event_logger=SolveEventLogger(log_path),
        api_call_planner=api_call_planner,
    )

    response = await service.solve(_request(), context=_context())

    assert response.status == "completed"
    events = _read_events(log_path)
    assert [event["event"] for event in events] == ["received", "planned", "completed"]
    assert api_call_planner.calls == []
