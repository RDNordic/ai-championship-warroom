"""Workflow primitives for deterministic Tripletex execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from ..client import TripletexClient
from ..task_plan import TaskFamily, TaskPlan


class WorkflowResult(BaseModel):
    """Structured output from a workflow execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    completed: bool = True
    intended_operations: list[str] = Field(default_factory=list)


class BaseWorkflow(ABC):
    """Base class for all deterministic workflow handlers."""

    family: TaskFamily

    def supports(self, plan: TaskPlan) -> bool:
        return plan.task_family == self.family

    @abstractmethod
    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        """Run the workflow against the Tripletex API."""
