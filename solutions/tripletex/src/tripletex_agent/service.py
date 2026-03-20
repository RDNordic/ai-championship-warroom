"""Service orchestration for the Tripletex solver endpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .client import TripletexClient
from .config import AppSettings
from .models import SolveRequest, SolveResponse, TripletexCredentials
from .planner import Planner, build_default_planner
from .task_plan import TaskFamily
from .workflows import (
    CustomerCreateWorkflow,
    DepartmentCreateWorkflow,
    EmployeeCreateWorkflow,
    InvoiceCreateWorkflow,
    ProductCreateWorkflow,
    ProjectCreateWorkflow,
    StubWorkflow,
    WorkflowRegistry,
)

logger = logging.getLogger(__name__)


class SolverService:
    """Coordinates planning, workflow selection, and Tripletex client setup."""

    def __init__(
        self,
        *,
        planner: Planner,
        workflows: WorkflowRegistry,
        client_factory: Callable[[TripletexCredentials], TripletexClient],
    ) -> None:
        self._planner = planner
        self._workflows = workflows
        self._client_factory = client_factory

    async def solve(self, request: SolveRequest) -> SolveResponse:
        plan = await asyncio.to_thread(self._planner.plan, request.prompt, request.files)
        workflow = self._workflows.for_plan(plan)

        async with self._client_factory(request.tripletex_credentials) as client:
            result = await workflow.execute(plan=plan, client=client)

        logger.info(
            "Solved request with scaffold workflow",
            extra={
                "task_family": plan.task_family.value,
                "operation": plan.operation.value,
                "workflow": result.name,
                "intended_operations": result.intended_operations,
            },
        )

        return SolveResponse(status="completed")


def build_default_service() -> SolverService:
    settings = AppSettings.load()
    workflows = WorkflowRegistry(
        workflows=[
            CustomerCreateWorkflow(),
            ProductCreateWorkflow(),
            EmployeeCreateWorkflow(),
            DepartmentCreateWorkflow(),
            ProjectCreateWorkflow(),
            InvoiceCreateWorkflow(),
        ],
        fallback=StubWorkflow(TaskFamily.UNKNOWN),
    )

    return SolverService(
        planner=build_default_planner(settings),
        workflows=workflows,
        client_factory=TripletexClient.from_credentials,
    )
