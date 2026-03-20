"""Internal structured plan representation used by the agent."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskFamily(str, Enum):
    EMPLOYEES = "employees"
    CUSTOMERS_PRODUCTS = "customers_products"
    INVOICING = "invoicing"
    TRAVEL_EXPENSES = "travel_expenses"
    PROJECTS = "projects"
    CORRECTIONS = "corrections"
    DEPARTMENTS = "departments"
    UNKNOWN = "unknown"


class Operation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    REVERSE = "reverse"
    REGISTER_PAYMENT = "register_payment"
    CREATE_CREDIT_NOTE = "create_credit_note"
    ENABLE_MODULE = "enable_module"
    UNKNOWN = "unknown"


class AttachmentFact(BaseModel):
    """Minimal attachment summary passed into planning and workflows."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    mime_type: str


class EntityReference(BaseModel):
    """A target entity that needs lookup before mutation or linking."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str
    lookup: dict[str, Any] = Field(default_factory=dict)


class EntityPayload(BaseModel):
    """A target entity that will be created or updated by a workflow."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str
    fields: dict[str, Any] = Field(default_factory=dict)


class CompletionCheck(BaseModel):
    """A lightweight postcondition that the workflow should verify."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    entity_type: str
    expected_fields: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """Constrained intermediate representation between LLM and workflows."""

    model_config = ConfigDict(extra="forbid")

    task_family: TaskFamily
    operation: Operation
    entities_to_create: list[EntityPayload] = Field(default_factory=list)
    entities_to_find: list[EntityReference] = Field(default_factory=list)
    fields_to_set: dict[str, Any] = Field(default_factory=dict)
    links_between_entities: list[dict[str, Any]] = Field(default_factory=list)
    attachment_facts: list[AttachmentFact] = Field(default_factory=list)
    completion_checks: list[CompletionCheck] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    def primary_entity_type(self) -> str | None:
        if self.entities_to_create:
            return self.entities_to_create[0].entity_type
        if self.entities_to_find:
            return self.entities_to_find[0].entity_type
        return None

    def primary_payload(self, entity_type: str | None = None) -> EntityPayload | None:
        for payload in self.entities_to_create:
            if entity_type is None or payload.entity_type == entity_type:
                return payload
        return None

    def primary_reference(self, entity_type: str | None = None) -> EntityReference | None:
        for reference in self.entities_to_find:
            if entity_type is None or reference.entity_type == entity_type:
                return reference
        return None

    @classmethod
    def unknown(cls, *, attachment_facts: list[AttachmentFact] | None = None) -> "TaskPlan":
        return cls(
            task_family=TaskFamily.UNKNOWN,
            operation=Operation.UNKNOWN,
            attachment_facts=attachment_facts or [],
            confidence=0.0,
        )
