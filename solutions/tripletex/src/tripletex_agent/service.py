"""Service orchestration for the Tripletex solver endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import uuid4

from .api_call_plan import ApiCallPlan
from .api_call_planner import ApiCallPlanner, build_default_api_call_planner
from .client import TripletexClient
from .config import AppSettings
from .models import SolveRequest, SolveResponse, TripletexCredentials
from .planner import Planner, build_default_planner
from .runtime_context import bind_runtime_context
from .solve_logging import SolveEventLogger, SolveRequestContext
from .task_plan import TaskFamily, TaskPlan
from .workflows import (
    CustomerCreateWorkflow,
    CustomerDeleteWorkflow,
    CustomerUpdateWorkflow,
    DepartmentCreateWorkflow,
    DepartmentDeleteWorkflow,
    EmployeeCreateWorkflow,
    EmployeeUpdateWorkflow,
    InvoiceCreateWorkflow,
    InvoiceCreditNoteWorkflow,
    InvoicePaymentWorkflow,
    ProductCreateWorkflow,
    ProductDeleteWorkflow,
    ProjectCreateWorkflow,
    ProjectDeleteWorkflow,
    StubWorkflow,
    TravelExpenseCreateWorkflow,
    TravelExpenseDeleteWorkflow,
    WorkflowRegistry,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SolveTrace:
    """Resolved trace metadata used through the lifetime of one solve call."""

    trace_id: str
    context: SolveRequestContext


class SolverService:
    """Coordinates planning, workflow selection, and Tripletex client setup."""

    def __init__(
        self,
        *,
        planner: Planner,
        workflows: WorkflowRegistry,
        client_factory: Callable[[TripletexCredentials], TripletexClient],
        event_logger: SolveEventLogger | None = None,
        api_call_planner: ApiCallPlanner | None = None,
    ) -> None:
        self._planner = planner
        self._workflows = workflows
        self._client_factory = client_factory
        self._event_logger = event_logger
        self._api_call_planner = api_call_planner

    async def solve(
        self,
        request: SolveRequest,
        *,
        context: SolveRequestContext | None = None,
    ) -> SolveResponse:
        trace = _resolve_trace(context)
        self._record_received(request=request, trace=trace)
        logger.info(
            "Received solve request trace_id=%s prompt=%r attachments=%s base_url=%s client=%s",
            trace.trace_id,
            request.prompt,
            [attachment.filename for attachment in request.files],
            request.tripletex_credentials.base_url,
            trace.context.client_host,
        )
        plan = None
        workflow_name = None
        try:
            runtime_context = (
                bind_runtime_context(
                    request_context=trace.context,
                    event_logger=self._event_logger,
                )
                if self._event_logger is not None
                else nullcontext()
            )
            with runtime_context:
                plan = await asyncio.to_thread(self._planner.plan, request.prompt, request.files)
                workflow = self._workflows.for_plan(plan)
                workflow_name = workflow.__class__.__name__
                self._record_planned(plan=plan, workflow_name=workflow_name, trace=trace)
                self._maybe_record_api_call_plan(
                    request=request,
                    plan=plan,
                    workflow=workflow,
                    workflow_name=workflow_name,
                    trace=trace,
                )
                logger.info(
                    "Planned solve trace_id=%s workflow=%s plan=%s",
                    trace.trace_id,
                    workflow_name,
                    json.dumps(plan.model_dump(), ensure_ascii=False, default=str),
                )

                async with self._client_factory(request.tripletex_credentials) as client:
                    result = await workflow.execute(plan=plan, client=client)
        except Exception as exc:
            self._record_failed(error=exc, trace=trace, plan=plan, workflow_name=workflow_name)
            logger.exception(
                "Solve request failed trace_id=%s prompt=%r",
                trace.trace_id,
                request.prompt,
            )
            raise

        self._record_completed(
            plan=plan,
            workflow_name=workflow_name,
            result=result,
            trace=trace,
        )
        logger.info(
            (
                "Solved request trace_id=%s task_family=%s operation=%s workflow=%s "
                "operations=%s resources=%s details=%s"
            ),
            trace.trace_id,
            plan.task_family.value,
            plan.operation.value,
            result.name,
            result.intended_operations,
            result.resource_ids,
            json.dumps(result.details, ensure_ascii=False, default=str),
        )

        return SolveResponse(status="completed")

    def _record_received(self, *, request: SolveRequest, trace: _SolveTrace) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_received(request=request, context=trace.context)

    def _record_planned(
        self,
        *,
        plan,
        workflow_name: str,
        trace: _SolveTrace,
    ) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_planned(
            plan=plan,
            workflow_name=workflow_name,
            context=trace.context,
        )

    def _record_completed(
        self,
        *,
        plan,
        workflow_name: str,
        result,
        trace: _SolveTrace,
    ) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_completed(
            plan=plan,
            workflow_name=workflow_name,
            result=result,
            context=trace.context,
        )

    def _record_api_call_plan(
        self,
        *,
        base_plan,
        workflow_name: str,
        api_call_plan: ApiCallPlan,
        trace: _SolveTrace,
    ) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_api_call_plan(
            base_plan=base_plan,
            workflow_name=workflow_name,
            api_call_plan=api_call_plan,
            context=trace.context,
        )

    def _record_failed(
        self,
        *,
        error: Exception,
        trace: _SolveTrace,
        plan=None,
        workflow_name: str | None = None,
    ) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_failed(
            error=error,
            context=trace.context,
            plan=plan,
            workflow_name=workflow_name,
        )

    def _maybe_record_api_call_plan(
        self,
        *,
        request: SolveRequest,
        plan: TaskPlan,
        workflow,
        workflow_name: str,
        trace: _SolveTrace,
    ) -> None:
        if self._api_call_planner is None:
            return
        if not isinstance(workflow, StubWorkflow):
            return
        try:
            api_call_plan = self._api_call_planner.plan(request.prompt, request.files, plan)
        except Exception as exc:
            logger.warning(
                "ApiCallPlan dry-run planning failed trace_id=%s workflow=%s: %s",
                trace.trace_id,
                workflow_name,
                exc,
            )
            return
        if api_call_plan is None:
            return
        self._record_api_call_plan(
            base_plan=plan,
            workflow_name=workflow_name,
            api_call_plan=api_call_plan,
            trace=trace,
        )
        logger.info(
            "Recorded ApiCallPlan dry-run trace_id=%s workflow=%s steps=%s confidence=%.2f",
            trace.trace_id,
            workflow_name,
            len(api_call_plan.steps),
            api_call_plan.confidence,
        )


def build_default_service() -> SolverService:
    settings = AppSettings.load()
    workflows = WorkflowRegistry(
        workflows=[
            # Creates
            CustomerCreateWorkflow(),
            ProductCreateWorkflow(),
            EmployeeCreateWorkflow(),
            DepartmentCreateWorkflow(),
            ProjectCreateWorkflow(),
            InvoiceCreateWorkflow(),
            InvoicePaymentWorkflow(),
            InvoiceCreditNoteWorkflow(),
            TravelExpenseCreateWorkflow(),
            # Updates
            CustomerUpdateWorkflow(),
            EmployeeUpdateWorkflow(),
            # Deletes
            CustomerDeleteWorkflow(),
            ProductDeleteWorkflow(),
            DepartmentDeleteWorkflow(),
            ProjectDeleteWorkflow(),
            TravelExpenseDeleteWorkflow(),
        ],
        fallback=StubWorkflow(TaskFamily.UNKNOWN),
    )

    return SolverService(
        planner=build_default_planner(settings),
        workflows=workflows,
        client_factory=TripletexClient.from_credentials,
        event_logger=SolveEventLogger(settings.solve_event_log_path),
        api_call_planner=build_default_api_call_planner(settings),
    )


def _resolve_trace(context: SolveRequestContext | None) -> _SolveTrace:
    if context is not None:
        return _SolveTrace(trace_id=context.trace_id, context=context)

    generated_context = SolveRequestContext(trace_id=str(uuid4()))
    return _SolveTrace(trace_id=generated_context.trace_id, context=generated_context)
