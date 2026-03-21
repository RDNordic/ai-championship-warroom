from __future__ import annotations

from types import SimpleNamespace

import pytest

from tripletex_agent.models import AttachmentFile
from tripletex_agent.planner import (
    FallbackPlanner,
    KeywordTaskPlanner,
    LookupExtraction,
    OpenAIPlanner,
    PromptExtraction,
)
from tripletex_agent.task_plan import (
    ActionSemantics,
    CompletionCheck,
    EntityPayload,
    EntityReference,
    Operation,
    TaskFamily,
    TaskPlan,
)


class StaticPlanner:
    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        del prompt, attachments
        return self._plan


class _FakePromptResponses:
    def __init__(self, parsed: PromptExtraction) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed)


class _FakePromptOpenAIClient:
    def __init__(self, *, parsed: PromptExtraction) -> None:
        self.responses = _FakePromptResponses(parsed)


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


def test_planner_marks_invoice_payment_amount_as_excluding_vat() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            'O cliente Floresta Lda (org. nº 864828442) tem uma fatura pendente de '
            '29100 NOK sem IVA por "Design web". Registe o pagamento total desta fatura.'
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.REGISTER_PAYMENT
    assert plan.fields_to_set["paidAmount"] == 29100.0
    assert plan.fields_to_set["paidAmountExcludingVat"] is True


def test_planner_flags_supplier_invoice_prompt_as_incoming() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Hemos recibido la factura INV-2026-8702 del proveedor Sierra SL "
            "(org. nº 933305228) por 6850 NOK con IVA incluido. "
            "El importe corresponde a servicios de oficina (cuenta 6590). "
            "Registre la factura del proveedor con el IVA soportado correcto (25 %)."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE
    assert plan.entities_to_create[0].fields["supplierInvoice"] is True
    assert plan.entities_to_create[0].fields["customerLookup"]["organizationNumber"] == "933305228"


def test_planner_marks_supplier_registration_with_supplier_flags() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Registe o fornecedor Luz do Sol Lda com número de organização 962006930. E-mail: faktura@luzdosollda.no.",
        [],
    )

    assert plan.task_family == TaskFamily.CUSTOMERS_PRODUCTS
    assert plan.operation == Operation.CREATE
    fields = plan.entities_to_create[0].fields
    assert fields["name"] == "Luz do Sol Lda"
    assert fields["organizationNumber"] == "962006930"
    assert fields["isSupplier"] is True
    assert fields["isCustomer"] is False


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


def test_planner_extracts_voucher_lookup_from_returned_payment_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            'Le paiement de Rivière SARL (nº org. 937044488) pour la facture "Design web" '
            "(33050 NOK HT) a été retourné par la banque. "
            "Annulez le paiement afin que la facture affiche à nouveau le montant impayé."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.CORRECTIONS
    assert plan.operation == Operation.REVERSE
    assert plan.entities_to_find[0].entity_type == "voucher"
    assert plan.entities_to_find[0].lookup == {
        "name": "Rivière SARL",
        "organizationNumber": "937044488",
    }


def test_planner_fail_closes_project_lifecycle_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Executez le cycle de vie complet du projet 'Migration Cloud Colline' "
            "(Colline SARL, org. 910455052) : 1) Le projet a un budget de 323050 NOK. "
            "2) Enregistrez le temps : Jules Durand 46 heures et Hugo Durand 46 heures. "
            "3) Enregistrez un cout fournisseur de 36900 NOK de Lumiere SARL "
            "(org. 985264287). 4) Creez une facture client pour le projet."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.UNKNOWN
    assert plan.operation == Operation.UNKNOWN


def test_planner_fail_closes_month_end_close_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Fuhren Sie den Monatsabschluss fur Marz 2026 durch. "
            "Buchen Sie die Rechnungsabgrenzung (2200 NOK pro Monat von Konto 1720 auf Aufwand). "
            "Erfassen Sie die monatliche Abschreibung fur eine Anlage mit Anschaffungskosten "
            "291700 NOK und Nutzungsdauer 5 Jahre. Uberprufen Sie, ob die Saldenbilanz null ergibt. "
            "Buchen Sie ausserdem eine Gehaltsruckstellung."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.UNKNOWN
    assert plan.operation == Operation.UNKNOWN


def test_planner_fail_closes_attachment_led_employee_onboarding_prompt() -> None:
    planner = KeywordTaskPlanner()
    attachments = [
        AttachmentFile(
            filename="files/tilbudsbrev_pt_03.pdf",
            content_base64="aGVsbG8=",
            mime_type="application/pdf",
        )
    ]

    plan = planner.plan(
        (
            "Voce recebeu uma carta de oferta (ver PDF anexo) para um novo funcionario. "
            "Complete a integracao: crie o funcionario, atribua o departamento correto, "
            "configure os detalhes de emprego com percentagem e salario anual, "
            "e configure as horas de trabalho padrao."
        ),
        attachments,
    )

    assert plan.task_family == TaskFamily.UNKNOWN
    assert plan.operation == Operation.UNKNOWN
    assert len(plan.attachment_facts) == 1


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


def test_planner_extracts_order_to_invoice_with_full_payment() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Opprett ein ordre for kunden Strandvik AS (org.nr 911845016) med produkta "
            "Skylagring (7865) til 38500 kr og Datarådgjeving (3949) til 18500 kr. "
            "Konverter ordren til faktura og registrer full betaling."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {
        "customerName": "Strandvik AS",
        "organizationNumber": "911845016",
    }
    assert fields["createOrder"] is True
    assert fields["convertOrderToInvoice"] is True
    assert fields["registerPayment"] is True
    assert len(fields["lines"]) == 2
    assert fields["lines"][0]["productLookup"] == {"name": "Skylagring", "productNumber": "7865"}
    assert fields["lines"][0]["unitPriceExcludingVatCurrency"] == 38500.0
    assert fields["lines"][1]["productLookup"] == {
        "name": "Datarådgjeving",
        "productNumber": "3949",
    }
    assert fields["lines"][1]["unitPriceExcludingVatCurrency"] == 18500.0


def test_planner_extracts_multiline_invoice_prompt_with_vat() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Opprett en faktura til kunden Havbris AS (org.nr 924693576) med tre produktlinjer: "
            "Opplæring (3296) til 5400 kr med 25 % MVA, Skylagring (6620) til 6850 kr med "
            "15 % MVA (næringsmiddel), og Analyserapport (8441) til 13750 kr med 0 % MVA "
            "(avgiftsfri)."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {
        "customerName": "Havbris AS",
        "organizationNumber": "924693576",
    }
    assert len(fields["lines"]) == 3
    assert fields["lines"][0]["productLookup"] == {"name": "Opplæring", "productNumber": "3296"}
    assert fields["lines"][0]["vatPercent"] == 25.0
    assert fields["lines"][1]["productLookup"] == {"name": "Skylagring", "productNumber": "6620"}
    assert fields["lines"][1]["vatPercent"] == 15.0
    assert fields["lines"][2]["productLookup"] == {
        "name": "Analyserapport",
        "productNumber": "8441",
    }
    assert fields["lines"][2]["vatPercent"] == 0.0


def test_planner_distinguishes_create_invoice_from_create_and_send_invoice() -> None:
    planner = KeywordTaskPlanner()

    create_only = planner.plan(
        (
            "Create an invoice to customer ACME AS for 8750 NOK excluding VAT. "
            "Invoice is for Maintenance."
        ),
        [],
    )
    create_and_send = planner.plan(
        (
            "Create and send an invoice to customer ACME AS for 8750 NOK excluding VAT. "
            "Invoice is for Maintenance."
        ),
        [],
    )

    assert create_only.action_semantics.send_to_customer is None
    assert not any(check.kind == "sent_to_customer" for check in create_only.completion_checks)
    assert create_and_send.action_semantics.send_to_customer is True
    assert any(check.kind == "sent_to_customer" for check in create_and_send.completion_checks)


def test_planner_extracts_competition_french_invoice_send_prompt() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        (
            "Créez et envoyez une facture au client Lumière SARL "
            "(nº org. 827689114) de 8750 NOK hors TVA. "
            "La facture concerne Maintenance."
        ),
        [],
    )

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE
    assert plan.action_semantics.send_to_customer is True
    assert any(check.kind == "sent_to_customer" for check in plan.completion_checks)
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {
        "customerName": "Lumière SARL",
        "organizationNumber": "827689114",
    }
    assert "comment" not in fields
    assert "invoiceComment" not in fields
    assert fields["line"]["description"] == "Maintenance"
    assert "productLookup" not in fields["line"]
    assert fields["line"]["count"] == 1.0
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 8750.0


@pytest.mark.parametrize(
    ("prompt", "customer_name"),
    [
        (
            "Opprett og send en faktura til kunden ACME AS for 8750 NOK uten mva. "
            "Fakturaen gjelder Maintenance.",
            "ACME AS",
        ),
        (
            "Opprett og send ei faktura til kunden ACME AS for 8750 NOK utan mva. "
            "Fakturaen gjeld Maintenance.",
            "ACME AS",
        ),
        (
            "Create and send an invoice to customer ACME AS for 8750 NOK excluding VAT. "
            "Invoice is for Maintenance.",
            "ACME AS",
        ),
        (
            "Cree y envie una factura al cliente ACME AS por 8750 NOK sin IVA. "
            "La factura es para Maintenance.",
            "ACME AS",
        ),
        (
            "Crie e envie uma fatura ao cliente ACME AS de 8750 NOK sem IVA. "
            "A fatura é para Maintenance.",
            "ACME AS",
        ),
        (
            "Erstellen und senden Sie eine Rechnung an den Kunden ACME AS uber 8750 NOK "
            "ohne MwSt. Die Rechnung betrifft Maintenance.",
            "ACME AS",
        ),
        (
            "Créez et envoyez une facture au client Lumière SARL (nº org. 827689114) "
            "de 8750 NOK hors TVA. La facture concerne Maintenance.",
            "Lumière SARL",
        ),
    ],
)
def test_planner_extracts_send_intent_for_multilingual_invoice_prompts(
    prompt: str,
    customer_name: str,
) -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(prompt, [])

    assert plan.task_family == TaskFamily.INVOICING
    assert plan.operation == Operation.CREATE
    assert plan.action_semantics.send_to_customer is True
    fields = plan.entities_to_create[0].fields
    assert fields["customerLookup"]["customerName"] == customer_name
    assert fields["line"]["description"] == "Maintenance"
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 8750.0


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


def test_fallback_planner_adds_send_intent_for_logged_french_invoice_prompt() -> None:
    prompt = (
        "Créez et envoyez une facture au client Lumière SARL "
        "(nº org. 827689114) de 8750 NOK hors TVA. "
        "La facture concerne Maintenance."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "customerLookup": {
                        "customerName": "Lumière SARL",
                        "organizationNumber": "827689114",
                    },
                    "line": {
                        "description": "Maintenance",
                        "count": 1.0,
                        "unitPriceExcludingVatCurrency": 8750.0,
                    },
                },
            )
        ],
        action_semantics=ActionSemantics(),
        confidence=0.9,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.action_semantics.send_to_customer is True
    assert any(check.kind == "sent_to_customer" for check in merged_plan.completion_checks)
    fields = merged_plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {
        "customerName": "Lumière SARL",
        "organizationNumber": "827689114",
    }


def test_fallback_planner_recovers_voucher_lookup_from_returned_payment_prompt() -> None:
    prompt = (
        'Le paiement de Rivière SARL (nº org. 937044488) pour la facture "Design web" '
        "(33050 NOK HT) a été retourné par la banque. "
        "Annulez le paiement afin que la facture affiche à nouveau le montant impayé."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.CORRECTIONS,
        operation=Operation.REVERSE,
        entities_to_find=[EntityReference(entity_type="voucher", lookup={})],
        confidence=0.85,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.entities_to_find[0].lookup == {
        "name": "Rivière SARL",
        "organizationNumber": "937044488",
    }


def test_fallback_planner_uses_keyword_plan_when_primary_operation_is_unknown() -> None:
    prompt = (
        "Opprett en faktura til kunden Havbris AS (org.nr 924693576) med tre produktlinjer: "
        "Opplæring (3296) til 5400 kr med 25 % MVA, Skylagring (6620) til 6850 kr med 15 % "
        "MVA, og Analyserapport (8441) til 13750 kr med 0 % MVA."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.UNKNOWN,
        confidence=0.6,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.task_family == TaskFamily.INVOICING
    assert merged_plan.operation == Operation.CREATE
    assert len(merged_plan.entities_to_create[0].fields["lines"]) == 3


def test_fallback_planner_drops_stale_french_product_lookup_trace() -> None:
    prompt = (
        "Créez et envoyez une facture au client Codex Logging Probe 20260320-F "
        "de 8785 NOK hors TVA. "
        "La facture concerne Public solve send validation 20260320 A."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "customerLookup": {"customerName": "Codex Logging Probe 20260320-F"},
                    "line": {
                        "productLookup": {"name": "Public solve send validation 20260320 A"},
                        "unitPriceExcludingVatCurrency": 8785.0,
                    },
                },
            )
        ],
        confidence=0.88,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.action_semantics.send_to_customer is True
    assert any(check.kind == "sent_to_customer" for check in merged_plan.completion_checks)
    fields = merged_plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "Codex Logging Probe 20260320-F"}
    assert fields["line"]["description"] == "Public solve send validation 20260320 A"
    assert fields["line"]["count"] == 1.0
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 8785.0
    assert "productLookup" not in fields["line"]


def test_fallback_planner_drops_amount_vat_comment_from_successful_french_replay() -> None:
    prompt = (
        "Créez et envoyez une facture au client Codex Logging Probe 20260320-F "
        "de 8795 NOK hors TVA. "
        "La facture concerne Public solve send validation 20260320 B."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "comment": "8795 NOK hors TVA",
                    "customerLookup": {"customerName": "Codex Logging Probe 20260320-F"},
                    "line": {
                        "description": "Public solve send validation 20260320 B",
                        "count": 1.0,
                        "unitPriceExcludingVatCurrency": 8795.0,
                    },
                },
            )
        ],
        action_semantics=ActionSemantics(send_to_customer=True),
        completion_checks=[
            CompletionCheck(kind="created", entity_type="invoice", expected_fields=["id"]),
            CompletionCheck(kind="sent_to_customer", entity_type="invoice", expected_fields=[]),
        ],
        confidence=0.86,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.action_semantics.send_to_customer is True
    assert any(check.kind == "sent_to_customer" for check in merged_plan.completion_checks)
    fields = merged_plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {"customerName": "Codex Logging Probe 20260320-F"}
    assert "comment" not in fields
    assert "invoiceComment" not in fields
    assert fields["line"]["description"] == "Public solve send validation 20260320 B"
    assert fields["line"]["count"] == 1.0
    assert fields["line"]["unitPriceExcludingVatCurrency"] == 8795.0


def test_planner_detects_travel_expense_creation() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Register a travel expense for employee Kari Hansen", []
    )

    assert plan.task_family == TaskFamily.TRAVEL_EXPENSES
    assert plan.operation == Operation.CREATE
    assert plan.entities_to_create[0].entity_type == "travel_expense"
    fields = plan.entities_to_create[0].fields
    assert fields["employeeLookup"]["firstName"] == "Kari"
    assert fields["employeeLookup"]["lastName"] == "Hansen"


def test_planner_detects_travel_expense_norwegian() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Registrer en reiseregning for ansatt Ola Nordmann", []
    )

    assert plan.task_family == TaskFamily.TRAVEL_EXPENSES
    assert plan.operation == Operation.CREATE
    assert plan.entities_to_create[0].entity_type == "travel_expense"
    fields = plan.entities_to_create[0].fields
    assert fields["employeeLookup"]["firstName"] == "Ola"
    assert fields["employeeLookup"]["lastName"] == "Nordmann"


def test_planner_extracts_travel_expense_costs() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Register a travel expense report. Hotel 2000 NOK, Meals 500 NOK",
        [],
    )

    assert plan.task_family == TaskFamily.TRAVEL_EXPENSES
    assert plan.operation == Operation.CREATE
    fields = plan.entities_to_create[0].fields
    costs = fields.get("costs")
    assert isinstance(costs, list)
    assert len(costs) == 2
    assert costs[0]["description"] == "Hotel"
    assert costs[0]["amount"] == 2000.0
    assert costs[1]["description"] == "Meals"
    assert costs[1]["amount"] == 500.0


def test_planner_extracts_travel_expense_dates() -> None:
    planner = KeywordTaskPlanner()

    plan = planner.plan(
        "Register a travel expense from 2026-03-15 to 2026-03-17",
        [],
    )

    assert plan.task_family == TaskFamily.TRAVEL_EXPENSES
    assert plan.operation == Operation.CREATE
    fields = plan.entities_to_create[0].fields
    assert fields.get("departureDate") == "2026-03-15"
    assert fields.get("returnDate") == "2026-03-17"


def test_openai_planner_uses_compatible_responses_parse_payload(monkeypatch) -> None:
    parsed = PromptExtraction(
        task_family=TaskFamily.CORRECTIONS,
        operation=Operation.REVERSE,
        primary_entity_type="voucher",
        lookup=LookupExtraction(name="Rivière SARL", organizationNumber="937044488"),
        confidence=0.82,
    )
    fake_client = _FakePromptOpenAIClient(parsed=parsed)
    monkeypatch.setattr(
        "tripletex_agent.planner.OpenAI",
        lambda api_key: fake_client,
    )

    planner = OpenAIPlanner(api_key="placeholder", model="gpt-5-mini")
    plan = planner.plan("Reverse the payment for Rivière SARL", [])

    assert plan.task_family == TaskFamily.CORRECTIONS
    assert plan.operation == Operation.REVERSE
    assert len(fake_client.responses.calls) == 1
    payload = fake_client.responses.calls[0]
    assert payload["model"] == "gpt-5-mini"
    assert payload["text_format"] is PromptExtraction
    assert payload["temperature"] == 0


def test_fallback_planner_fail_closes_project_lifecycle_prompt_when_primary_misroutes() -> None:
    prompt = (
        "Executez le cycle de vie complet du projet 'Migration Cloud Colline' "
        "(Colline SARL, org. 910455052) : 1) Le projet a un budget de 323050 NOK. "
        "2) Enregistrez le temps : Jules Durand 46 heures et Hugo Durand 46 heures. "
        "3) Enregistrez un cout fournisseur de 36900 NOK de Lumiere SARL "
        "(org. 985264287). 4) Creez une facture client pour le projet."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[EntityPayload(entity_type="invoice", fields={})],
        confidence=0.45,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.task_family == TaskFamily.UNKNOWN
    assert merged_plan.operation == Operation.UNKNOWN


def test_fallback_planner_fail_closes_month_end_prompt_when_primary_misroutes() -> None:
    prompt = (
        "Fuhren Sie den Monatsabschluss fur Marz 2026 durch. "
        "Buchen Sie die Rechnungsabgrenzung (2200 NOK pro Monat von Konto 1720 auf Aufwand). "
        "Erfassen Sie die monatliche Abschreibung fur eine Anlage mit Anschaffungskosten "
        "291700 NOK und Nutzungsdauer 5 Jahre. Uberprufen Sie, ob die Saldenbilanz null ergibt. "
        "Buchen Sie ausserdem eine Gehaltsruckstellung."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[EntityPayload(entity_type="invoice", fields={})],
        confidence=0.45,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.task_family == TaskFamily.UNKNOWN
    assert merged_plan.operation == Operation.UNKNOWN


def test_fallback_planner_fail_closes_attachment_led_employee_onboarding_prompt() -> None:
    prompt = (
        "Voce recebeu uma carta de oferta (ver PDF anexo) para um novo funcionario. "
        "Complete a integracao: crie o funcionario, atribua o departamento correto, "
        "configure os detalhes de emprego com percentagem e salario anual, "
        "e configure as horas de trabalho padrao."
    )
    attachments = [
        AttachmentFile(
            filename="files/tilbudsbrev_pt_03.pdf",
            content_base64="aGVsbG8=",
            mime_type="application/pdf",
        )
    ]
    primary_plan = TaskPlan(
        task_family=TaskFamily.EMPLOYEES,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="employee",
                fields={
                    "comments": (
                        "Offer letter attached: files/tilbudsbrev_pt_03.pdf. "
                        "Create the employee and configure employment details."
                    )
                },
            )
        ],
        confidence=0.8,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, attachments)

    assert merged_plan.task_family == TaskFamily.UNKNOWN
    assert merged_plan.operation == Operation.UNKNOWN
    assert len(merged_plan.attachment_facts) == 1


def test_fallback_planner_prefers_order_invoice_payment_keyword_plan_over_payment_only_primary() -> None:
    prompt = (
        "Opprett en ordre for kunden Stormberg AS (org.nr 870531559) med produktene "
        "Vedlikehold (4665) til 35200 kr og Systemutvikling (7431) til 4400 kr. "
        "Konverter ordren til faktura og registrer full betaling."
    )
    primary_plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.REGISTER_PAYMENT,
        entities_to_find=[
            EntityReference(
                entity_type="invoice",
                lookup={
                    "customerLookup": {
                        "customerName": "Stormberg AS",
                        "organizationNumber": "870531559",
                    }
                },
            )
        ],
        fields_to_set={"paidAmount": 39600.0},
        confidence=0.82,
    )
    planner = FallbackPlanner(primary=StaticPlanner(primary_plan), fallback=KeywordTaskPlanner())

    merged_plan = planner.plan(prompt, [])

    assert merged_plan.task_family == TaskFamily.INVOICING
    assert merged_plan.operation == Operation.CREATE
    fields = merged_plan.entities_to_create[0].fields
    assert fields["customerLookup"] == {
        "customerName": "Stormberg AS",
        "organizationNumber": "870531559",
    }
    assert fields["createOrder"] is True
    assert fields["convertOrderToInvoice"] is True
    assert fields["registerPayment"] is True
    assert len(fields["lines"]) == 2
