"""Prompt planning for Tripletex tasks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .config import AppSettings
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


class InvoiceLineExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productName: str | None = None
    productNumber: str | None = None
    description: str | None = None
    count: float | None = None
    unitPriceExcludingVatCurrency: float | None = None


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
    line: InvoiceLineExtraction | None = None


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
    lookup: LookupExtraction | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: str | None = None


class KeywordTaskPlanner:
    """A conservative keyword-based fallback used when LLM planning is unavailable."""

    _rules = (
        IntentRule(
            TaskFamily.DEPARTMENTS,
            Operation.CREATE,
            "department",
            ("department", "avdeling"),
        ),
        IntentRule(TaskFamily.PROJECTS, Operation.CREATE, "project", ("project", "prosjekt")),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.REGISTER_PAYMENT,
            "invoice",
            ("payment", "betaling"),
        ),
        IntentRule(
            TaskFamily.INVOICING,
            Operation.CREATE_CREDIT_NOTE,
            "invoice",
            ("credit note", "credit memo", "kreditnota"),
        ),
        IntentRule(TaskFamily.INVOICING, Operation.CREATE, "invoice", ("invoice", "faktura")),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.CREATE,
            "customer",
            ("customer", "kunde"),
        ),
        IntentRule(
            TaskFamily.CUSTOMERS_PRODUCTS,
            Operation.CREATE,
            "product",
            ("product", "produkt"),
        ),
        IntentRule(
            TaskFamily.EMPLOYEES,
            Operation.UPDATE,
            "employee",
            ("update employee", "oppdater ansatt"),
        ),
        IntentRule(TaskFamily.EMPLOYEES, Operation.CREATE, "employee", ("employee", "ansatt")),
        IntentRule(TaskFamily.CORRECTIONS, Operation.REVERSE, "voucher", ("reverse", "reverser")),
        IntentRule(
            TaskFamily.TRAVEL_EXPENSES,
            Operation.DELETE,
            "travel_expense",
            ("delete travel", "slett reise"),
        ),
        IntentRule(
            TaskFamily.TRAVEL_EXPENSES,
            Operation.CREATE,
            "travel_expense",
            ("travel expense", "expense report", "reiseregning", "reiseutlegg"),
        ),
    )

    def plan(self, prompt: str, attachments: list[AttachmentFile]) -> TaskPlan:
        normalized_prompt = prompt.lower()
        attachment_facts = _attachment_facts(attachments)

        for rule in self._rules:
            if any(keyword in normalized_prompt for keyword in rule.keywords):
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

        if operation == Operation.CREATE:
            entities_to_create.append(EntityPayload(entity_type=entity_type, fields=payload))
            completion_checks.append(
                CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
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
        try:
            plan = self._primary.plan(prompt, attachments)
        except Exception as exc:
            logger.warning("Primary planner failed; falling back to keyword planner: %s", exc)
            return self._fallback.plan(prompt, attachments)

        if plan.task_family == TaskFamily.UNKNOWN:
            logger.info("Primary planner returned unknown; using keyword fallback")
            return self._fallback.plan(prompt, attachments)
        return plan


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

    payload = _payload_for_extraction(extraction)

    if extraction.operation == Operation.CREATE and entity_type != "unknown":
        entities_to_create.append(EntityPayload(entity_type=entity_type, fields=payload))
        completion_checks.append(
            CompletionCheck(kind="created", entity_type=entity_type, expected_fields=["id"])
        )

    if extraction.operation == Operation.UPDATE and entity_type != "unknown":
        lookup = _lookup_for_extraction(extraction)
        entities_to_find.append(EntityReference(entity_type=entity_type, lookup=lookup))
        fields_to_set = payload

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
    if extraction.primary_entity_type == "invoice" and extraction.invoice is not None:
        invoice_payload = extraction.invoice.model_dump(exclude_none=True)
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
  - create product
  - create employee
  - create department
  - create project linked to an existing customer
  - create invoice for an existing customer with one line item
  - register invoice payment
  - create credit note for an existing invoice
- Travel expense, correction, and module tasks are not yet implemented.
- For people, split names into firstName and lastName when possible.
- For projects, put customer references into customerName and/or customerOrganizationNumber.
- For projects, put explicit project manager references into projectManagerName and/or
  projectManagerEmail.
- For invoices, put customer references into customerName and/or customerOrganizationNumber.
- For invoice lines, put product references into productName and/or productNumber.
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


def _extract_customer_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    name = _extract_named_value(
        prompt,
        [
            r"(?:customer|kunde)\s+(?:named|med navn|with name)\s+(?P<value>[^,\n]+)",
            r"opprett\s+en\s+kunde\s+(?P<value>[^,\n]+)",
            r"create\s+(?:a|an)\s+customer\s+(?P<value>[^,\n]+)",
        ],
    )
    if name:
        payload["name"] = name

    email_match = _EMAIL_RE.search(prompt)
    if email_match:
        payload["email"] = email_match.group("email")

    org_match = _ORG_RE.search(prompt)
    if org_match:
        payload["organizationNumber"] = org_match.group("org")

    return payload


def _extract_employee_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    full_name = _extract_named_value(
        prompt,
        [
            r"(?:employee|ansatt)\s+(?:named|med navn|with name)\s+(?P<value>[^,\n]+)",
            r"oppdater\s+ansatt\s+(?P<value>[^,\n]+)",
        ],
    )
    if full_name:
        parts = full_name.split()
        if parts:
            payload["firstName"] = parts[0]
        if len(parts) > 1:
            payload["lastName"] = " ".join(parts[1:])

    email_match = _EMAIL_RE.search(prompt)
    if email_match:
        payload["email"] = email_match.group("email")

    return payload


def _extract_department_payload(prompt: str) -> dict[str, object]:
    name = _extract_named_value(
        prompt,
        [
            r"(?:department|avdeling)\s+(?:named|med navn|with name)\s+(?P<value>[^,\n]+)",
            r"opprett\s+en\s+avdeling\s+(?P<value>[^,\n]+)",
            r"create\s+(?:a|an)\s+department\s+(?P<value>[^,\n]+)",
        ],
    )
    return {"name": name} if name else {}


def _extract_product_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    product_name = _extract_named_value(
        prompt,
        [
            r"(?:product|produkt)\s+(?:named|med navn|with name)\s+(?P<value>[^,\n]+)",
            r"create\s+(?:a|an)\s+product\s+(?P<value>[^,\n]+)",
            r"opprett\s+et\s+produkt\s+(?P<value>[^,\n]+)",
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
    customer_name = _extract_named_value(
        prompt,
        [
            r"(?:for|til)\s+(?:customer|kunde)\s+(?P<value>[^,\n]+)",
        ],
    )
    if customer_name:
        payload["customerLookup"] = {"customerName": _strip_invoice_suffixes(customer_name)}

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

    quantity_match = re.search(
        r"(?:quantity|count|antall)\s+(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if quantity_match:
        line["count"] = _parse_decimal(quantity_match.group("value"))

    price_match = re.search(
        r"(?:price|pris)\s+(?:på\s+|of\s+)?(?P<value>\d+(?:[.,]\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if price_match:
        line["unitPriceExcludingVatCurrency"] = _parse_decimal(price_match.group("value"))

    if line:
        payload["line"] = line

    return payload


def _extract_invoice_action_components(
    prompt: str, operation: Operation
) -> tuple[dict[str, object], dict[str, object]]:
    lookup = _extract_invoice_lookup(prompt)
    fields: dict[str, object] = {}

    if operation == Operation.REGISTER_PAYMENT:
        payment_date = _extract_named_value(
            prompt,
            [
                r"(?:payment date|paid on|betalingsdato)\s+(?P<value>\d{4}-\d{2}-\d{2})",
            ],
        )
        if payment_date:
            fields["paymentDate"] = payment_date

        payment_type = _extract_named_value(
            prompt,
            [
                r"(?:payment type|payment method|betalingstype|betalingsmåte)\s+(?P<value>[^,\n]+)",
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
        if amount_match:
            fields["paidAmount"] = _parse_decimal(amount_match.group("value"))

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
                    r"(?:credit note date|credit memo date|kreditnotadato|date)\s+"
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
            r"(?:invoice number|fakturanummer)\s+(?P<value>\d+)",
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

    return lookup


def _extract_project_payload(prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    project_name = _extract_named_value(
        prompt,
        [
            r"(?:project|prosjekt)\s+(?:named|med navn|with name)\s+(?P<value>[^,\n]+)",
            r"create\s+(?:a|an)\s+project\s+(?P<value>[^,\n]+)",
            r"opprett\s+et\s+prosjekt\s+(?P<value>[^,\n]+)",
        ],
    )
    if project_name:
        payload["name"] = project_name

    customer_name = _extract_named_value(
        prompt,
        [
            r"(?:for|tilknyttet)\s+(?:customer|kunde)\s+(?P<value>[^,\n]+)",
        ],
    )
    if customer_name:
        payload["customerLookup"] = {"customerName": _strip_project_manager_clause(customer_name)}

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
        names = project_manager_name.split()
        manager_lookup: dict[str, object] = {}
        if names:
            manager_lookup["firstName"] = names[0]
        if len(names) > 1:
            manager_lookup["lastName"] = " ".join(names[1:])
        if manager_lookup:
            payload["projectManagerLookup"] = manager_lookup

    email_matches = _EMAIL_RE.findall(prompt)
    if project_manager_name and email_matches:
        payload.setdefault("projectManagerLookup", {})
        payload["projectManagerLookup"]["email"] = email_matches[-1]

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


def _strip_product_suffixes(value: str) -> str:
    cleaned = re.split(
        r"\b(?:product number|produktnummer|varenummer|price|pris|cost|kost(?:pris)?)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_extracted_value(cleaned)


def _strip_invoice_suffixes(value: str) -> str:
    cleaned = re.split(
        (
            r"\b(?:with|med)\s+(?:product|produkt)\b|"
            r"\b(?:product number|produktnummer|varenummer|price|pris|quantity|count|antall)\b"
        ),
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_extracted_value(cleaned)


def _strip_invoice_line_suffixes(value: str) -> str:
    cleaned = re.split(
        r"\b(?:product number|produktnummer|varenummer|price|pris|quantity|count|antall)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_extracted_value(cleaned)


def _strip_payment_type_suffixes(value: str) -> str:
    cleaned = re.split(
        (
            r"\b(?:paid amount|payment amount|amount|betalt beløp|beløp|"
            r"payment date|betalingsdato|date)\b"
        ),
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_extracted_value(cleaned)
