"""First live Tripletex workflows for the real implementation phase."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ..client import TripletexClient
from ..task_plan import Operation, TaskFamily, TaskPlan
from .base import BaseWorkflow, WorkflowExecutionError, WorkflowResult

_DEFAULT_INVOICE_BANK_ACCOUNT_NUMBER = "12345678903"
_DEFAULT_INVOICE_DUE_DAYS = 14


def _compact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def _compact_address(mapping: dict[str, Any] | None) -> dict[str, Any] | None:
    if not mapping:
        return None
    compacted = _compact_mapping(mapping)
    return compacted or None


def _require_payload(plan: TaskPlan, entity_type: str) -> dict[str, Any]:
    payload = plan.primary_payload(entity_type)
    if payload is None:
        raise WorkflowExecutionError(f"Expected payload for entity type {entity_type}")
    return payload.fields


class CustomerCreateWorkflow(BaseWorkflow):
    family = TaskFamily.CUSTOMERS_PRODUCTS
    entity_type = "customer"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "customer")
        name = fields.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowExecutionError("Customer creation requires a name")

        body = _compact_mapping(
            {
                "name": name.strip(),
                "organizationNumber": _normalize_org_number(fields.get("organizationNumber")),
                "email": fields.get("email"),
                "invoiceEmail": fields.get("invoiceEmail"),
                "phoneNumber": fields.get("phoneNumber"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "description": fields.get("description"),
                "language": fields.get("language"),
                "postalAddress": _compact_address(_as_dict(fields.get("postalAddress"))),
                "physicalAddress": _compact_address(_as_dict(fields.get("physicalAddress"))),
                "isCustomer": True,
            }
        )

        response = await client.post("/customer", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="customer_create",
            intended_operations=["POST /customer"],
            resource_ids=[created_id] if created_id is not None else [],
            details={"entity": "customer", "created": created},
        )


class ProductCreateWorkflow(BaseWorkflow):
    family = TaskFamily.CUSTOMERS_PRODUCTS
    entity_type = "product"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "product")
        name = fields.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowExecutionError("Product creation requires a name")

        body = _compact_mapping(
            {
                "name": name.strip(),
                "number": fields.get("number"),
                "description": fields.get("description"),
                "orderLineDescription": fields.get("orderLineDescription"),
                "priceExcludingVatCurrency": fields.get("priceExcludingVatCurrency"),
                "costExcludingVatCurrency": fields.get("costExcludingVatCurrency"),
                "isInactive": fields.get("isInactive"),
                "isStockItem": fields.get("isStockItem"),
            }
        )

        response = await client.post("/product", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="product_create",
            intended_operations=["POST /product"],
            resource_ids=[created_id] if created_id is not None else [],
            details={"entity": "product", "created": created},
        )


class InvoiceCreateWorkflow(BaseWorkflow):
    family = TaskFamily.INVOICING
    entity_type = "invoice"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "invoice")

        customer_lookup = _as_dict(fields.get("customerLookup"))
        if not customer_lookup:
            raise WorkflowExecutionError("Invoice creation requires a customer reference")
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")

        line_fields = _as_dict(fields.get("line")) or {}
        order_line = await _build_invoice_order_line(client, line_fields)

        invoice_date = _normalize_date(fields.get("invoiceDate")) or date.today().isoformat()
        due_date = _normalize_date(fields.get("invoiceDueDate")) or _add_days(
            invoice_date, _DEFAULT_INVOICE_DUE_DAYS
        )
        delivery_date = _normalize_date(fields.get("deliveryDate")) or invoice_date

        bank_account, bank_account_was_updated = await _ensure_invoice_bank_account_configured(client)

        body = _compact_mapping(
            {
                "invoiceDate": invoice_date,
                "invoiceDueDate": due_date,
                "comment": fields.get("comment"),
                "customer": {"id": customer_id},
                "orders": [
                    _compact_mapping(
                        {
                            "customer": {"id": customer_id},
                            "orderDate": invoice_date,
                            "deliveryDate": delivery_date,
                            "invoiceComment": fields.get("invoiceComment"),
                            "orderLines": [order_line],
                        }
                    )
                ],
            }
        )

        response = await client.post(
            "/invoice",
            params={"sendToCustomer": False},
            json_body=body,
        )
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        intended_operations = [
            "GET /customer",
            "GET /ledger/account",
            "POST /invoice",
        ]
        if _as_dict(line_fields.get("productLookup")):
            intended_operations.insert(1, "GET /product")
        if bank_account_was_updated:
            intended_operations.insert(2, "PUT /ledger/account/{id}")

        return WorkflowResult(
            name="invoice_create",
            intended_operations=intended_operations,
            resource_ids=[created_id] if created_id is not None else [],
            details={
                "entity": "invoice",
                "customerId": customer_id,
                "invoiceId": created_id,
                "created": created,
            },
        )


class EmployeeCreateWorkflow(BaseWorkflow):
    family = TaskFamily.EMPLOYEES
    entity_type = "employee"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "employee")
        first_name = fields.get("firstName")
        last_name = fields.get("lastName")
        if not isinstance(first_name, str) or not first_name.strip():
            raise WorkflowExecutionError("Employee creation requires firstName")
        if not isinstance(last_name, str) or not last_name.strip():
            raise WorkflowExecutionError("Employee creation requires lastName")

        body = _compact_mapping(
            {
                "firstName": first_name.strip(),
                "lastName": last_name.strip(),
                "email": fields.get("email"),
                "employeeNumber": fields.get("employeeNumber"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "comments": fields.get("comments"),
                "address": _compact_address(_as_dict(fields.get("address"))),
            }
        )

        response = await client.post("/employee", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="employee_create",
            intended_operations=["POST /employee"],
            resource_ids=[created_id] if created_id is not None else [],
            details={"entity": "employee", "created": created},
        )


class DepartmentCreateWorkflow(BaseWorkflow):
    family = TaskFamily.DEPARTMENTS
    entity_type = "department"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "department")
        name = fields.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowExecutionError("Department creation requires a name")

        body = _compact_mapping(
            {
                "name": name.strip(),
                "departmentNumber": fields.get("departmentNumber"),
            }
        )

        response = await client.post("/department", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="department_create",
            intended_operations=["POST /department"],
            resource_ids=[created_id] if created_id is not None else [],
            details={"entity": "department", "created": created},
        )


class ProjectCreateWorkflow(BaseWorkflow):
    family = TaskFamily.PROJECTS
    entity_type = "project"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "project")
        name = fields.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowExecutionError("Project creation requires a name")

        customer_lookup = _as_dict(fields.get("customerLookup"))
        if not customer_lookup:
            raise WorkflowExecutionError(
                "Project creation requires customerName or customerOrganizationNumber"
            )
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")
        project_manager_lookup = _as_dict(fields.get("projectManagerLookup"))
        project_manager = await _resolve_project_manager(client, project_manager_lookup)
        project_manager_id = _extract_id(project_manager)
        if project_manager_id is None:
            raise WorkflowExecutionError("Matched project manager did not include an id")

        body = _compact_mapping(
            {
                "name": name.strip(),
                "number": fields.get("number"),
                "description": fields.get("description"),
                "startDate": fields.get("startDate") or date.today().isoformat(),
                "endDate": fields.get("endDate"),
                "isInternal": fields.get("isInternal"),
                "isOffer": fields.get("isOffer"),
                "customer": {"id": customer_id},
                "projectManager": {"id": project_manager_id},
            }
        )

        response = await client.post("/project", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="project_create",
            intended_operations=["GET /customer", "POST /project"],
            resource_ids=[created_id] if created_id is not None else [],
            details={
                "entity": "project",
                "customerId": customer_id,
                "projectManagerId": project_manager_id,
                "created": created,
            },
        )


async def _find_single_customer(
    client: TripletexClient, lookup: dict[str, Any]
) -> dict[str, Any]:
    params = _compact_mapping(
        {
            "customerName": lookup.get("customerName") or lookup.get("name"),
            "organizationNumber": _normalize_org_number(lookup.get("organizationNumber")),
            "email": lookup.get("email"),
            "count": 2,
            "fields": client.select_fields("id", "name", "organizationNumber", "email"),
        }
    )
    if not params or set(params) <= {"count", "fields"}:
        raise WorkflowExecutionError("Customer lookup requires name, organization number, or email")

    payload = await client.get("/customer", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No customer matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Customer lookup was ambiguous for {lookup!r}")
    return matches[0]


async def _find_single_product(
    client: TripletexClient, lookup: dict[str, Any]
) -> dict[str, Any]:
    params = _compact_mapping(
        {
            "name": lookup.get("name"),
            "count": 2,
            "sorting": "name",
            "fields": client.select_fields(
                "id",
                "name",
                "number",
                "priceExcludingVatCurrency",
            ),
        }
    )
    product_number = lookup.get("productNumber") or lookup.get("number")
    if product_number is not None:
        params["productNumber"] = [product_number]
    if lookup.get("id") is not None:
        params["ids"] = str(lookup["id"])

    if not params or set(params) <= {"count", "sorting", "fields"}:
        raise WorkflowExecutionError("Product lookup requires id, name, or product number")

    payload = await client.get("/product", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No product matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Product lookup was ambiguous for {lookup!r}")
    return matches[0]


async def _resolve_project_manager(
    client: TripletexClient, lookup: dict[str, Any] | None
) -> dict[str, Any]:
    if lookup:
        return await _find_single_employee(client, lookup, require_assignable=True)
    return await _find_default_project_manager(client)


async def _find_default_project_manager(client: TripletexClient) -> dict[str, Any]:
    payload = await client.get(
        "/employee",
        params={
            "assignableProjectManagers": True,
            "count": 1,
            "sorting": "id",
            "fields": client.select_fields(
                "id",
                "firstName",
                "lastName",
                "displayName",
                "employeeNumber",
                "email",
            ),
        },
    )
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError("No assignable project manager was available")
    return matches[0]


async def _find_single_employee(
    client: TripletexClient,
    lookup: dict[str, Any],
    *,
    require_assignable: bool = False,
) -> dict[str, Any]:
    params = _compact_mapping(
        {
            "id": lookup.get("id"),
            "firstName": lookup.get("firstName"),
            "lastName": lookup.get("lastName"),
            "employeeNumber": lookup.get("employeeNumber") or lookup.get("number"),
            "email": lookup.get("email"),
            "assignableProjectManagers": True if require_assignable else None,
            "count": 2,
            "sorting": "id",
            "fields": client.select_fields(
                "id",
                "firstName",
                "lastName",
                "displayName",
                "employeeNumber",
                "email",
            ),
        }
    )
    if not params or set(params) <= {"assignableProjectManagers", "count", "sorting", "fields"}:
        raise WorkflowExecutionError(
            "Employee lookup requires id, firstName/lastName, employeeNumber, or email"
        )

    payload = await client.get("/employee", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No employee matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Employee lookup was ambiguous for {lookup!r}")
    return matches[0]


async def _build_invoice_order_line(
    client: TripletexClient, line_fields: dict[str, Any]
) -> dict[str, Any]:
    if not line_fields:
        raise WorkflowExecutionError("Invoice creation requires at least one line item")

    product_lookup = _as_dict(line_fields.get("productLookup"))
    product_id: int | None = None
    if product_lookup:
        product = await _find_single_product(client, product_lookup)
        product_id = _extract_id(product)
        if product_id is None:
            raise WorkflowExecutionError("Matched product did not include an id")

    description = line_fields.get("description")
    unit_price = line_fields.get("unitPriceExcludingVatCurrency")
    count = line_fields.get("count")
    normalized_count = count if isinstance(count, (int, float)) else 1

    if product_id is None and not isinstance(description, str):
        raise WorkflowExecutionError(
            "Invoice line requires either a product reference or a description"
        )
    if product_id is None and not isinstance(unit_price, (int, float)):
        raise WorkflowExecutionError(
            "Invoice line without a product reference requires a unit price"
        )

    return _compact_mapping(
        {
            "product": {"id": product_id} if product_id is not None else None,
            "description": description.strip() if isinstance(description, str) else None,
            "count": normalized_count,
            "unitPriceExcludingVatCurrency": unit_price,
        }
    )


async def _ensure_invoice_bank_account_configured(
    client: TripletexClient,
) -> tuple[dict[str, Any], bool]:
    payload = await client.get(
        "/ledger/account",
        params={
            "isBankAccount": True,
            "count": 10,
            "sorting": "number",
            "fields": client.select_fields(
                "id",
                "number",
                "name",
                "isBankAccount",
                "isInvoiceAccount",
                "bankAccountNumber",
            ),
        },
    )
    accounts = client.unwrap_values(payload)
    invoice_accounts = [
        account for account in accounts if isinstance(account, dict) and account.get("isInvoiceAccount")
    ]
    if not invoice_accounts:
        raise WorkflowExecutionError("No invoice bank account was available")

    account = invoice_accounts[0]
    existing_number = account.get("bankAccountNumber")
    if isinstance(existing_number, str) and existing_number.strip():
        return account, False

    account_id = _extract_id(account)
    if account_id is None:
        raise WorkflowExecutionError("Invoice bank account did not include an id")

    updated = await client.put(
        f"/ledger/account/{account_id}",
        json_body={"bankAccountNumber": _DEFAULT_INVOICE_BANK_ACCOUNT_NUMBER},
    )
    unwrapped = client.unwrap_value(updated)
    if isinstance(unwrapped, dict):
        return unwrapped, True
    raise WorkflowExecutionError("Invoice bank account update did not return an account payload")


def _extract_id(payload: Any) -> int | None:
    if isinstance(payload, dict):
        value = payload.get("id")
        if isinstance(value, int):
            return value
    return None


def _normalize_org_number(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _normalize_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _add_days(iso_date: str, days: int) -> str:
    base = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return (base + timedelta(days=days)).isoformat()
