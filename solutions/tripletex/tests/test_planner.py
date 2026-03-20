from __future__ import annotations

from tripletex_agent.models import AttachmentFile
from tripletex_agent.planner import FallbackPlanner, KeywordTaskPlanner
from tripletex_agent.task_plan import EntityPayload, Operation, TaskFamily, TaskPlan


class StaticPlanner:
    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        del prompt, attachments
        return self._plan


def test_planner_detects_employee_creation() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan("Opprett en ansatt med navn Ola Nordmann", [])

    assert plan.task_family == TaskFamily.EMPLOYEES
    assert plan.operation == Operation.CREATE
    assert plan.entities_to_create[0].entity_type == "employee"


def test_planner_detects_invoice_payment() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan("Register payment for invoice 1001", [])

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.REGISTER_PAYMENT
    assert plan.entities_to_find[0].entity_type == "invoice"
    assert plan.entities_to_find[0].lookup == {"invoiceNumber": "1001"}


def test_planner_extracts_invoice_payment_payload() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Register payment for invoice 1001 payment date 2026-03-20 "
            "payment type Betalt til bank amount 1250"
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.entities_to_find[0].lookup == {"invoiceNumber": "1001"}
    assert plan.fields_to_set["paymentDate"] == "2026-03-20"
    assert plan.fields_to_set["paidAmount"] == 1250.0
    assert plan.fields_to_set["paymentTypeLookup"] == {"description": "Betalt til bank"}


def test_planner_extracts_credit_note_payload() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Create credit note for invoice 1001 date 2026-03-20 comment Customer cancellation",
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE_CREDIT_NOTE
    assert plan.entities_to_find[0].lookup == {"invoiceNumber": "1001"}
    assert plan.fields_to_set["creditNoteDate"] == "2026-03-20"
    assert plan.fields_to_set["comment"] == "Customer cancellation"


def test_planner_extracts_product_payload() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Opprett et produkt med navn Konsulenttime produktnummer CONS-001 pris 1500 kost 900",
        [],
    )

    assert plan.task_family == TaskFamily.CUSTOMERS_PRODUCTS
    fields = plan.entities_to_create[0].fields
    assert fields["name"] == "Konsulenttime"
    assert fields["number"] == "CONS-001"
    assert fields["priceExcludingVatCurrency"] == 1500.0
    assert fields["costExcludingVatCurrency"] == 900.0


def test_planner_extracts_invoice_payload() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Opprett en faktura for kunde ACME AS med produkt Konsulenttime antall 2 pris 1500",
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "ACME AS"}
    assert fields["line"]["productLookup"] == {"name": "Konsulenttime"}
    assert fields["line"]["count"] == 2.0
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 1500.0


def test_planner_attaches_file_metadata() -> None:
    planner = KeywordTaskPlanner()
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


def test_planner_extracts_project_manager_lookup_for_project() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Opprett et prosjekt med navn Migrering for kunde ACME AS prosjektleder Ola Nordmann",
        [],
    )

    assert plan.task_family == TaskFamily.PROJECTS
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "ACME AS"}
    assert fields["projectManagerLookup"] == {"firstName": "Ola", "lastName": "Nordmann"}


def test_planner_extracts_customer_name_without_trailing_email_fields() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Add customer named ACME Automation AS and email finance@acme.test "
            "organization number 123 456 789 language English"
        ),
        [],
    )

    assert plan.task_family == TaskFamily.CUSTOMERS_PRODUCTS
    fields = plan.entities_to_create[0].fields
    assert fields["name"] == "ACME Automation AS"
    assert fields["email"] == "finance@acme.test"
    assert fields["organizationNumber"] == "123 456 789"
    assert fields["language"] == "EN"


def test_planner_extracts_employee_payload_from_hire_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Hire employee Kari Nordmann email kari@acme.test "
            "employee number EMP-42 mobile +47 900 00 000"
        ),
        [],
    )

    assert plan.task_family == TaskFamily.EMPLOYEES
    fields = plan.entities_to_create[0].fields
    assert fields["firstName"] == "Kari"
    assert fields["lastName"] == "Nordmann"
    assert fields["email"] == "kari@acme.test"
    assert fields["employeeNumber"] == "EMP-42"
    assert fields["phoneNumberMobile"] == "+47 900 00 000"


def test_planner_extracts_invoice_payment_from_mark_paid_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Mark invoice #1001 as paid on 2026-03-20 via Betalt til bank amount 1250",
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.REGISTER_PAYMENT
    assert plan.entities_to_find[0].lookup == {"invoiceNumber": "1001"}
    assert plan.fields_to_set["paymentDate"] == "2026-03-20"
    assert plan.fields_to_set["paidAmount"] == 1250.0
    assert plan.fields_to_set["paymentTypeLookup"] == {"description": "Betalt til bank"}


def test_planner_extracts_credit_note_from_credit_invoice_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Credit invoice #1001 on 2026-03-20 because Customer cancellation",
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE_CREDIT_NOTE
    assert plan.entities_to_find[0].lookup == {"invoiceNumber": "1001"}
    assert plan.fields_to_set["creditNoteDate"] == "2026-03-20"
    assert plan.fields_to_set["comment"] == "Customer cancellation"


def test_planner_extracts_invoice_description_line_variant() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Issue invoice for customer ACME AS line description Consulting services "
            "qty 2 unit price 1500 invoice comment Phase 1"
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "ACME AS"}
    assert fields["invoiceComment"] == "Phase 1"
    assert "comment" not in fields
    assert fields["line"]["description"] == "Consulting services"
    assert fields["line"]["count"] == 2.0
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 1500.0


def test_planner_extracts_project_variant_with_manager_email_and_dates() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Set up project named Migration Sprint for customer ACME AS "
            "project manager Ola Nordmann ola.nordmann@acme.test "
            "project number PROJ-42 start date 2026-03-20"
        ),
        [],
    )

    assert plan.task_family == TaskFamily.PROJECTS
    fields = plan.entities_to_create[0].fields
    assert fields["name"] == "Migration Sprint"
    assert fields["customerLookup"] == {"customerName": "ACME AS"}
    assert fields["projectManagerLookup"] == {
        "firstName": "Ola",
        "lastName": "Nordmann",
        "email": "ola.nordmann@acme.test",
    }
    assert fields["number"] == "PROJ-42"
    assert fields["startDate"] == "2026-03-20"


def test_planner_extracts_department_number_without_polluting_name() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan("Add department named Sales Ops department number 240", [])

    assert plan.task_family == TaskFamily.DEPARTMENTS
    fields = plan.entities_to_create[0].fields
    assert fields["name"] == "Sales Ops"
    assert fields["departmentNumber"] == "240"


def test_fallback_planner_merges_keyword_cleanup_into_primary_plan() -> None:
    prompt = (
        "Issue invoice for customer Codex Conversational Kunde 20260320-B "
        "line description Conversational validation qty 2 unit price 1500 "
        "invoice comment Phase 1"
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "invoiceComment": "Phase 1",
                    "line": {
                        "description": "Conversational validation",
                        "count": 2.0,
                        "unitPriceExcludingVatCurrency": 1500.0,
                    },
                    "customerLookup": {
                        "customerName": "Codex Conversational Kunde",
                        "organizationNumber": "20260320-B",
                    },
                },
            )
        ],
        confidence=0.78,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    fields = merged_plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "Codex Conversational Kunde 20260320-B"}


def test_fallback_planner_drops_hallucinated_product_lookup_for_description_line() -> None:
    prompt = (
        "Issue invoice for customer Codex Conversational Kunde 20260320-B "
        "line description Conversational validation qty 2 unit price 1500 "
        "invoice comment Phase 1"
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "customerLookup": {"customerName": "Codex Conversational Kunde 20260320-B"},
                    "line": {
                        "description": "Conversational validation",
                        "productLookup": {"name": "Conversational validation"},
                        "count": 2.0,
                        "unitPriceExcludingVatCurrency": 1500.0,
                    },
                },
            )
        ],
        confidence=0.85,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    line = merged_plan.entities_to_create[0].fields["line"]
    assert line["description"] == "Conversational validation"
    assert "productLookup" not in line
