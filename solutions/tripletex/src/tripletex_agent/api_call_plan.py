"""Structured dry-run API call planning models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .task_plan import Operation, TaskFamily


class ApiCallStep(BaseModel):
    """One proposed Tripletex API call in a dry-run plan."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    purpose: str
    method: Literal["GET", "POST", "PUT", "DELETE"]
    path: str
    params: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    save_response_fields_as: dict[str, str] = Field(default_factory=dict)


class ApiCallCompletionCheck(BaseModel):
    """What the planner expects to verify if this plan were executed."""

    model_config = ConfigDict(extra="forbid")

    description: str
    kind: Literal["resource_created", "response_field", "manual_review"] = "manual_review"
    field_path: str | None = None
    expected_value: str | int | float | bool | None = None


class ApiCallPlan(BaseModel):
    """Dry-run execution plan proposed by the LLM for unsupported tasks."""

    model_config = ConfigDict(extra="forbid")

    dry_run_only: Literal[True] = True
    task_family: TaskFamily
    operation: Operation
    primary_goal: str
    steps: list[ApiCallStep] = Field(default_factory=list)
    completion_checks: list[ApiCallCompletionCheck] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
