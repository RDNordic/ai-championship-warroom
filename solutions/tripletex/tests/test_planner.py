from __future__ import annotations

from tripletex_agent.models import AttachmentFile
from tripletex_agent.planner import KeywordTaskPlanner
from tripletex_agent.task_plan import Operation, TaskFamily


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
