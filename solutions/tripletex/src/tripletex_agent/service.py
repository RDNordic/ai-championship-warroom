"""Service orchestration for the Tripletex solver endpoint."""

from __future__ import annotations

import asyncio
import json
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
    InvoiceCreditNoteWorkflow,
    InvoicePaymentWorkflow,
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
        logger.info(
            "Received solve request prompt=%r attachments=%s base_url=%s",
            request.prompt,
            [attachment.filename for attachment in request.files],
            request.tripletex_credentials.base_url,
        )
        plan = await asyncio.to_thread(self._planner.plan, request.prompt, request.files)
        workflow = self._workflows.for_plan(plan)
        logger.info(
            "Planned solve workflow=%s plan=%s",
            workflow.__class__.__name__,
            json.dumps(plan.model_dump(), ensure_ascii=False, default=str),
        )

        try:
            async with self._client_factory(request.tripletex_credentials) as client:
                result = await workflow.execute(plan=plan, client=client)
        except Exception:
            logger.exception("Solve request failed prompt=%r", request.prompt)
            raise

        logger.info(
            (
                "Solved request task_family=%s operation=%s workflow=%s "
                "operations=%s resources=%s details=%s"
            ),
            plan.task_family.value,
            plan.operation.value,
            result.name,
            result.intended_operations,
            result.resource_ids,
            json.dumps(result.details, ensure_ascii=False, default=str),
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
            InvoicePaymentWorkflow(),
            InvoiceCreditNoteWorkflow(),
        ],
        fallback=StubWorkflow(TaskFamily.UNKNOWN),
    )

    return SolverService(
        planner=build_default_planner(settings),
        workflows=workflows,
        client_factory=TripletexClient.from_credentials,
    )
