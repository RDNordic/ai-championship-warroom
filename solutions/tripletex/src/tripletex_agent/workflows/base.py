"""Workflow primitives for deterministic Tripletex execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..client import TripletexClient
from ..task_plan import Operation, TaskFamily, TaskPlan


class WorkflowResult(BaseModel):
    """Structured output from a workflow execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    completed: bool = True
    intended_operations: list[str] = Field(default_factory=list)
    resource_ids: list[int] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionError(RuntimeError):
    """Raised when a concrete workflow cannot safely complete the task."""


class BaseWorkflow(ABC):
    """Base class for all deterministic workflow handlers."""

    family: TaskFamily
    entity_type: str | None = None
    supported_operations: tuple[Operation, ...] = ()

    def supports(self, plan: TaskPlan) -> bool:
        if plan.task_family != self.family:
            return False
        if self.supported_operations and plan.operation not in self.supported_operations:
            return False
        if self.entity_type is not None and plan.primary_entity_type() != self.entity_type:
            return False
        return True

    @abstractmethod
    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        """Run the workflow against the Tripletex API."""
