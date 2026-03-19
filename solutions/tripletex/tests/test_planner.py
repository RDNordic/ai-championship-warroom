from __future__ import annotations

from tripletex_agent.models import AttachmentFile
from tripletex_agent.planner import TaskPlanner
from tripletex_agent.task_plan import Operation, TaskFamily


def test_planner_detects_employee_creation() -> None:
    planner = TaskPlanner()

    plan = planner.plan("Opprett en ansatt med navn Ola Nordmann", [])

    assert plan.task_family == TaskFamily.EMPLOYEES
    assert plan.operation == Operation.CREATE
    assert plan.entities_to_create[0].entity_type == "employee"


def test_planner_detects_invoice_payment() -> None:
    planner = TaskPlanner()

    plan = planner.plan("Register payment for invoice 1001", [])

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.REGISTER_PAYMENT
    assert plan.entities_to_find[0].entity_type == "invoice"


def test_planner_attaches_file_metadata() -> None:
    planner = TaskPlanner()
    files = [
        AttachmentFile(
            filename="receipt.pdf",
            content_base64="aGVsbG8=",
            mime_type="application/pdf",
        )
    ]

    plan = planner.plan("Opprett en reiseregning basert på vedlegget", files)

    assert plan.task_family == TaskFamily.TRAVEL_EXPENSES
    assert len(plan.attachment_facts) == 1
    assert plan.attachment_facts[0].filename == "receipt.pdf"
