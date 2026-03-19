"""Initial deterministic planner used while the richer planner is built."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AttachmentFile
from .task_plan import (
    AttachmentFact,
    CompletionCheck,
    EntityPayload,
    EntityReference,
    Operation,
    TaskFamily,
    TaskPlan,
)


@dataclass(frozen=True)
class IntentRule:
    family: TaskFamily
    operation: Operation
    keywords: tuple[str, ...]


class TaskPlanner:
    """A conservative keyword-based planner used for the initial scaffold."""

    _rules = (
        IntentRule(TaskFamily.INVOICING, Operation.REGISTER_PAYMENT, ("payment", "betaling")),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.CREATE_CREDIT_NOTE,
            ("credit note", "credit memo", "kreditnota"),
        ),
        IntentRule(TaskFamily.CORRECTIONS, Operation.REVERSE, ("reverse", "reverser")),
        IntentRule(TaskFamily.TRAVEL_EXPENSES, Operation.DELETE, ("delete travel", "slett reise")),
        IntentRule(
            TaskFamily.TRAVEL_EXPENSES,
            Operation.CREATE,
            ("travel expense", "expense report", "reiseregning", "reiseutlegg"),
        ),
        IntentRule(TaskFamily.DEPARTMENTS, Operation.ENABLE_MODULE, ("enable module", "aktiver")),
        IntentRule(TaskFamily.DEPARTMENTS, Operation.CREATE, ("department", "avdeling")),
        IntentRule(TaskFamily.PROJECTS, Operation.CREATE, ("project", "prosjekt")),
        IntentRule(TaskFamily.CUSTOMERS_PRODUCTS, Operation.CREATE, ("customer", "kunde")),
        IntentRule(TaskFamily.CUSTOMERS_PRODUCTS, Operation.CREATE, ("product", "produkt")),
        IntentRule(TaskFamily.EMPLOYEES, Operation.UPDATE, ("update employee", "oppdater ansatt")),
        IntentRule(TaskFamily.EMPLOYEES, Operation.CREATE, ("employee", "ansatt")),
        IntentRule(TaskFamily.INVOICING, Operation.CREATE, ("invoice", "faktura")),
    )

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        normalized_prompt = prompt.lower()
        attachment_facts = [
            AttachmentFact(filename=file.filename, mime_type=file.mime_type) for file in attachments
        ]

        for rule in self._rules:
            if any(keyword in normalized_prompt for keyword in rule.keywords):
                return self._build_plan(rule.family, rule.operation, attachment_facts)

        return TaskPlan.unknown(attachment_facts=attachment_facts)

    def _build_plan(
        self,
        family: TaskFamily,
        operation: Operation,
        attachment_facts: list[AttachmentFact],
    ) -> TaskPlan:
        entity_type = self._default_entity_type(family)

        entities_to_create: list[EntityPayload] = []
        entities_to_find: list[EntityReference] = []
        completion_checks: list[CompletionCheck] = []

        if operation == Operation.CREATE and entity_type is not None:
            entities_to_create.append(EntityPayload(entity_type=entity_type))
            completion_checks.append(
                CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
            )
        elif operation in {
            Operation.UPDATE,
            Operation.DELETE,
            Operation.REVERSE,
            Operation.REGISTER_PAYMENT,
            Operation.CREATE_CREDIT_NOTE,
            Operation.ENABLE_MODULE,
        } and entity_type is not None:
            entities_to_find.append(EntityReference(entity_type=entity_type))

        confidence = 0.4 if family == TaskFamily.UNKNOWN else 0.7

        return TaskPlan(
            task_family=family,
            operation=operation,
            entities_to_create=entities_to_create,
            entities_to_find=entities_to_find,
            attachment_facts=attachment_facts,
            completion_checks=completion_checks,
            confidence=confidence,
        )

    @staticmethod
    def _default_entity_type(family: TaskFamily) -> str | None:
        mapping = {
            TaskFamily.EMPLOYEES: "employee",
            TaskFamily.CUSTOMERS_PRODUCTS: "customer_or_product",
            TaskFamily.INVOICING: "invoice",
            TaskFamily.TRAVEL_EXPENSES: "travel_expense",
            TaskFamily.PROJECTS: "project",
            TaskFamily.CORRECTIONS: "voucher_or_entity",
            TaskFamily.DEPARTMENTS: "department_or_module",
        }
        return mapping.get(family)
