"""Stub workflows used while the production handlers are built out."""

from __future__ import annotations

import logging

from ..client import TripletexClient
from ..task_plan import TaskFamily, TaskPlan
from .base import BaseWorkflow, WorkflowResult

logger = logging.getLogger(__name__)


class StubWorkflow(BaseWorkflow):
    """A no-op workflow that preserves the service shape during scaffolding."""

    def __init__(self, family: TaskFamily, *, name: str | None = None) -> None:
        self.family = family
        self._name = name or f"{family.value}_stub"

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        del client

        intended_operations = [f"{plan.task_family.value}:{plan.operation.value}"]
        for entity in plan.entities_to_create:
            intended_operations.append(f"create:{entity.entity_type}")
        for entity in plan.entities_to_find:
            intended_operations.append(f"find:{entity.entity_type}")

        logger.warning(
            "Executing stub workflow family=%s operation=%s intended_operations=%s",
            plan.task_family.value,
            plan.operation.value,
            intended_operations,
        )

        return WorkflowResult(name=self._name, intended_operations=intended_operations)
