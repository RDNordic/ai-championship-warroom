"""Workflow registry and lookup."""

from __future__ import annotations

from collections.abc import Iterable

from ..task_plan import TaskPlan
from .base import BaseWorkflow


class WorkflowRegistry:
    """Selects the first workflow that supports a given task plan."""

    def __init__(self, workflows: Iterable[BaseWorkflow], fallback: BaseWorkflow) -> None:
        self._workflows = list(workflows)
        self._fallback = fallback

    def for_plan(self, plan: TaskPlan) -> BaseWorkflow:
        for workflow in self._workflows:
            if workflow.supports(plan):
                return workflow
        return self._fallback
