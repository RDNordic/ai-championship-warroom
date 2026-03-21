"""Prompt planning for Tripletex tasks."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .config import AppSettings
from .models import AttachmentFile
from .task_plan import (
    ActionSemantics,
    AttachmentFact,
    CompletionCheck,
    EntityPayload,
    EntityReference,
    Operation,
    TaskFamily,
    TaskPlan,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at import time
    OpenAI = None

logger = logging.getLogger(__name__)


class Planner(Protocol):
    """Shared interface for prompt planners."""

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        """Return a constrained task plan for the given prompt."""


@dataclass(frozen=True)
class IntentRule:
    family: TaskFamily
    operation: Operation
    entity_type: str
    keywords: tuple[str, ...]


class AddressExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addressLine1: str | None = None
    addressLine2: str | None = None
    postalCode: str | None = None
    city: str | None = None


class CustomerExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    organizationNumber: str | None = None
    email: str | None = None
    invoiceEmail: str | None = None
    phoneNumber: str | None = None
    phoneNumberMobile: str | None = None
    description: str | None = None
    language: Literal["NO", "EN"] | None = None
    postalAddress: AddressExtraction | None = None
    physicalAddress: AddressExtraction | None = None


class EmployeeExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firstName: str | None = None
    lastName: str | None = None
    email: str | None = None
    employeeNumber: str | None = None
    phoneNumberMobile: str | None = None
    comments: str | None = None
    address: AddressExtraction | None = None


class DepartmentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    names: list[str] | None = None  # for multi-department prompts
    departmentNumber: str | None = None


class ProjectExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    number: str | None = None
    description: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    isInternal: bool | None = None
    isOffer: bool | None = None
    customerName: str | None = None
    customerOrganizationNumber: str | None = None
    projectManagerName: str | None = None
    projectManagerEmail: str | None = None


class ProductExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    number: str | None = None
    description: str | None = None
    priceExcludingVatCurrency: float | None = None
    costExcludingVatCurrency: float | None = None


class TravelExpenseCostExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    amount: float | None = None
    date: str | None = None


class TravelExpenseMileageExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    km: float | None = None
    date: str | None = None
    description: str | None = None


class TravelExpenseExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    departureDate: str | None = None
    returnDate: str | None = None
    employeeName: str | None = None
    employeeEmail: str | None = None
    projectName: str | None = None
    departmentName: str | None = None
    costs: list[TravelExpenseCostExtraction] | None = None
    mileageAllowances: list[TravelExpenseMileageExtraction] | None = None


class InvoiceLineExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productName: str | None = None
    productNumber: str | None = None
    description: str | None = None
    count: float | None = None
    unitPriceExcludingVatCurrency: float | None = None
    vatPercent: float | None = None  # e.g. 25.0, 15.0, 0.0


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoiceId: int | None = None
    invoiceNumber: str | None = None
    customerName: str | None = None
    customerOrganizationNumber: str | None = None
    invoiceDate: str | None = None
    invoiceDueDate: str | None = None
    deliveryDate: str | None = None
    paymentDate: str | None = None
    paidAmount: float | None = None
    paidAmountCurrency: float | None = None
    paymentTypeId: int | None = None
    paymentTypeDescription: str | None = None
    creditNoteDate: str | None = None
    creditNoteEmail: str | None = None
    comment: str | None = None
    invoiceComment: str | None = None
    sendToCustomer: bool | None = None
    line: InvoiceLineExtraction | None = None  # single-line (legacy)
    lines: list[InvoiceLineExtraction] | None = None  # multi-line


class LookupExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str | None = None
    email: str | None = None
    organizationNumber: str | None = None
    number: str | None = None
    firstName: str | None = None
    lastName: str | None = None


class PromptExtraction(BaseModel):
    """Structured extraction returned by the LLM planner."""

    model_config = ConfigDict(extra="forbid")

    task_family: TaskFamily
    operation: Operation
    primary_entity_type: Literal[
        "customer",
        "employee",
        "product",
        "project",
        "department",
        "invoice",
        "travel_expense",
        "voucher",
        "unknown",
    ]
    customer: CustomerExtraction | None = None
    employee: EmployeeExtraction | None = None
    product: ProductExtraction | None = None
    project: ProjectExtraction | None = None
    department: DepartmentExtraction | None = None
    invoice: InvoiceExtraction | None = None
    travel_expense: TravelExpenseExtraction | None = None
    lookup: LookupExtraction | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: str | None = None


class KeywordTaskPlanner:
    """A conservative keyword-based fallback used when LLM planning is unavailable."""

    _rules = (
        IntentRule(
            TaskFamily.INVOICING,
            Operation.CREATE,
            "invoice",
            (
                "convert order to invoice",
                "convert the order to invoice",
                "order to invoice",
                "konverter ordren til faktura",
                "konverter ordre til faktura",
                "konverter ordren til ein faktura",
                "konverter ordre til ein faktura",
            ),
        ),
        IntentRule(
            TaskFamily.DEPARTMENTS,
            Operation.CREATE,
            "department",
            (
                "department",
                "avdeling",
                "add department",
                "register department",
                "registrer avdeling",
                "legg til avdeling",
            ),
        ),
        IntentRule(
            TaskFamily.PROJECTS,
            Operation.CREATE,
            "project",
            (
                "project",
                "prosjekt",
                "new project",
                "sett opp prosjekt",
                "legg til prosjekt",
            ),
        ),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.REGISTER_PAYMENT,
            "invoice",
            (
                "payment",
                "betaling",
                "pay invoice",
                "paid invoice",
                "mark invoice",
                "mark the invoice",
                "betal faktura",
                "betale faktura",
                "innbetaling",
                "register payment",
                "register the payment",
                "registe o pagamento",
                "registre o pagamento",
                "registrar o pagamento",
                "registre el pago",
                "registrar el pago",
            ),
        ),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.CREATE_CREDIT_NOTE,
            "invoice",
            (
                "credit note",
                "credit memo",
                "credit invoice",
                "credit the invoice",
                "kreditnota",
                "krediter",
                "kreditere",
            ),
        ),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.CREATE,
            "invoice",
            (
                "invoice",
                "faktura",
                "facture",
                "factura",
                "fatura",
                "rechnung",
                "issue invoice",
                "send invoice",
                "utsted faktura",
            ),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.CREATE,
            "customer",
            (
                "customer",
                "kunde",
                "supplier",
                "vendor",
                "leverandør",
                "leverandor",
                "fornecedor",
                "proveedor",
                "fournisseur",
                "register customer",
                "register supplier",
                "add supplier",
                "add customer",
                "registrer kunde",
                "registrer leverandør",
                "registrer leverandor",
                "legg til kunde",
            ),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.CREATE,
            "product",
            (
                "product",
                "produkt",
                "register product",
                "add product",
                "registrer produkt",
                "legg til produkt",
            ),
        ),
        IntentRule(
            TaskFamily.TRAVEL_EXPENSES,
            Operation.DELETE,
            "travel_expense",
            (
                "delete travel",
                "remove travel",
                "slett reise",
                "fjern reise",
                "ta bort reise",
                "delete expense",
                "slett utlegg",
            ),
        ),
        IntentRule(
            TaskFamily.TRAVEL_EXPENSES,
            Operation.CREATE,
            "travel_expense",
            ("travel expense", "expense report", "reiseregning", "reiseutlegg"),
        ),
        IntentRule(
            TaskFamily.EMPLOYEES,
            Operation.UPDATE,
            "employee",
            (
                "update employee",
                "edit employee",
                "change employee",
                "modify employee",
                "oppdater ansatt",
                "endre ansatt",
                "rediger ansatt",
            ),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.DELETE,
            "customer",
            (
                "delete customer",
                "remove customer",
                "slett kunde",
                "fjern kunde",
                "ta bort kunde",
            ),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.UPDATE,
            "customer",
            (
                "update customer",
                "edit customer",
                "change customer",
                "modify customer",
                "oppdater kunde",
                "endre kunde",
                "rediger kunde",
            ),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.DELETE,
            "product",
            (
                "delete product",
                "remove product",
                "slett produkt",
                "fjern produkt",
                "ta bort produkt",
            ),
        ),
        IntentRule(
            TaskFamily.DEPARTMENTS,
            Operation.DELETE,
            "department",
            (
                "delete department",
                "remove department",
                "slett avdeling",
                "fjern avdeling",
                "ta bort avdeling",
            ),
        ),
        IntentRule(
            TaskFamily.PROJECTS,
            Operation.DELETE,
            "project",
            (
                "delete project",
                "remove project",
                "slett prosjekt",
                "fjern prosjekt",
                "ta bort prosjekt",
            ),
        ),
        IntentRule(
            TaskFamily.EMPLOYEES,
            Operation.CREATE,
            "employee",
            (
                "employee",
                "ansatt",
                "register employee",
                "add employee",
                "new employee",
                "hire employee",
                "registrer ansatt",
                "legg til ansatt",
                "ansett",
            ),
        ),
        IntentRule(
            TaskFamily.CORRECTIONS,
            Operation.REVERSE,
            "voucher",
            (
                "reverse voucher",
                "reverse the voucher",
                "reverser bilag",
                "reverser bilaget",
                "tilbakefør bilag",
                "reverse posting",
                "reverse entry",
                "credit note voucher",
                "reverse payment",
                "cancel the payment",
                "payment returned",
                "returned by the bank",
                "annuler betalingen",
                "annuller betalingen",
                "betalingen ble returnert",
                "paiement retourne",
                "retourne par la banque",
                "annulez le paiement",
                "revierta el pago",
                "pago devuelto",
                "devuelto por el banco",
                "reverta o pagamento",
                "pagamento devolvido",
                "devolvido pelo banco",
                "zahlung zuruckgebucht",
                "zahlung storniert",
                "storno",
            ),
        ),
    )

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        normalized_prompt = _normalize_prompt_text(_EMAIL_RE.sub("<email>", prompt))
        attachment_facts = _attachment_facts(attachments)

        if _requires_fail_closed_unknown(normalized_prompt, attachment_facts):
            logger.info("Prompt matched unsupported fail-closed family; returning unknown")
            return TaskPlan.unknown(attachment_facts=attachment_facts)

        for rule in self._rules:
            if rule.family != TaskFamily.CORRECTIONS or rule.operation != Operation.REVERSE:
                continue
            if any(_normalize_prompt_text(keyword) in normalized_prompt for keyword in rule.keywords):
                return self._build_rule_plan(
                    prompt=prompt,
                    family=rule.family,
                    operation=rule.operation,
                    entity_type=rule.entity_type,
                    attachment_facts=attachment_facts,
                )

        for rule in self._rules:
            if any(_normalize_prompt_text(keyword) in normalized_prompt for keyword in rule.keywords):
                return self._build_rule_plan(
                    prompt=prompt,
                    family=rule.family,
                    operation=rule.operation,
                    entity_type=rule.entity_type,
                    attachment_facts=attachment_facts,
                )

        return TaskPlan.unknown(attachment_facts=attachment_facts)

    def _build_rule_plan(
        self,
        *,
        prompt: str,
        family: TaskFamily,
        operation: Operation,
        entity_type: str,
        attachment_facts: list[AttachmentFact],
    ) -> TaskPlan:
        payload = self._extract_payload(prompt, entity_type)
        completion_checks: list[CompletionCheck] = []
        entities_to_create: list[EntityPayload] = []
        entities_to_find: list[EntityReference] = []
        fields_to_set: dict[str, object] = {}
        action_semantics = _extract_action_semantics(
            prompt=prompt,
            entity_type=entity_type,
            operation=operation,
        )

        if operation == Operation.CREATE:
            entities_to_create.append(EntityPayload(entity_type=entity_type, fields=payload))
            completion_checks.append(
                CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
            )
            completion_checks.extend(
                _action_completion_checks(
                    entity_type=entity_type,
                    operation=operation,
                    action_semantics=action_semantics,
                )
            )
        elif operation != Operation.UNKNOWN:
            lookup = payload
            if entity_type == "invoice" and operation in (
                Operation.REGISTER_PAYMENT,
                Operation.CREATE_CREDIT_NOTE,
            ):
                lookup, fields_to_set = _extract_invoice_action_components(prompt, operation)
            entities_to_find.append(EntityReference(entity_type=entity_type, lookup=payload))
            if entity_type == "invoice" and operation in (
                Operation.REGISTER_PAYMENT,
                Operation.CREATE_CREDIT_NOTE,
            ):
                entities_to_find[-1] = EntityReference(entity_type=entity_type, lookup=lookup)
            elif operation == Operation.UPDATE:
                fields_to_set = payload

        extracted_lookup = entities_to_find[0].lookup if entities_to_find else {}
        confidence = 0.7 if payload or fields_to_set or extracted_lookup else 0.45
        return TaskPlan(
            task_family=family,
            operation=operation,
            entities_to_create=entities_to_create,
            entities_to_find=entities_to_find,
            fields_to_set=fields_to_set,
            attachment_facts=attachment_facts,
            completion_checks=completion_checks,
            action_semantics=action_semantics,
            confidence=confidence,
        )

    def _extract_payload(self, prompt: str, entity_type: str) -> dict[str, object]:
        if entity_type == "customer":
            return _extract_customer_payload(prompt)
        if entity_type == "employee":
            return _extract_employee_payload(prompt)
        if entity_type == "product":
            return _extract_product_payload(prompt)
        if entity_type == "invoice":
            return _extract_invoice_payload(prompt)
        if entity_type == "department":
            return _extract_department_payload(prompt)
        if entity_type == "project":
            return _extract_project_payload(prompt)
        if entity_type == "travel_expense":
            return _extract_travel_expense_payload(prompt)
        if entity_type == "voucher":
            return _extract_voucher_lookup(prompt)
        return {}


class OpenAIPlanner:
    """Structured extraction planner backed by the OpenAI API."""

    def __init__(self, *, api_key: str, model: str) -> None:
        if OpenAI is None:  # pragma: no cover - depends on installed dependencies
            raise RuntimeError("openai package is required for OpenAIPlanner")

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        attachment_lines = "\n".join(
            f"- {attachment.filename} ({attachment.mime_type})" for attachment in attachments
        )
        attachment_section = (
            f"\nAttachments:\n{attachment_lines}" if attachment_lines else "\nAttachments:\n- none"
        )

        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Convert this Tripletex task prompt into the structured schema.\n"
                        "Only extract facts explicitly stated or strongly implied.\n\n"
                        f"Prompt:\n{prompt}\n"
                        f"{attachment_section}"
                    ),
                },
            ],
            text_format=PromptExtraction,
        )
        extraction = response.output_parsed
        if extraction is None:
            return TaskPlan.unknown(attachment_facts=_attachment_facts(attachments))
        return _plan_from_extraction(extraction, attachments)


class FallbackPlanner:
    """Uses the primary planner, then falls back if it raises or returns unknown."""

    def __init__(self, primary: Planner, fallback: Planner) -> None:
        self._primary = primary
        self._fallback = fallback

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        normalized_prompt = _normalize_prompt_text(_EMAIL_RE.sub("<email>", prompt))
        attachment_facts = _attachment_facts(attachments)

        try:
            plan = self._primary.plan(prompt, attachments)
        except Exception as exc:
            if _requires_fail_closed_unknown(normalized_prompt, attachment_facts):
                logger.info("Unsupported prompt family hit planner error; returning unknown")
                return TaskPlan.unknown(attachment_facts=attachment_facts)
            logger.warning("Primary planner failed; falling back to keyword planner: %s", exc)
            return self._fallback.plan(prompt, attachments)

        if _requires_fail_closed_unknown(normalized_prompt, attachment_facts):
            logger.info("Prompt matched unsupported fail-closed family; returning unknown")
            return TaskPlan.unknown(attachment_facts=attachment_facts)

        if plan.task_family == TaskFamily.UNKNOWN:
            logger.info("Primary planner returned unknown; using keyword fallback")
            return self._fallback.plan(prompt, attachments)

        fallback_plan = self._fallback.plan(prompt, attachments)
        if plan.operation == Operation.UNKNOWN and fallback_plan.operation != Operation.UNKNOWN:
            logger.info("Primary planner returned unknown operation; using keyword fallback")
            return fallback_plan
        if plan.primary_entity_type() is None and fallback_plan.primary_entity_type() is not None:
            logger.info("Primary planner returned no primary entity; using keyword fallback")
            return fallback_plan
        return _merge_with_fallback_plan(plan, fallback_plan)


def build_default_planner(settings: AppSettings) -> Planner:
    fallback = KeywordTaskPlanner()
    if settings.openai_api_key:
        try:
            return FallbackPlanner(
                primary=OpenAIPlanner(api_key=settings.openai_api_key, model=settings.openai_model),
                fallback=fallback,
            )
        except Exception:
            return fallback
    return fallback


def _plan_from_extraction(
    extraction: PromptExtraction, attachments: list[AttachmentFile]
) -> TaskPlan:
    attachment_facts = _attachment_facts(attachments)
    entity_type = extraction.primary_entity_type
    completion_checks: list[CompletionCheck] = []
    entities_to_create: list[EntityPayload] = []
    entities_to_find: list[EntityReference] = []
    fields_to_set: dict[str, object] = {}
    action_semantics = _action_semantics_for_extraction(extraction)

    payload = _payload_for_extraction(extraction)

    if extraction.operation == Operation.CREATE and entity_type != "unknown":
        entities_to_create.append(EntityPayload(entity_type=entity_type, fields=payload))
        completion_checks.append(
            CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
        )
        completion_checks.extend(
            _action_completion_checks(
                entity_type=entity_type,
                operation=extraction.operation,
                action_semantics=action_semantics,
            )
        )

    if extraction.operation == Operation.UPDATE and entity_type != "unknown":
        lookup = _lookup_for_extraction(extraction)
        entities_to_find.append(EntityReference(entity_type=entity_type, lookup=lookup))
        fields_to_set = payload

    if extraction.operation in (Operation.DELETE, Operation.REVERSE) and entity_type != "unknown":
        lookup = _lookup_for_extraction(extraction)
        entities_to_find.append(EntityReference(entity_type=entity_type, lookup=lookup))

    if extraction.operation in (Operation.REGISTER_PAYMENT, Operation.CREATE_CREDIT_NOTE):
        if entity_type == "invoice":
            lookup, fields_to_set = _invoice_lookup_and_fields_from_payload(
                payload, extraction.operation
            )
            entities_to_find.append(EntityReference(entity_type=entity_type, lookup=lookup))

    return TaskPlan(
        task_family=extraction.task_family,
        operation=extraction.operation,
        entities_to_create=entities_to_create,
        entities_to_find=entities_to_find,
        fields_to_set=fields_to_set,
        attachment_facts=attachment_facts,
        completion_checks=completion_checks,
        action_semantics=action_semantics,
        confidence=extraction.confidence,
    )


def _payload_for_extraction(extraction: PromptExtraction) -> dict[str, object]:
    if extraction.primary_entity_type == "customer" and extraction.customer is not None:
        return extraction.customer.model_dump(exclude_none=True)
    if extraction.primary_entity_type == "employee" and extraction.employee is not None:
        return extraction.employee.model_dump(exclude_none=True)
    if extraction.primary_entity_type == "department" and extraction.department is not None:
        return extraction.department.model_dump(exclude_none=True)
    if extraction.primary_entity_type == "project" and extraction.project is not None:
        project_payload = extraction.project.model_dump(exclude_none=True)
        customer_lookup: dict[str, object] = {}
        project_manager_lookup: dict[str, object] = {}
        customer_name = project_payload.pop("customerName", None)
        customer_org = project_payload.pop("customerOrganizationNumber", None)
        project_manager_name = project_payload.pop("projectManagerName", None)
        project_manager_email = project_payload.pop("projectManagerEmail", None)
        if customer_name is not None:
            customer_lookup["customerName"] = customer_name
        if customer_org is not None:
            customer_lookup["organizationNumber"] = customer_org
        if project_manager_name is not None:
            names = project_manager_name.split()
            if names:
                project_manager_lookup["firstName"] = names[0]
            if len(names) > 1:
                project_manager_lookup["lastName"] = " ".join(names[1:])
        if project_manager_email is not None:
            project_manager_lookup["email"] = project_manager_email
        if customer_lookup:
            project_payload["customerLookup"] = customer_lookup
        if project_manager_lookup:
            project_payload["projectManagerLookup"] = project_manager_lookup
        return project_payload
    if extraction.primary_entity_type == "product" and extraction.product is not None:
        return extraction.product.model_dump(exclude_none=True)
    if extraction.primary_entity_type == "travel_expense" and extraction.travel_expense is not None:
        te_payload = extraction.travel_expense.model_dump(exclude_none=True)
        te_employee_lookup: dict[str, object] = {}
        employee_name = te_payload.pop("employeeName", None)
        employee_email = te_payload.pop("employeeEmail", None)
        if employee_name is not None:
            names = employee_name.split()
            if names:
                te_employee_lookup["firstName"] = names[0]
            if len(names) > 1:
                te_employee_lookup["lastName"] = " ".join(names[1:])
        if employee_email is not None:
            te_employee_lookup["email"] = employee_email
        if te_employee_lookup:
            te_payload["employeeLookup"] = te_employee_lookup
        project_name = te_payload.pop("projectName", None)
        if project_name is not None:
            te_payload["projectLookup"] = {"name": project_name}
        department_name = te_payload.pop("departmentName", None)
        if department_name is not None:
            te_payload["departmentLookup"] = {"name": department_name}
        return te_payload
    if extraction.primary_entity_type == "invoice" and extraction.invoice is not None:
        invoice_payload = extraction.invoice.model_dump(exclude_none=True)
        invoice_payload.pop("sendToCustomer", None)
        customer_lookup: dict[str, object] = {}
        customer_name = invoice_payload.pop("customerName", None)
        customer_org = invoice_payload.pop("customerOrganizationNumber", None)
        if customer_name is not None:
            customer_lookup["customerName"] = customer_name
        if customer_org is not None:
            customer_lookup["organizationNumber"] = customer_org
        if customer_lookup:
            invoice_payload["customerLookup"] = customer_lookup

        line_payload = invoice_payload.get("line")
        if isinstance(line_payload, dict):
            product_lookup: dict[str, object] = {}
            product_name = line_payload.pop("productName", None)
            product_number = line_payload.pop("productNumber", None)
            if product_name is not None:
                product_lookup["name"] = product_name
            if product_number is not None:
                product_lookup["productNumber"] = product_number
            if product_lookup:
                line_payload["productLookup"] = product_lookup

        # Multi-line: normalise each line the same way
        lines_payload = invoice_payload.get("lines")
        if isinstance(lines_payload, list):
            for lp in lines_payload:
                if not isinstance(lp, dict):
                    continue
                ml_product_lookup: dict[str, object] = {}
                ml_product_name = lp.pop("productName", None)
                ml_product_number = lp.pop("productNumber", None)
                if ml_product_name is not None:
                    ml_product_lookup["name"] = ml_product_name
                if ml_product_number is not None:
                    ml_product_lookup["productNumber"] = ml_product_number
                if ml_product_lookup:
                    lp["productLookup"] = ml_product_lookup

        payment_type_lookup: dict[str, object] = {}
        payment_type_id = invoice_payload.pop("paymentTypeId", None)
        payment_type_description = invoice_payload.pop("paymentTypeDescription", None)
        if payment_type_id is not None:
            payment_type_lookup["id"] = payment_type_id
        if payment_type_description is not None:
            payment_type_lookup["description"] = payment_type_description
        if payment_type_lookup:
            invoice_payload["paymentTypeLookup"] = payment_type_lookup
        return invoice_payload
    return {}


def _action_semantics_for_extraction(extraction: PromptExtraction) -> ActionSemantics:
    if extraction.primary_entity_type == "invoice" and extraction.invoice is not None:
        return ActionSemantics(send_to_customer=extraction.invoice.sendToCustomer)
    return ActionSemantics()


def _invoice_lookup_and_fields_from_payload(
    payload: dict[str, object],
    operation: Operation,
) -> tuple[dict[str, object], dict[str, object]]:
    lookup: dict[str, object] = {}
    fields: dict[str, object] = {}

    if "invoiceId" in payload:
        lookup["id"] = payload["invoiceId"]
    if "invoiceNumber" in payload:
        lookup["invoiceNumber"] = payload["invoiceNumber"]
    if "invoiceDate" in payload:
        lookup["invoiceDate"] = payload["invoiceDate"]
    if "customerLookup" in payload:
        lookup["customerLookup"] = payload["customerLookup"]

    if operation == Operation.REGISTER_PAYMENT:
        if "paymentDate" in payload:
            fields["paymentDate"] = payload["paymentDate"]
        if "paidAmount" in payload:
            fields["paidAmount"] = payload["paidAmount"]
        if "paidAmountExcludingVat" in payload:
            fields["paidAmountExcludingVat"] = payload["paidAmountExcludingVat"]
        if "paidAmountCurrency" in payload:
            fields["paidAmountCurrency"] = payload["paidAmountCurrency"]
        if "paymentTypeLookup" in payload:
            fields["paymentTypeLookup"] = payload["paymentTypeLookup"]

    if operation == Operation.CREATE_CREDIT_NOTE:
        if "creditNoteDate" in payload:
            fields["creditNoteDate"] = payload["creditNoteDate"]
        if "comment" in payload:
            fields["comment"] = payload["comment"]
        if "creditNoteEmail" in payload:
            fields["creditNoteEmail"] = payload["creditNoteEmail"]

    return lookup, fields


def _extract_action_semantics(
    *,
    prompt: str,
    entity_type: str,
    operation: Operation,
) -> ActionSemantics:
    if entity_type == "invoice" and operation == Operation.CREATE:
        return ActionSemantics(send_to_customer=_extract_send_to_customer_intent(prompt))
    return ActionSemantics()


def _action_completion_checks(
    *,
    entity_type: str,
    operation: Operation,
    action_semantics: ActionSemantics,
) -> list[CompletionCheck]:
    if (
        entity_type == "invoice"
        and operation == Operation.CREATE
        and action_semantics.send_to_customer is True
    ):
        return [CompletionCheck(kind="sent_to_customer", entity_type="invoice")]
    return []


def _lookup_for_extraction(extraction: PromptExtraction) -> dict[str, object]:
    if extraction.lookup is not None:
        return extraction.lookup.model_dump(exclude_none=True)

    payload = _payload_for_extraction(extraction)
    keys = ("name", "email", "organizationNumber", "number", "firstName", "lastName")
    return {key: payload[key] for key in keys if key in payload}


def _attachment_facts(attachments: list[AttachmentFile]) -> list[AttachmentFact]:
    return [
        AttachmentFact(filename=attachment.filename, mime_type=attachment.mime_type)
        for attachment in attachments
    ]


def _merge_with_fallback_plan(primary: TaskPlan, fallback: TaskPlan) -> TaskPlan:
    merged = _sanitize_plan(primary)
    if fallback.task_family != merged.task_family or fallback.operation != merged.operation:
        return merged
    if fallback.primary_entity_type() != merged.primary_entity_type():
        return merged

    update: dict[str, object] = {}

    if merged.entities_to_create and fallback.entities_to_create:
        primary_payload = merged.entities_to_create[0]
        fallback_payload = fallback.entities_to_create[0]
        if primary_payload.entity_type == fallback_payload.entity_type:
            entities_to_create = list(merged.entities_to_create)
            entities_to_create[0] = primary_payload.model_copy(
                update={"fields": _merge_mappings(primary_payload.fields, fallback_payload.fields)}
            )
            update["entities_to_create"] = entities_to_create

    if merged.entities_to_find and fallback.entities_to_find:
        primary_reference = merged.entities_to_find[0]
        fallback_reference = fallback.entities_to_find[0]
        if primary_reference.entity_type == fallback_reference.entity_type:
            entities_to_find = list(merged.entities_to_find)
            entities_to_find[0] = primary_reference.model_copy(
                update={
                    "lookup": _merge_mappings(
                        primary_reference.lookup,
                        fallback_reference.lookup,
                    )
                }
            )
            update["entities_to_find"] = entities_to_find

    if fallback.fields_to_set:
        update["fields_to_set"] = _merge_mappings(merged.fields_to_set, fallback.fields_to_set)

    merged_action_semantics = _merge_action_semantics(
        merged.action_semantics,
        fallback.action_semantics,
    )
    if merged_action_semantics != merged.action_semantics:
        update["action_semantics"] = merged_action_semantics

    merged_completion_checks = _merge_completion_checks(
        merged.completion_checks,
        fallback.completion_checks,
    )
    if merged_completion_checks != merged.completion_checks:
        update["completion_checks"] = merged_completion_checks

    return merged.model_copy(update=update) if update else merged


def _sanitize_plan(plan: TaskPlan) -> TaskPlan:
    update: dict[str, object] = {}

    if plan.entities_to_create:
        update["entities_to_create"] = [
            entity.model_copy(update={"fields": _sanitize_mapping(entity.fields)})
            for entity in plan.entities_to_create
        ]

    if plan.entities_to_find:
        update["entities_to_find"] = [
            entity.model_copy(update={"lookup": _sanitize_mapping(entity.lookup)})
            for entity in plan.entities_to_find
        ]

    if plan.fields_to_set:
        update["fields_to_set"] = _sanitize_mapping(plan.fields_to_set)

    return plan.model_copy(update=update) if update else plan


def _merge_action_semantics(
    primary: ActionSemantics,
    fallback: ActionSemantics,
) -> ActionSemantics:
    send_to_customer = primary.send_to_customer
    if fallback.send_to_customer is not None:
        send_to_customer = fallback.send_to_customer
    return ActionSemantics(send_to_customer=send_to_customer)


def _merge_completion_checks(
    primary: list[CompletionCheck],
    fallback: list[CompletionCheck],
) -> list[CompletionCheck]:
    merged = list(primary)
    seen = {(check.kind, check.entity_type, tuple(check.expected_fields)) for check in merged}
    for check in fallback:
        signature = (check.kind, check.entity_type, tuple(check.expected_fields))
        if signature not in seen:
            merged.append(check)
            seen.add(signature)
    return merged


def _sanitize_mapping(mapping: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in mapping.items():
        normalized = _sanitize_value(key, value)
        if normalized is not None:
            sanitized[key] = normalized
    return sanitized


def _sanitize_value(key: str, value: object) -> object | None:
    if isinstance(value, dict):
        cleaned = _sanitize_mapping(value)
        return cleaned or None

    if key == "organizationNumber":
        if isinstance(value, str) and _is_valid_org_number(value):
            return value
        return None

    return value


def _merge_mappings(primary: dict[str, object], fallback: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for key in primary.keys() | fallback.keys():
        value = _merge_values(key, primary.get(key), fallback.get(key))
        if value is not None:
            merged[key] = value
    return _prune_conflicting_fields(primary, fallback, merged)


def _merge_values(key: str, primary: object | None, fallback: object | None) -> object | None:
    if isinstance(primary, dict) and isinstance(fallback, dict):
        merged = _merge_mappings(primary, fallback)
        return merged or None

    if primary is None:
        return fallback
    if fallback is None:
        return primary

    if key == "organizationNumber":
        if isinstance(primary, str) and _is_valid_org_number(primary):
            return primary
        if isinstance(fallback, str) and _is_valid_org_number(fallback):
            return fallback
        return None

    if isinstance(primary, str) and isinstance(fallback, str):
        if _should_replace_text_value(key, primary, fallback):
            return fallback

    return primary


def _should_replace_text_value(key: str, primary: str, fallback: str) -> bool:
    normalized_primary = " ".join(primary.lower().split())
    normalized_fallback = " ".join(fallback.lower().split())

    if not normalized_fallback:
        return False
    if not normalized_primary:
        return True

    if key in {"name", "customerName", "firstName", "lastName"}:
        if _looks_suspicious_name_text(primary) and not _looks_suspicious_name_text(fallback):
            return True
        if normalized_fallback.startswith(normalized_primary) and len(
            normalized_fallback
        ) > len(normalized_primary):
            return True

    return False


def _looks_suspicious_name_text(value: str) -> bool:
    if _EMAIL_RE.search(value):
        return True
    return bool(
        re.search(
            (
                r"\b(?:invoice comment|fakturakommentar|comment|kommentar|description|"
                r"beskrivelse|project number|prosjektnummer|start date|startdato|"
                r"end date|sluttdato|payment|betaling|department|avdeling)\b"
            ),
            value,
            flags=re.IGNORECASE,
        )
    )


def _prune_conflicting_fields(
    primary: dict[str, object],
    fallback: dict[str, object],
    merged: dict[str, object],
) -> dict[str, object]:
    updated = merged

    product_lookup = merged.get("productLookup")
    description = merged.get("description")
    if (
        isinstance(product_lookup, dict)
        and "productLookup" not in fallback
        and isinstance(description, str)
        and "description" in fallback
    ):
        product_name = product_lookup.get("name")
        if isinstance(product_name, str) and _normalize_text(product_name) == _normalize_text(
            description
        ):
            updated = dict(updated)
            updated.pop("productLookup", None)

    line = updated.get("line")
    if isinstance(line, dict):
        for comment_key in ("comment", "invoiceComment"):
            comment_value = updated.get(comment_key)
            if (
                isinstance(comment_value, str)
                and comment_key not in fallback
                and _is_redundant_invoice_amount_comment(comment_value, line)
            ):
                if updated is merged:
                    updated = dict(updated)
                updated.pop(comment_key, None)

    return updated


def _is_redundant_invoice_amount_comment(comment: str, line: dict[str, object]) -> bool:
    amount = _extract_invoice_amount_phrase_value(comment)
    unit_price = line.get("unitPriceExcludingVatCurrency")
    if amount is None or not isinstance(unit_price, (int, float)):
        return False

    count = line.get("count")
    normalized_count = float(count) if isinstance(count, (int, float)) else 1.0
    normalized_unit_price = float(unit_price)
    return _numbers_match(normalized_unit_price, amount) or _numbers_match(
        normalized_unit_price * normalized_count,
        amount,
    )


def _extract_invoice_amount_phrase_value(value: str) -> float | None:
    match = re.fullmatch(
        (
            r"(?P<amount>\d+(?:[.,]\d+)?)\s*nok\b"
            r"(?:\s*(?:excluding vat|ex vat|hors tva|sin iva|sem iva|uten mva|utan mva|"
            r"ohne mwst))?"
        ),
        _normalize_prompt_text(_clean_extracted_value(value)),
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return _parse_decimal(match.group("amount"))


def _numbers_match(left: float, right: float) -> bool:
    return abs(left - right) < 1e-6


def _build_generic_plan(
    *,
    family: TaskFamily,
    operation: Operation,
    entity_type: str,
    attachment_facts: list[AttachmentFact],
    confidence: float,
) -> TaskPlan:
    entities_to_create: list[EntityPayload] = []
    entities_to_find: list[EntityReference] = []
    completion_checks: list[CompletionCheck] = []

    if operation == Operation.CREATE:
        entities_to_create.append(EntityPayload(entity_type=entity_type))
        completion_checks.append(
            CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
        )
    elif operation != Operation.UNKNOWN:
        entities_to_find.append(EntityReference(entity_type=entity_type))

    return TaskPlan(
        task_family=family,
        operation=operation,
        entities_to_create=entities_to_create,
        entities_to_find=entities_to_find,
        attachment_facts=attachment_facts,
        completion_checks=completion_checks,
        confidence=confidence,
    )


_SYSTEM_PROMPT = """
You are a Tripletex task extractor for an accounting automation service.

You read a user prompt that may be written in Norwegian Bokmal, Nynorsk, English, Spanish,
Portuguese, German, or French.

Your job is to convert the prompt into a strict structured object for the current implementation.

Important rules:
- Only extract facts that are explicitly stated or strongly implied.
- Use Tripletex-style field names when possible.
- If the prompt is outside the currently supported slice, return unknown.
- The currently supported live implementation slice is:
  - create customer
  - update customer (change name, email, phone, address, etc.)
  - delete customer
  - create product
  - delete product
  - create employee
  - update employee (change name, email, phone, comments)
  - create department
  - delete department
  - create project linked to an existing customer
  - delete project
  - create invoice for an existing customer with one line item
  - register invoice payment
  - create credit note for an existing invoice
- create travel expense report
- delete travel expense report
- reverse a voucher/posting (use operation=reverse, primary_entity_type=voucher)
- For voucher reverse tasks, extract the voucher id or voucherNumber into the lookup field.
- If a voucher reverse task only identifies the paid invoice by customer name and/or organization
  number, put those values into lookup.name and lookup.organizationNumber.
- Module activation tasks are not yet implemented.
- For department create tasks with multiple departments (e.g. "create departments X, Y, Z"),
  put all department names into the names list field, not just name.
- For travel expenses, put employee references into employeeName and/or employeeEmail.
- For travel expenses, put cost items into the costs array with description, amount, and date.
- For travel expenses, put mileage items into the mileageAllowances array with km, date, and
  description.
- For travel expenses, put the report title into title.
- For travel expenses, put travel dates into departureDate and returnDate (YYYY-MM-DD format).
- For people, split names into firstName and lastName when possible.
- For projects, put customer references into customerName and/or customerOrganizationNumber.
- For projects, put explicit project manager references into projectManagerName and/or
  projectManagerEmail.
- For invoices, put customer references into customerName and/or customerOrganizationNumber.
- For invoice lines, put product references into productName and/or productNumber.
- For invoice create tasks with a single line, put it in the line field.
- For invoice create tasks with multiple lines (e.g. "tre produktlinjer", "three product lines",
  "plusieurs lignes"), put ALL lines in the lines list instead of line. Leave line null.
- For each invoice line, put product references into productName and/or productNumber,
  and put the VAT percentage (e.g. 25.0, 15.0, 0.0) into vatPercent.
- For invoice create tasks, phrases like "invoice is for", "fakturaen gjelder", "la facture
  concerne", "la factura es para", "a fatura e para", or "die Rechnung betrifft" describe the
  free-text line description unless the prompt explicitly names a product.
- For invoice create tasks, set sendToCustomer=true only when the prompt explicitly asks to send
  the invoice now. Leave it null when the prompt only asks to create or issue the invoice.
- Do not put amount or VAT wording into comment or invoiceComment unless the prompt explicitly
  asks for a comment.
- For invoice payment or credit note tasks, prefer invoiceNumber unless the prompt explicitly says
  invoice id; extract invoiceId only when that wording is explicit.
- For invoice payment tasks, put payment method hints into paymentTypeId and/or
  paymentTypeDescription.
- For credit note tasks, put the credit note date into creditNoteDate.
- If a field is not present, leave it null.
- Confidence should reflect how sure you are that the extraction is correct.
""".strip()

_EMAIL_RE = re.compile(r"(?P<email>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)
_ORG_RE = re.compile(r"\b(?P<org>\d{3}\s?\d{3}\s?\d{3})\b")
_SEND_INTENT_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\bdo not send\b",
    r"\bdon't send\b",
    r"\bwithout sending\b",
    r"\bikke send\b",
    r"\bikkje send\b",
    r"\buten a sende\b",
    r"\bne pas envoyer\b",
    r"\bn[' ]?envoyez pas\b",
    r"\bsans envoyer\b",
    r"\bno enviar\b",
    r"\bsin enviar\b",
    r"\bnao enviar\b",
    r"\bsem enviar\b",
    r"\bnicht senden\b",
    r"\bohne zu senden\b",
)
_SEND_INTENT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bsend\b",
    r"\bsende\b",
    r"\bsender\b",
    r"\bsendt\b",
    r"\benvoyer\b",
    r"\benvoyez\b",
    r"\benvoie\b",
    r"\benviar\b",
    r"\benvie\b",
    r"\benvia\b",
    r"\bsenden\b",
    r"\bsende\b",
    r"\bversenden\b",
    r"\bverschicken\b",
    r"\bdispatch\b",
)


def _extract_customer_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    if _mentions_supplier_party_prompt(prompt):
        payload["isSupplier"] = True
        payload["isCustomer"] = False
    name = _extract_named_value(
        prompt,
        [
            (
                r"(?:customer|kunde|company|selskap)\s+"
                r"(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:opprett|registrer|lag|legg til)\s+(?:en\s+)?kunde"
                r"(?:\s+(?:med navn|som heter))?\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:create|register|add)\s+(?:a|an)\s+customer"
                r"(?:\s+(?:named|called|with name))?\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:supplier|vendor|leverand[oø]r|fornecedor|proveedor|fournisseur)\s+"
                r"(?:named|med navn|with name|som heter|called)?\s*"
                r"(?P<value>.+?)(?=\s+(?:com|with|med)\b|\s*(?:,|$))"
            ),
            (
                r"(?:register|add|create|registrer|legg til|registe|registre|registrar)\s+"
                r"(?:the\s+)?(?:supplier|vendor|leverand[oø]r|fornecedor|proveedor|fournisseur)"
                r"(?:\s+(?:named|called|with name))?\s+"
                r"(?P<value>.+?)(?=\s+(?:com|with|med)\b|\s*(?:,|$))"
            ),
        ],
    )
    if name:
        payload["name"] = _strip_customer_suffixes(name)

    email_match = _EMAIL_RE.search(prompt)
    if email_match:
        payload["email"] = email_match.group("email")

    invoice_email = _extract_named_value(
        prompt,
        [
            (
                r"(?:invoice email|billing email|faktura(?:e-?post| email))\s+"
                r"(?P<value>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})"
            ),
        ],
    )
    if invoice_email:
        payload["invoiceEmail"] = invoice_email

    organization_number = _extract_org_number(prompt)
    if organization_number:
        payload["organizationNumber"] = organization_number

    phone_number = _extract_named_value(
        prompt,
        [
            r"(?:phone|telefon)\s+(?P<value>\+?\d[\d\s-]+)",
        ],
    )
    if phone_number:
        payload["phoneNumber"] = phone_number

    mobile_number = _extract_named_value(
        prompt,
        [
            r"(?:mobile|mobil(?:nummer)?)\s+(?P<value>\+?\d[\d\s-]+)",
        ],
    )
    if mobile_number:
        payload["phoneNumberMobile"] = mobile_number

    language = _extract_named_value(
        prompt,
        [
            r"(?:language|språk)\s+(?P<value>[^,\n]+)",
        ],
    )
    if language:
        normalized_language = _normalize_language(language)
        if normalized_language is not None:
            payload["language"] = normalized_language

    return payload


def _extract_employee_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    full_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:employee|ansatt|new hire)\s+"
                r"(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
            r"(?:create|register|add|hire)\s+(?:(?:a|an)\s+)?employee\s+(?P<value>[^,\n]+)",
            (
                r"(?:ansett|legg til|registrer)\s+(?:en\s+)?ansatt"
                r"(?:\s+(?:med navn|som heter))?\s+(?P<value>[^,\n]+)"
            ),
            r"oppdater\s+ansatt\s+(?P<value>[^,\n]+)",
        ],
    )
    if full_name:
        parts = _strip_person_suffixes(full_name).split()
        if parts:
            payload["firstName"] = parts[0]
        if len(parts) > 1:
            payload["lastName"] = " ".join(parts[1:])

    email_match = _EMAIL_RE.search(prompt)
    if email_match:
        payload["email"] = email_match.group("email")

    employee_number = _extract_named_value(
        prompt,
        [
            r"(?:employee number|ansattnummer)\s+(?P<value>[A-Z0-9._-]+)",
        ],
    )
    if employee_number:
        payload["employeeNumber"] = employee_number

    mobile_number = _extract_named_value(
        prompt,
        [
            r"(?:mobile|mobil(?:nummer)?)\s+(?P<value>\+?\d[\d\s-]+)",
            r"(?:phone|telefon)\s+(?P<value>\+?\d[\d\s-]+)",
        ],
    )
    if mobile_number:
        payload["phoneNumberMobile"] = mobile_number

    comments = _extract_named_value(
        prompt,
        [
            r"(?:comment|kommentar)\s+(?P<value>[^,\n]+)",
        ],
    )
    if comments:
        payload["comments"] = comments

    return payload


def _extract_department_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    name = _extract_named_value(
        prompt,
        [
            (
                r"(?:department|avdeling)\s+"
                r"(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:opprett|registrer|legg til)\s+(?:en\s+)?avdeling"
                r"(?:\s+(?:med navn|som heter))?\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:create|register|add)\s+(?:a|an)\s+department"
                r"(?:\s+(?:named|called|with name))?\s+(?P<value>[^,\n]+)"
            ),
        ],
    )
    if name:
        payload["name"] = _strip_department_suffixes(name)

    department_number = _extract_named_value(
        prompt,
        [
            r"(?:department number|avdelingsnummer)\s+(?P<value>[A-Z0-9._-]+)",
        ],
    )
    if department_number:
        payload["departmentNumber"] = department_number

    return payload


def _extract_product_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    product_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:product|produkt)\s+"
                r"(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:create|register|add)\s+(?:a|an)\s+product"
                r"(?:\s+(?:named|called|with name))?\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:opprett|registrer|legg til)\s+(?:et|et nytt)?\s*produkt"
                r"(?:\s+(?:med navn|som heter))?\s+(?P<value>[^,\n]+)"
            ),
        ],
    )
    if product_name:
        payload["name"] = _strip_product_suffixes(product_name)

    product_number = _extract_named_value(
        prompt,
        [
            r"(?:product number|produktnummer|varenummer)\s+(?P<value>[A-Z0-9._-]+)",
        ],
    )
    if product_number:
        payload["number"] = product_number

    description = _extract_named_value(
        prompt,
        [
            r"(?:description|beskrivelse)\s+(?P<value>[^,\n]+)",
        ],
    )
    if description:
        payload["description"] = description

    price_match = re.search(
        r"(?:price|pris)\s+(?:på\s+|of\s+)?(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if price_match:
        payload["priceExcludingVatCurrency"] = _parse_decimal(price_match.group("value"))

    cost_match = re.search(
        r"(?:cost|kost(?:pris)?)\s+(?:på\s+|of\s+)?(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if cost_match:
        payload["costExcludingVatCurrency"] = _parse_decimal(cost_match.group("value"))

    return payload


def _extract_invoice_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    if _mentions_supplier_invoice_prompt(prompt):
        payload["supplierInvoice"] = True
    customer_lookup: dict[str, object] = {}
    customer_name = _extract_invoice_customer_name(prompt)
    if customer_name:
        customer_lookup["customerName"] = customer_name

    organization_number = _extract_org_number(prompt)
    if organization_number:
        customer_lookup.setdefault("organizationNumber", organization_number)

    if customer_lookup:
        payload["customerLookup"] = customer_lookup

    invoice_date = _extract_named_value(
        prompt,
        [
            r"(?:invoice date|fakturadato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if invoice_date:
        payload["invoiceDate"] = invoice_date

    due_date = _extract_named_value(
        prompt,
        [
            r"(?:due date|forfallsdato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if due_date:
        payload["invoiceDueDate"] = due_date

    delivery_date = _extract_named_value(
        prompt,
        [
            r"(?:delivery date|leveringsdato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if delivery_date:
        payload["deliveryDate"] = delivery_date

    invoice_comment = _extract_named_value(
        prompt,
        [
            r"(?:invoice comment|fakturakommentar)\s+(?P<value>[^,\n]+)",
        ],
    )
    if invoice_comment:
        payload["invoiceComment"] = invoice_comment

    comment = _extract_named_value(
        prompt,
        [
            r"(?<!invoice\s)(?<!faktura\s)(?:comment|kommentar)\s+(?P<value>[^,\n]+)",
        ],
    )
    if comment:
        payload["comment"] = comment

    lines = _extract_structured_invoice_lines(prompt)
    if lines:
        payload["lines"] = lines

    if _mentions_order_to_invoice_conversion(prompt):
        payload["createOrder"] = True
        payload["convertOrderToInvoice"] = True
        if _mentions_register_payment_after_invoice(prompt):
            payload["registerPayment"] = True

    line: dict[str, object] = {}
    product_name = _extract_named_value(
        prompt,
        [
            r"(?:with|med)\s+(?:product|produkt)\s+(?P<value>[^,\n]+)",
            r"(?:product|produkt)\s+(?P<value>[^,\n]+)",
        ],
    )
    if product_name:
        line["productLookup"] = {"name": _strip_invoice_line_suffixes(product_name)}

    product_number = _extract_named_value(
        prompt,
        [
            r"(?:product number|produktnummer|varenummer)\s+(?P<value>[A-Z0-9._-]+)",
        ],
    )
    if product_number:
        line.setdefault("productLookup", {})
        line["productLookup"]["productNumber"] = product_number

    description = _extract_invoice_line_description(prompt)
    if description:
        line["description"] = description

    quantity_match = re.search(
        r"(?:quantity|qty|count|antall|stk)\s+(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if quantity_match:
        line["count"] = _parse_decimal(quantity_match.group("value"))

    price_match = re.search(
        r"(?:unit price|enhetspris|price|pris)\s+(?:på\s+|of\s+)?(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if price_match is None:
        price_match = _search_invoice_amount_excluding_vat(prompt)
    if price_match:
        line["unitPriceExcludingVatCurrency"] = _parse_decimal(price_match.group("value"))

    if line and "count" not in line:
        line["count"] = 1.0

    if line and "lines" not in payload:
        payload["line"] = line

    return payload


def _extract_structured_invoice_lines(prompt: str) -> list[dict[str, object]]:
    matches = list(
        re.finditer(
            (
                r"(?P<name>[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 '&+./-]*?)\s*"
                r"\((?P<number>[A-Z0-9._-]+)\)\s+"
                r"(?:til|for|de|por|uber)\s+"
                r"(?P<price>\d+(?:[.,]\d+)?)\s*(?:kr|nok)\b"
                r"(?:\s+med\s+(?P<vat>\d+(?:[.,]\d+)?)\s*%\s*"
                r"(?:mva|vat|tva|iva|mwst))?"
            ),
            prompt,
            flags=re.IGNORECASE,
        )
    )
    if len(matches) < 2:
        return []

    lines: list[dict[str, object]] = []
    for match in matches:
        line: dict[str, object] = {
            "count": 1.0,
            "unitPriceExcludingVatCurrency": _parse_decimal(match.group("price")),
            "productLookup": {
                "name": _clean_structured_line_name(match.group("name")),
                "productNumber": _clean_extracted_value(match.group("number")),
            },
        }
        vat_raw = match.group("vat")
        if vat_raw is not None:
            line["vatPercent"] = _parse_decimal(vat_raw)
        lines.append(line)

    return lines


def _mentions_order_to_invoice_conversion(prompt: str) -> bool:
    normalized_prompt = _normalize_prompt_text(prompt)
    if not re.search(r"\b(?:order|ordre)\b", normalized_prompt):
        return False
    return bool(
        re.search(
            r"\b(?:convert|konverter)\w*\b.*\b(?:invoice|faktura)\b",
            normalized_prompt,
        )
    )


def _mentions_register_payment_after_invoice(prompt: str) -> bool:
    normalized_prompt = _normalize_prompt_text(prompt)
    if re.search(r"\b(?:full|heil|hele|complete)\s+(?:payment|betaling)\b", normalized_prompt):
        return True
    return bool(
        re.search(
            r"\b(?:register|registrer|mark|betal)\w*\b.*\b(?:payment|betaling|paid|betalt)\b",
            normalized_prompt,
        )
    )


def _requires_fail_closed_unknown(
    normalized_prompt: str,
    attachment_facts: list[AttachmentFact],
) -> bool:
    return (
        _mentions_unsupported_project_lifecycle_prompt(normalized_prompt)
        or _mentions_unsupported_period_close_prompt(normalized_prompt)
        or _mentions_unsupported_employee_attachment_prompt(
            normalized_prompt,
            attachment_facts,
        )
    )


def _mentions_unsupported_project_lifecycle_prompt(normalized_prompt: str) -> bool:
    if not re.search(r"\b(?:project|prosjekt|projet|proyecto|projeto)\b", normalized_prompt):
        return False

    has_lifecycle_phrase = re.search(
        (
            r"\b(?:lifecycle|life cycle|cycle de vie|ciclo de vida|"
            r"ciclo de vida completo|project lifecycle)\b"
        ),
        normalized_prompt,
    )
    has_time_registration = re.search(
        (
            r"\b(?:register|registrer|enregistrer|registre|registrar|registe)\w*\b"
            r".{0,40}\b(?:time|timesheet|hours?|heures?|horas?|timer|temps)\b"
        ),
        normalized_prompt,
    )
    has_supplier_cost = re.search(
        (
            r"\b(?:supplier cost|supplier invoice|vendor bill|cout fournisseur|"
            r"coste del proveedor|custo do fornecedor|leverandorkost)\b|"
            r"\b(?:supplier|vendor|fornecedor|proveedor|fournisseur|leverandor)\b"
            r".{0,40}\b(?:cost|invoice|bill|cout|costo|custo)\b"
        ),
        normalized_prompt,
    )
    has_client_invoice = re.search(
        (
            r"\b(?:client invoice|customer invoice|facture client|factura cliente|"
            r"fatura cliente)\b|"
            r"\b(?:invoice|faktura|facture|factura|fatura|rechnung)\b"
            r".{0,40}\b(?:project|prosjekt|projet|proyecto|projeto)\b"
        ),
        normalized_prompt,
    )

    return bool(
        has_lifecycle_phrase or (has_time_registration and has_supplier_cost and has_client_invoice)
    )


def _mentions_unsupported_period_close_prompt(normalized_prompt: str) -> bool:
    has_period_close = re.search(
        (
            r"\b(?:month[- ]end|month end close|monthly close|period close|closing entries|"
            r"monatsabschluss|periodeavslutning|manedsavslutning)\b"
        ),
        normalized_prompt,
    )
    if not has_period_close:
        return False

    related_signal_count = sum(
        1
        for pattern in (
            r"\b(?:accrual|rechnungsabgrenzung|periodisering|periodization)\b",
            r"\b(?:depreciation|abschreibung|avskrivning)\b",
            r"\b(?:balance sheet|trial balance|saldenbilanz|balanse)\b",
            r"\b(?:salary accrual|gehaltsruckstellung|lonnsavsetning|payroll accrual)\b",
        )
        if re.search(pattern, normalized_prompt)
    )
    return related_signal_count >= 2


def _mentions_unsupported_employee_attachment_prompt(
    normalized_prompt: str,
    attachment_facts: list[AttachmentFact],
) -> bool:
    if not attachment_facts:
        return False

    has_employee_signal = re.search(
        (
            r"\b(?:employee|new employee|new hire|employee onboarding|onboarding|"
            r"funcionario|empregado|empleado|ansatt|mitarbeiter|employe)\b"
        ),
        normalized_prompt,
    )
    if not has_employee_signal:
        return False

    has_attachment_reference = re.search(
        (
            r"\b(?:pdf|attachment|attached|annex|anexo|anexo pdf|vedlegg|"
            r"offer letter|carta de oferta|tilbudsbrev)\b"
        ),
        normalized_prompt,
    )
    if not has_attachment_reference:
        return False

    setup_signal_count = sum(
        1
        for pattern in (
            r"\b(?:department|departamento|avdeling)\b",
            r"\b(?:salary|annual salary|salario anual|salario|lonn)\b",
            r"\b(?:working hours|standard working hours|horas de trabalho|arbeidstid)\b",
            r"\b(?:employment details|detalhes de emprego|integracao|integration)\b",
            r"\b(?:percentage|percentagem|prosent)\b",
        )
        if re.search(pattern, normalized_prompt)
    )
    return setup_signal_count >= 2


def _mentions_supplier_invoice_prompt(prompt: str) -> bool:
    normalized_prompt = _normalize_prompt_text(prompt)

    explicit_patterns = (
        r"\bsupplier invoice\b",
        r"\bpurchase invoice\b",
        r"\bvendor bill\b",
        r"\bincoming invoice\b",
        r"\bleverandorfaktura\b",
        r"\bfactura del proveedor\b",
        r"\bfactura de proveedor\b",
        r"\bfatura do fornecedor\b",
        r"\bfacture fournisseur\b",
    )
    if any(re.search(pattern, normalized_prompt) for pattern in explicit_patterns):
        return True

    has_invoice_word = re.search(
        r"\b(?:invoice|faktura|factura|facture|fatura|rechnung)\b",
        normalized_prompt,
    )
    if not has_invoice_word:
        return False

    has_supplier_word = re.search(
        r"\b(?:supplier|vendor|leverandor|proveedor|fornecedor|fournisseur)\b",
        normalized_prompt,
    )
    if has_supplier_word:
        return True

    has_received_word = re.search(
        r"\b(?:received|mottatt|recibid[oa]|recebid[oa])\b",
        normalized_prompt,
    )
    has_account_word = re.search(r"\b(?:account|cuenta|konto)\b", normalized_prompt)
    return bool(has_received_word and has_account_word)


def _mentions_supplier_party_prompt(prompt: str) -> bool:
    normalized_prompt = _normalize_prompt_text(prompt)
    return bool(
        re.search(
            r"\b(?:supplier|vendor|leverandor|fornecedor|proveedor|fournisseur)\b",
            normalized_prompt,
        )
    )


def _clean_structured_line_name(value: str) -> str:
    cleaned = _clean_extracted_value(value)
    cleaned = re.sub(
        (
            r"^(?:med\s+tre\s+produktlinjer:\s*|med\s+produktlinjer:\s*|"
            r"med\s+produkta\s+|med\s+produkter\s+|og\s+)"
        ),
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_extracted_value(cleaned)


def _extract_invoice_action_components(
    prompt: str, operation: Operation
) -> tuple[dict[str, object], dict[str, object]]:
    lookup = _extract_invoice_lookup(prompt)
    fields: dict[str, object] = {}

    if operation == Operation.REGISTER_PAYMENT:
        payment_date = _extract_named_value(
            prompt,
            [
                (
                    r"(?:payment date|paid on|betalingsdato|betalt(?: på| den)?|on)\s+"
                    r"(?P<value>\d{4}-\d{2}-\d{2})"
                ),
            ],
        )
        if payment_date:
            fields["paymentDate"] = payment_date

        payment_type = _extract_named_value(
            prompt,
            [
                r"(?:payment type|payment method|betalingstype|betalingsmåte)\s+(?P<value>[^,\n]+)",
                r"via\s+(?P<value>[^,\n]+)",
            ],
        )
        if payment_type:
            fields["paymentTypeLookup"] = {
                "description": _strip_payment_type_suffixes(payment_type)
            }

        amount_match = re.search(
            (
                r"(?:paid amount|payment amount|amount|betalt beløp|beløp)\s+"
                r"(?:på\s+|of\s+)?(?P<value>\d+(?:[.,]\d+)?)"
            ),
            prompt,
            flags=re.IGNORECASE,
        )
        if amount_match is None:
            amount_match = re.search(
                r"(?:payment|betaling)\s+(?:of|på)\s+(?P<value>\d+(?:[.,]\d+)?)",
                prompt,
                flags=re.IGNORECASE,
            )
        if amount_match is None:
            amount_match = re.search(
                r"(?:pay|paid|betal)\s+(?P<value>\d+(?:[.,]\d+)?)",
                prompt,
                flags=re.IGNORECASE,
            )
        if amount_match is None:
            amount_match = _search_invoice_amount_excluding_vat(prompt)
        if amount_match:
            fields["paidAmount"] = _parse_decimal(amount_match.group("value"))
            if _search_invoice_amount_excluding_vat(prompt) is not None:
                fields["paidAmountExcludingVat"] = True

        if "paymentTypeLookup" not in fields:
            if re.search(r"\b(?:bank|bankkonto|bank account)\b", prompt, flags=re.IGNORECASE):
                fields["paymentTypeLookup"] = {"query": "bank"}
            elif re.search(r"\b(?:cash|kontant)\b", prompt, flags=re.IGNORECASE):
                fields["paymentTypeLookup"] = {"query": "kontant"}

    if operation == Operation.CREATE_CREDIT_NOTE:
        credit_note_date = _extract_named_value(
            prompt,
            [
                (
                    r"(?:credit note date|credit memo date|kreditnotadato|date|dated|on)\s+"
                    r"(?P<value>\d{4}-\d{2}-\d{2})"
                ),
            ],
        )
        if credit_note_date:
            fields["creditNoteDate"] = credit_note_date

        comment = _extract_named_value(
            prompt,
            [
                r"(?:comment|kommentar)\s+(?P<value>[^,\n]+)",
                r"(?:reason|because|på grunn av|pga)\s+(?P<value>[^,\n]+)",
            ],
        )
        if comment:
            fields["comment"] = comment

        email_match = _EMAIL_RE.search(prompt)
        if email_match:
            fields["creditNoteEmail"] = email_match.group("email")

    return lookup, fields


def _extract_invoice_lookup(prompt: str) -> dict[str, object]:
    lookup: dict[str, object] = {}

    invoice_id = _extract_named_value(
        prompt,
        [
            r"(?:invoice id|fakturaid|faktura id)\s+(?P<value>\d+)",
        ],
    )
    if invoice_id:
        lookup["id"] = int(invoice_id)

    invoice_number = _extract_named_value(
        prompt,
        [
            (
                r"(?:invoice number|invoice no\.?|invoice nr\.?|fakturanummer|"
                r"faktura nr\.?)\s*#?(?P<value>\d+)"
            ),
            r"(?:invoice|faktura)\s*#(?P<value>\d+)",
            r"(?:for|på|on)?\s*(?:invoice|faktura)\s+(?P<value>\d+)",
        ],
    )
    if invoice_number:
        lookup["invoiceNumber"] = invoice_number

    invoice_date = _extract_named_value(
        prompt,
        [
            r"(?:invoice date|fakturadato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if invoice_date:
        lookup["invoiceDate"] = invoice_date

    customer_name = _extract_invoice_customer_name(prompt)
    customer_lookup: dict[str, object] = {}
    if customer_name:
        customer_lookup["customerName"] = customer_name
    organization_number = _extract_org_number(prompt)
    if organization_number:
        customer_lookup.setdefault("organizationNumber", organization_number)
    if customer_lookup:
        lookup["customerLookup"] = customer_lookup

    return lookup


def _extract_voucher_lookup(prompt: str) -> dict[str, object]:
    lookup: dict[str, object] = {}

    voucher_id = _extract_named_value(
        prompt,
        [
            r"(?:voucher id|voucher-id|bilagsid|bilag id)\s+(?P<value>\d+)",
        ],
    )
    if voucher_id:
        lookup["id"] = int(voucher_id)

    voucher_number = _extract_named_value(
        prompt,
        [
            r"(?:voucher number|voucher no\.?|voucher nr\.?|bilagsnummer|bilag nr\.?)\s*#?(?P<value>\d+)",
            r"(?:voucher|bilag)\s*#(?P<value>\d+)",
        ],
    )
    if voucher_number:
        lookup["voucherNumber"] = voucher_number

    customer_name = _extract_named_value(
        prompt,
        [
            (
                r"payment\s+(?:from|of|for)\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|for\s+the\s+invoice\b|for\s+invoice\b|invoice\b|was\b|$))"
            ),
            (
                r"betaling(?:en|a)?\s+(?:fra|for)\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|for\s+faktura\b|faktura(?:en)?\b|ble\b|$))"
            ),
            (
                r"paiement\s+de\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|pour\s+la\s+facture\b|la\s+facture\b|a\b|$))"
            ),
            (
                r"pago\s+de\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|por\s+la\s+factura\b|la\s+factura\b|fue\b|$))"
            ),
            (
                r"pagamento\s+de\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|para\s+a\s+fatura\b|a\s+fatura\b|foi\b|$))"
            ),
            (
                r"zahlung\s+von\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|fur\s+die\s+rechnung\b|die\s+rechnung\b|wurde\b|$))"
            ),
            r"(?:customer|kunde(?:n)?|client|cliente)\s+(?P<value>[^,\n(]+)",
        ],
    )
    if customer_name:
        lookup["name"] = _strip_voucher_customer_suffixes(customer_name)

    organization_number = _extract_org_number(prompt)
    if organization_number:
        lookup["organizationNumber"] = organization_number

    return lookup


def _extract_project_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    project_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:project|prosjekt)\s+"
                r"(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:create|register|add)\s+(?:a|an)\s+project"
                r"(?:\s+(?:named|called|with name))?\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:opprett|registrer|legg til|sett opp)\s+(?:et\s+)?prosjekt"
                r"(?:\s+(?:med navn|som heter))?\s+(?P<value>[^,\n]+)"
            ),
        ],
    )
    if project_name:
        payload["name"] = _strip_project_suffixes(project_name)

    customer_name = _extract_named_value(
        prompt,
        [
            r"(?:for|tilknyttet)\s+(?:customer|kunde)\s+(?P<value>[^,\n]+)",
        ],
    )
    if customer_name:
        payload["customerLookup"] = {"customerName": _strip_project_manager_clause(customer_name)}

    organization_number = _extract_org_number(prompt)
    if organization_number:
        payload.setdefault("customerLookup", {})
        payload["customerLookup"].setdefault("organizationNumber", organization_number)

    project_manager_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:project manager|prosjektleder)\s+"
                r"(?:named|med navn|with name)\s+(?P<value>[^,\n]+)"
            ),
            r"(?:project manager|prosjektleder)\s+(?P<value>[^,\n]+)",
        ],
    )
    if project_manager_name:
        names = _strip_person_suffixes(project_manager_name).split()
        manager_lookup: dict[str, object] = {}
        if names:
            manager_lookup["firstName"] = names[0]
        if len(names) > 1:
            manager_lookup["lastName"] = " ".join(names[1:])
        if manager_lookup:
            payload["projectManagerLookup"] = manager_lookup

    project_number = _extract_named_value(
        prompt,
        [
            r"(?:project number|prosjektnummer)\s+(?P<value>[A-Z0-9._-]+)",
        ],
    )
    if project_number:
        payload["number"] = project_number

    start_date = _extract_named_value(
        prompt,
        [
            r"(?:start date|startdato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if start_date:
        payload["startDate"] = start_date

    end_date = _extract_named_value(
        prompt,
        [
            r"(?:end date|sluttdato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if end_date:
        payload["endDate"] = end_date

    email_matches = _EMAIL_RE.findall(prompt)
    if project_manager_name and email_matches:
        payload.setdefault("projectManagerLookup", {})
        payload["projectManagerLookup"]["email"] = email_matches[-1]

    return payload


def _extract_travel_expense_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}

    # Extract employee name
    employee_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:for|til)\s+(?:employee|ansatt|empleado|empregado|employ[eé]|mitarbeiter)"
                r"\s+(?P<value>[^,\n]+)"
            ),
            (
                r"(?:employee|ansatt|empleado|empregado|employ[eé]|mitarbeiter)"
                r"\s+(?:named|med navn|with name|som heter|called)\s+(?P<value>[^,\n]+)"
            ),
        ],
    )
    if employee_name:
        names = _strip_person_suffixes(employee_name).split()
        employee_lookup: dict[str, object] = {}
        if names:
            employee_lookup["firstName"] = names[0]
        if len(names) > 1:
            employee_lookup["lastName"] = " ".join(names[1:])
        if employee_lookup:
            payload["employeeLookup"] = employee_lookup

    # Extract title/description
    title = _extract_named_value(
        prompt,
        [
            r"(?:title|tittel|titulo|titre)\s+(?P<value>[^,\n]+)",
            r"(?:description|beskrivelse)\s+(?P<value>[^,\n]+)",
        ],
    )
    if title:
        payload["title"] = title

    # Extract departure date
    departure_date = _extract_named_value(
        prompt,
        [
            r"(?:departure|avreise|from|fra|del|du|von|ab)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if departure_date:
        payload["departureDate"] = departure_date

    # Extract return date
    return_date = _extract_named_value(
        prompt,
        [
            r"(?:return|retur|to|til|al|au|bis)\s+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
    )
    if return_date:
        payload["returnDate"] = return_date

    # Extract cost items from prompt
    costs: list[dict[str, object]] = []
    cost_matches = re.finditer(
        r"(?P<description>[A-Za-zÀ-ÿ\s]+?)\s+(?P<amount>\d+(?:[.,]\d+)?)\s*(?:NOK|kr)\b",
        prompt,
        flags=re.IGNORECASE,
    )
    for match in cost_matches:
        desc = match.group("description").strip()
        amount = _parse_decimal(match.group("amount"))
        if desc and amount > 0:
            costs.append({"description": desc, "amount": amount})
    if costs:
        payload["costs"] = costs

    # Extract email for employee lookup
    email_match = _EMAIL_RE.search(prompt)
    if email_match and "employeeLookup" not in payload:
        payload["employeeLookup"] = {"email": email_match.group("email")}

    return payload


def _extract_named_value(prompt: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _clean_extracted_value(match.group("value"))
    return None


def _clean_extracted_value(value: str) -> str:
    cleaned = value.strip().strip(" .,:;\"'")
    return cleaned


def _strip_suffixes(value: str, stop_patterns: list[str]) -> str:
    cleaned = value
    for pattern in stop_patterns:
        cleaned = re.split(pattern, cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    return _clean_extracted_value(cleaned)


def _strip_project_manager_clause(value: str) -> str:
    cleaned = re.split(
        r"\b(?:project manager|prosjektleder)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_extracted_value(cleaned)


def _parse_decimal(value: str) -> float:
    return float(value.replace(",", "."))


def _extract_invoice_customer_name(prompt: str) -> str | None:
    customer_name = _extract_named_value(
        prompt,
        [
            (
                r"(?:for|to)\s+(?:customer|kunde(?:n)?)\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|for\s+\d+(?:[.,]\d+)?\s*nok\b|invoice\s+(?:is\s+)?for\b|$))"
            ),
            (
                r"til\s+kunden?\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|for\s+\d+(?:[.,]\d+)?\s*nok\b|faktura(?:en)?\s+gjel(?:der|d)\b|$))"
            ),
            (
                r"au\s+client\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|de\s+\d+(?:[.,]\d+)?\s*nok\b|la\s+facture\s+concerne\b|$))"
            ),
            (
                r"al\s+cliente\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|por\s+\d+(?:[.,]\d+)?\s*nok\b|la\s+factura\s+(?:es|se\s+refiere)\b|$))"
            ),
            (
                r"ao\s+cliente\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|de\s+\d+(?:[.,]\d+)?\s*nok\b|a\s+fatura\s+(?:e|é|refere-se)\b|$))"
            ),
            (
                r"an\s+den\s+kunden\s+(?P<value>.+?)"
                r"(?=\s*(?:\(|uber\s+\d+(?:[.,]\d+)?\s*nok\b|die\s+rechnung\s+betrifft\b|$))"
            ),
        ],
    )
    if customer_name:
        return _strip_invoice_customer_suffixes(customer_name)
    return None


def _extract_invoice_line_description(prompt: str) -> str | None:
    description = _extract_named_value(
        prompt,
        [
            r"(?:line description|invoice line|description|beskrivelse)\s+(?P<value>[^,\n]+)",
            r"(?:invoice\s+(?:is\s+)?for|faktura(?:en)?\s+gjel(?:der|d))\s+(?P<value>[^,\n.]+)",
            r"la\s+facture\s+concerne\s+(?P<value>[^,\n.]+)",
            r"la\s+factura\s+(?:es\s+para|es|se\s+refiere(?:\s+a)?)\s+(?P<value>[^,\n.]+)",
            r"a\s+fatura\s+(?:e|é|refere-se)\s+(?:para\s+)?(?P<value>[^,\n.]+)",
            r"die\s+rechnung\s+betrifft\s+(?P<value>[^,\n.]+)",
        ],
    )
    if description:
        return _strip_invoice_line_suffixes(description)
    return None


def _search_invoice_amount_excluding_vat(prompt: str) -> re.Match[str] | None:
    return re.search(
        (
            r"(?:for|de|por|uber)\s+(?P<value>\d+(?:[.,]\d+)?)\s*nok\b"
            r"(?:\s*(?:excluding vat|ex vat|hors tva|sin iva|sem iva|uten mva|utan mva|"
            r"ohne mwst))"
        ),
        _normalize_prompt_text(prompt),
        flags=re.IGNORECASE,
    )


def _strip_product_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:and|og)\s+(?:product number|produktnummer|varenummer|price|pris|"
                r"cost|kost(?:pris)?|description|beskrivelse)\b"
            ),
            (
                r"\b(?:product number|produktnummer|varenummer|price|pris|cost|"
                r"kost(?:pris)?|description|beskrivelse)\b"
            ),
        ],
    )


def _strip_customer_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:and|og)\s+(?:e-?post|email|invoice email|billing email|"
                r"faktura(?:e-?post| email)|organization number|organisasjonsnummer|orgnr|"
                r"phone|telefon|mobile|mobil(?:nummer)?|language|språk|description|beskrivelse)\b"
            ),
            (
                r"\b(?:e-?post|email|invoice email|billing email|faktura(?:e-?post| email)|"
                r"organization number|organisasjonsnummer|orgnr|phone|telefon|mobile|"
                r"mobil(?:nummer)?|language|språk|description|beskrivelse)\b"
            ),
            r"\b(?:numero de organiza(?:c(?:ao|ão)|cion)|n[úu]mero de organiza(?:ç|c)[ãa]o|n[úu]mero de organizaci[oó]n)\b",
        ],
    )


def _strip_person_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:and|og)\s+(?:email|e-?post|employee number|ansattnummer|mobile|"
                r"mobil(?:nummer)?|phone|telefon|comment|kommentar|department|avdeling|"
                r"project number|prosjektnummer|start date|startdato|end date|sluttdato)\b"
            ),
            (
                r"\b(?:email|e-?post|employee number|ansattnummer|mobile|mobil(?:nummer)?|"
                r"phone|telefon|comment|kommentar|department|avdeling|project number|"
                r"prosjektnummer|start date|startdato|end date|sluttdato)\b"
            ),
            _EMAIL_RE.pattern,
        ],
    )


def _strip_department_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            r"\b(?:and|og)\s+(?:department number|avdelingsnummer)\b",
            r"\b(?:department number|avdelingsnummer)\b",
        ],
    )


def _strip_invoice_customer_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:with|med)\s+(?:product|produkt)\b|"
                r"\b(?:project manager|prosjektleder)\b|"
                r"\b(?:invoice date|fakturadato|due date|forfallsdato|delivery date|leveringsdato|"
                r"comment|kommentar|invoice comment|fakturakommentar|product number|"
                r"produktnummer|varenummer|price|pris|quantity|qty|count|antall|stk|"
                r"line description|invoice line|description|beskrivelse|organization number|"
                r"organisasjonsnummer|org(?:anization)?\s*(?:number|nr|no)?|la\s+facture\s+concerne|"
                r"la\s+factura\s+(?:es|se\s+refiere)|a\s+fatura\s+(?:e|refere-se)|"
                r"die\s+rechnung\s+betrifft|faktura(?:en)?\s+gjel(?:der|d))\b|"
                r"(?:for|de|por|uber)\s+\d+(?:[.,]\d+)?\s*nok\b"
            ),
        ],
    )


def _strip_invoice_line_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:and|og)\s+(?:product number|produktnummer|varenummer|price|pris|"
                r"unit price|enhetspris|quantity|qty|count|antall|stk|description|"
                r"beskrivelse)\b"
            ),
            (
                r"\b(?:product number|produktnummer|varenummer|price|pris|unit price|"
                r"enhetspris|quantity|qty|count|antall|stk|description|beskrivelse)\b"
            ),
        ],
    )


def _strip_voucher_customer_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:for|pour|por|para|fur)\s+(?:the\s+)?(?:invoice|facture|factura|fatura|rechnung)\b|"
                r"\b(?:invoice|facture|factura|fatura|rechnung)\b|"
                r"\b(?:was|ble|fue|foi|wurde)\b"
            ),
        ],
    )


def _strip_payment_type_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:paid amount|payment amount|amount|betalt beløp|beløp|payment date|"
                r"betalingsdato|date|dato)\b"
            ),
        ],
    )


def _strip_project_suffixes(value: str) -> str:
    return _strip_suffixes(
        value,
        [
            (
                r"\b(?:for|tilknyttet)\s+(?:customer|kunde)\b|"
                r"\b(?:project manager|prosjektleder)\b|"
                r"\b(?:project number|prosjektnummer|start date|startdato|end date|sluttdato)\b"
            ),
        ],
    )


def _extract_send_to_customer_intent(prompt: str) -> bool | None:
    normalized_prompt = _normalize_prompt_text(prompt)

    for pattern in _SEND_INTENT_NEGATIVE_PATTERNS:
        if re.search(pattern, normalized_prompt, flags=re.IGNORECASE):
            return False

    for pattern in _SEND_INTENT_POSITIVE_PATTERNS:
        if re.search(pattern, normalized_prompt, flags=re.IGNORECASE):
            return True

    return None


def _normalize_prompt_text(prompt: str) -> str:
    decomposed = unicodedata.normalize("NFKD", prompt)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.lower()


def _extract_org_number(prompt: str) -> str | None:
    labeled = _extract_named_value(
        prompt,
        [
            r"(?:organization number|organisasjonsnummer|orgnr)\s+(?P<value>\d{3}\s?\d{3}\s?\d{3})",
        ],
    )
    if labeled:
        return labeled
    org_match = _ORG_RE.search(prompt)
    if org_match:
        return org_match.group("org")
    return None


def _is_valid_org_number(value: str) -> bool:
    return bool(re.fullmatch(r"\d{3}\s?\d{3}\s?\d{3}", value.strip()))


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _normalize_language(value: str) -> Literal["NO", "EN"] | None:
    normalized = " ".join(value.lower().split())
    if normalized in {"no", "nb", "nn", "norsk", "norwegian"}:
        return "NO"
    if normalized in {"en", "engelsk", "english"}:
        return "EN"
    return None
