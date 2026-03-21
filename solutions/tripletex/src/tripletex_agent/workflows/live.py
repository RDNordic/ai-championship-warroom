"""First live Tripletex workflows for the real implementation phase."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ..client import TripletexAPIError, TripletexClient
from ..task_plan import Operation, TaskFamily, TaskPlan
from .base import BaseWorkflow, WorkflowExecutionError, WorkflowResult

_DEFAULT_INVOICE_BANK_ACCOUNT_NUMBER = "12345678903"
_DEFAULT_INVOICE_DUE_DAYS = 14
_DEFAULT_INVOICE_LOOKUP_DATE_FROM = "2000-01-01"
_DEFAULT_INVOICE_LOOKUP_DATE_TO = "2100-01-01"
_DEFAULT_EMPLOYEE_USER_TYPE = "NO_ACCESS"


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


def _require_reference(plan: TaskPlan, entity_type: str) -> dict[str, Any]:
    reference = plan.primary_reference(entity_type)
    if reference is None:
        raise WorkflowExecutionError(f"Expected reference for entity type {entity_type}")
    return reference.lookup


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
                "isSupplier": fields.get("isSupplier"),
                "isCustomer": fields.get("isCustomer"),
                "email": fields.get("email"),
                "invoiceEmail": fields.get("invoiceEmail"),
                "phoneNumber": fields.get("phoneNumber"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "description": fields.get("description"),
                "language": _normalize_language(fields.get("language")),
                "postalAddress": _compact_address(_as_dict(fields.get("postalAddress"))),
                "physicalAddress": _compact_address(_as_dict(fields.get("physicalAddress"))),
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


class OrderInvoicePaymentWorkflow(BaseWorkflow):
    family = TaskFamily.INVOICING
    entity_type = "invoice"
    supported_operations = (Operation.CREATE,)

    def supports(self, plan: TaskPlan) -> bool:
        if not super().supports(plan):
            return False
        payload = plan.primary_payload("invoice")
        fields = payload.fields if payload is not None else {}
        return (
            fields.get("createOrder") is True
            and fields.get("convertOrderToInvoice") is True
        )

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "invoice")

        customer_lookup = _as_dict(fields.get("customerLookup"))
        if not customer_lookup:
            raise WorkflowExecutionError("Order conversion requires a customer reference")
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")

        line_fields_list = _invoice_line_field_list(fields)
        order_lines = await _build_invoice_order_lines(client, line_fields_list)

        invoice_date = _invoice_date(fields)
        delivery_date = _invoice_delivery_date(fields, invoice_date)

        order_body = _compact_mapping(
            {
                "customer": {"id": customer_id},
                "orderDate": invoice_date,
                "deliveryDate": delivery_date,
                "invoiceComment": fields.get("invoiceComment"),
                "orderLines": order_lines,
            }
        )
        order_response = await client.post("/order", json_body=order_body)
        created_order = client.unwrap_value(order_response)
        order_id = _extract_id(created_order)
        if order_id is None:
            raise WorkflowExecutionError("Created order did not include an id")

        invoice_response = await client.put(f"/order/{order_id}/:invoice")
        created_invoice = await _invoice_from_order_conversion(
            client=client,
            payload=client.unwrap_value(invoice_response),
            customer_lookup=customer_lookup,
            invoice_date=invoice_date,
        )
        invoice_id = _extract_id(created_invoice)
        if invoice_id is None:
            raise WorkflowExecutionError("Created invoice did not include an id")

        result_details: dict[str, Any] = {
            "entity": "invoice",
            "customerId": customer_id,
            "orderId": order_id,
            "invoiceId": invoice_id,
            "invoiceNumber": created_invoice.get("invoiceNumber"),
            "createdOrder": created_order,
            "createdInvoice": created_invoice,
        }
        intended_operations = ["GET /customer"]
        if any(_as_dict(lf.get("productLookup")) for lf in line_fields_list):
            intended_operations.append("GET /product")
        intended_operations.extend(["POST /order", "PUT /order/{id}/:invoice"])

        if fields.get("registerPayment") is True:
            payment_date = _normalize_date(fields.get("paymentDate")) or date.today().isoformat()
            paid_amount = _resolve_invoice_payment_amount(fields, created_invoice, order_lines)
            payment_type_lookup = _as_dict(fields.get("paymentTypeLookup"))
            payment_type = await _find_invoice_payment_type(client, payment_type_lookup)
            payment_type_id = _extract_id(payment_type)
            if payment_type_id is None:
                raise WorkflowExecutionError("Matched payment type did not include an id")

            payment_response = await client.put(
                f"/invoice/{invoice_id}/:payment",
                params=_compact_mapping(
                    {
                        "paymentDate": payment_date,
                        "paymentTypeId": payment_type_id,
                        "paidAmount": paid_amount,
                        "paidAmountCurrency": _coerce_number(fields.get("paidAmountCurrency")),
                    }
                ),
            )
            result_details.update(
                {
                    "paymentTypeId": payment_type_id,
                    "paidAmount": paid_amount,
                    "paymentUpdated": client.unwrap_value(payment_response),
                }
            )
            intended_operations.extend(
                ["GET /invoice/paymentType", "PUT /invoice/{id}/:payment"]
            )

        return WorkflowResult(
            name="order_invoice_payment",
            intended_operations=intended_operations,
            resource_ids=[order_id, invoice_id],
            details=result_details,
        )


class InvoiceCreateWorkflow(BaseWorkflow):
    family = TaskFamily.INVOICING
    entity_type = "invoice"
    supported_operations = (Operation.CREATE,)

    def supports(self, plan: TaskPlan) -> bool:
        if not super().supports(plan):
            return False
        payload = plan.primary_payload("invoice")
        fields = payload.fields if payload is not None else {}
        return fields.get("supplierInvoice") is not True

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "invoice")
        send_to_customer = plan.action_semantics.send_to_customer is True

        customer_lookup = _as_dict(fields.get("customerLookup"))
        if not customer_lookup:
            raise WorkflowExecutionError("Invoice creation requires a customer reference")
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")

        line_fields_list = _invoice_line_field_list(fields)
        order_lines = await _build_invoice_order_lines(client, line_fields_list)
        invoice_date = _invoice_date(fields)
        due_date = _invoice_due_date(fields, invoice_date)
        delivery_date = _invoice_delivery_date(fields, invoice_date)

        bank_account_id: int | None = None
        bank_account_was_updated = False
        if send_to_customer:
            bank_account, bank_account_was_updated = await _ensure_invoice_bank_account_configured(
                client
            )
            bank_account_id = _extract_id(bank_account)

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
                            "orderLines": order_lines,
                        }
                    )
                ],
            }
        )

        response = await client.post(
            "/invoice",
            params={"sendToCustomer": send_to_customer},
            json_body=body,
        )
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        intended_operations = ["GET /customer", "POST /invoice"]
        if any(_as_dict(lf.get("productLookup")) for lf in line_fields_list):
            intended_operations.insert(1, "GET /product")
        if send_to_customer:
            ledger_index = 1 if "GET /product" not in intended_operations else 2
            intended_operations.insert(ledger_index, "GET /ledger/account")
        if bank_account_was_updated:
            intended_operations.insert(len(intended_operations) - 1, "PUT /ledger/account/{id}")

        return WorkflowResult(
            name="invoice_create",
            intended_operations=intended_operations,
            resource_ids=[created_id] if created_id is not None else [],
            details={
                "entity": "invoice",
                "customerId": customer_id,
                "invoiceId": created_id,
                "sendToCustomer": send_to_customer,
                "invoiceBankAccountId": bank_account_id,
                "invoiceBankAccountUpdated": bank_account_was_updated,
                "created": created,
            },
        )


class InvoicePaymentWorkflow(BaseWorkflow):
    family = TaskFamily.INVOICING
    entity_type = "invoice"
    supported_operations = (Operation.REGISTER_PAYMENT,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "invoice")
        fields = plan.fields_to_set

        invoice = await _find_single_invoice(client, lookup)
        invoice_id = _extract_id(invoice)
        if invoice_id is None:
            raise WorkflowExecutionError("Matched invoice did not include an id")

        payment_date = _normalize_date(fields.get("paymentDate")) or date.today().isoformat()
        paid_amount = _resolve_invoice_payment_amount(fields, invoice)

        payment_type_lookup = _as_dict(fields.get("paymentTypeLookup"))
        payment_type = await _find_invoice_payment_type(client, payment_type_lookup)
        payment_type_id = _extract_id(payment_type)
        if payment_type_id is None:
            raise WorkflowExecutionError("Matched payment type did not include an id")

        response = await client.put(
            f"/invoice/{invoice_id}/:payment",
            params=_compact_mapping(
                {
                    "paymentDate": payment_date,
                    "paymentTypeId": payment_type_id,
                    "paidAmount": paid_amount,
                    "paidAmountCurrency": _coerce_number(fields.get("paidAmountCurrency")),
                }
            ),
        )
        updated = client.unwrap_value(response)

        return WorkflowResult(
            name="invoice_payment",
            intended_operations=[
                _invoice_lookup_operation(lookup),
                "GET /invoice/paymentType",
                "PUT /invoice/{id}/:payment",
            ],
            resource_ids=[invoice_id],
            details={
                "entity": "invoice",
                "invoiceId": invoice_id,
                "invoiceNumber": invoice.get("invoiceNumber"),
                "paymentTypeId": payment_type_id,
                "paidAmount": paid_amount,
                "updated": updated,
            },
        )


class InvoiceCreditNoteWorkflow(BaseWorkflow):
    family = TaskFamily.INVOICING
    entity_type = "invoice"
    supported_operations = (Operation.CREATE_CREDIT_NOTE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "invoice")
        fields = plan.fields_to_set

        invoice = await _find_single_invoice(client, lookup)
        invoice_id = _extract_id(invoice)
        if invoice_id is None:
            raise WorkflowExecutionError("Matched invoice did not include an id")
        if invoice.get("isCreditNote") is True:
            raise WorkflowExecutionError("Cannot create a credit note from a credit note")

        credit_note_date = _normalize_date(fields.get("creditNoteDate")) or date.today().isoformat()
        response = await client.put(
            f"/invoice/{invoice_id}/:createCreditNote",
            params=_compact_mapping(
                {
                    "date": credit_note_date,
                    "comment": fields.get("comment"),
                    "creditNoteEmail": fields.get("creditNoteEmail"),
                    "sendToCustomer": False,
                }
            ),
        )
        created = client.unwrap_value(response)
        credit_note_id = _extract_id(created)

        return WorkflowResult(
            name="invoice_credit_note",
            intended_operations=[
                _invoice_lookup_operation(lookup),
                "PUT /invoice/{id}/:createCreditNote",
            ],
            resource_ids=[credit_note_id] if credit_note_id is not None else [],
            details={
                "entity": "invoice",
                "sourceInvoiceId": invoice_id,
                "sourceInvoiceNumber": invoice.get("invoiceNumber"),
                "creditNoteId": credit_note_id,
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

        user_type = fields.get("userType")
        normalized_user_type = (
            user_type.strip().upper()
            if isinstance(user_type, str) and user_type.strip()
            else _DEFAULT_EMPLOYEE_USER_TYPE
        )
        if normalized_user_type not in {"STANDARD", "EXTENDED", "NO_ACCESS"}:
            raise WorkflowExecutionError(
                f"Employee creation received unsupported userType {normalized_user_type!r}"
            )
        department = await _resolve_employee_department(client, fields)
        department_id = _extract_id(department)
        if department_id is None:
            raise WorkflowExecutionError("Matched department did not include an id")

        body = _compact_mapping(
            {
                "firstName": first_name.strip(),
                "lastName": last_name.strip(),
                "email": fields.get("email"),
                "employeeNumber": fields.get("employeeNumber"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "comments": fields.get("comments"),
                "address": _compact_address(_as_dict(fields.get("address"))),
                "userType": normalized_user_type,
                "department": {"id": department_id},
            }
        )

        response = await client.post("/employee", json_body=body)
        created = client.unwrap_value(response)
        created_id = _extract_id(created)

        return WorkflowResult(
            name="employee_create",
            intended_operations=["GET /department", "POST /employee"],
            resource_ids=[created_id] if created_id is not None else [],
            details={
                "entity": "employee",
                "departmentId": department_id,
                "userType": normalized_user_type,
                "created": created,
            },
        )


class DepartmentCreateWorkflow(BaseWorkflow):
    family = TaskFamily.DEPARTMENTS
    entity_type = "department"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "department")

        # Support both single name and multi-department name lists
        names_list = fields.get("names")
        single_name = fields.get("name")
        if isinstance(names_list, list) and names_list:
            dept_names = [str(n).strip() for n in names_list if str(n).strip()]
        elif isinstance(single_name, str) and single_name.strip():
            dept_names = [single_name.strip()]
        else:
            raise WorkflowExecutionError("Department creation requires a name")

        created_ids: list[int] = []
        all_created: list[Any] = []
        for dept_name in dept_names:
            body = _compact_mapping(
                {
                    "name": dept_name,
                    "departmentNumber": fields.get("departmentNumber"),
                }
            )
            response = await client.post("/department", json_body=body)
            created = client.unwrap_value(response)
            created_id = _extract_id(created)
            if created_id is not None:
                created_ids.append(created_id)
            all_created.append(created)

        return WorkflowResult(
            name="department_create",
            intended_operations=["POST /department"] * len(dept_names),
            resource_ids=created_ids,
            details={"entity": "department", "count": len(dept_names), "created": all_created},
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


class TravelExpenseCreateWorkflow(BaseWorkflow):
    family = TaskFamily.TRAVEL_EXPENSES
    entity_type = "travel_expense"
    supported_operations = (Operation.CREATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        fields = _require_payload(plan, "travel_expense")

        # Resolve employee
        employee_lookup = _as_dict(fields.get("employeeLookup"))
        if employee_lookup:
            employee = await _find_single_employee(client, employee_lookup)
        else:
            employee = await _find_default_employee(client)
        employee_id = _extract_id(employee)
        if employee_id is None:
            raise WorkflowExecutionError("Matched employee did not include an id")

        # Resolve optional project
        project_id: int | None = None
        project_lookup = _as_dict(fields.get("projectLookup"))
        if project_lookup:
            project = await _find_single_project(client, project_lookup)
            project_id = _extract_id(project)

        # Resolve optional department
        department_id: int | None = None
        department_lookup = _as_dict(fields.get("departmentLookup"))
        if department_lookup:
            department = await _find_single_department(client, department_lookup)
            department_id = _extract_id(department)

        # Build parent travel expense body
        title = fields.get("title") or "Travel expense"
        expense_date = _normalize_date(fields.get("departureDate")) or date.today().isoformat()

        body = _compact_mapping(
            {
                "employee": {"id": employee_id},
                "title": title,
                "date": expense_date,
                "project": {"id": project_id} if project_id is not None else None,
                "department": {"id": department_id} if department_id is not None else None,
            }
        )

        response = await client.post("/travelExpense", json_body=body)
        created = client.unwrap_value(response)
        expense_id = _extract_id(created)
        if expense_id is None:
            raise WorkflowExecutionError("Travel expense creation did not return an id")

        intended_operations = ["GET /employee", "POST /travelExpense", "GET /travelExpense/paymentType"]
        child_ids: list[int] = []

        # Look up default payment type for costs
        payment_type_id: int | None = None
        try:
            pt_resp = await client.get("/travelExpense/paymentType", params={"count": 1})
            pt_values = client.unwrap_values(pt_resp)
            if pt_values:
                payment_type_id = _extract_id(pt_values[0])
        except Exception:
            pass  # Will fail at cost creation if no payment type found

        # Add cost items
        costs = fields.get("costs")
        if isinstance(costs, list):
            for cost_item in costs:
                if not isinstance(cost_item, dict):
                    continue
                cost_body = _compact_mapping(
                    {
                        "travelExpense": {"id": expense_id},
                        "comments": cost_item.get("description", ""),
                        "amountCurrencyIncVat": _coerce_number(cost_item.get("amount")),
                        "date": _normalize_date(cost_item.get("date")) or expense_date,
                        "paymentType": {"id": payment_type_id} if payment_type_id else None,
                    }
                )
                cost_response = await client.post("/travelExpense/cost", json_body=cost_body)
                cost_created = client.unwrap_value(cost_response)
                cost_id = _extract_id(cost_created)
                if cost_id is not None:
                    child_ids.append(cost_id)
                intended_operations.append("POST /travelExpense/cost")

        # Add mileage allowances
        mileage_allowances = fields.get("mileageAllowances")
        if isinstance(mileage_allowances, list):
            for mileage_item in mileage_allowances:
                if not isinstance(mileage_item, dict):
                    continue
                mileage_body = _compact_mapping(
                    {
                        "travelExpense": {"id": expense_id},
                        "rateTypeId": _coerce_int(mileage_item.get("rateTypeId")),
                        "km": _coerce_number(mileage_item.get("km")),
                        "date": _normalize_date(mileage_item.get("date")) or expense_date,
                    }
                )
                mileage_response = await client.post(
                    "/travelExpense/mileageAllowance", json_body=mileage_body
                )
                mileage_created = client.unwrap_value(mileage_response)
                mileage_id = _extract_id(mileage_created)
                if mileage_id is not None:
                    child_ids.append(mileage_id)
                intended_operations.append("POST /travelExpense/mileageAllowance")

        # Add per diem compensations
        per_diem_compensations = fields.get("perDiemCompensations")
        if isinstance(per_diem_compensations, list):
            for per_diem_item in per_diem_compensations:
                if not isinstance(per_diem_item, dict):
                    continue
                per_diem_body = _compact_mapping(
                    {
                        "travelExpense": {"id": expense_id},
                        "rateTypeId": _coerce_int(per_diem_item.get("rateTypeId")),
                        "countDays": _coerce_number(per_diem_item.get("countDays")),
                        "date": _normalize_date(per_diem_item.get("date")) or expense_date,
                    }
                )
                per_diem_response = await client.post(
                    "/travelExpense/perDiemCompensation", json_body=per_diem_body
                )
                per_diem_created = client.unwrap_value(per_diem_response)
                per_diem_id = _extract_id(per_diem_created)
                if per_diem_id is not None:
                    child_ids.append(per_diem_id)
                intended_operations.append("POST /travelExpense/perDiemCompensation")

        # Optionally deliver the expense report
        deliver = fields.get("deliver") is True
        if deliver:
            await client.put(f"/travelExpense/{expense_id}/:deliver")
            intended_operations.append("PUT /travelExpense/{id}/:deliver")

        return WorkflowResult(
            name="travel_expense_create",
            intended_operations=intended_operations,
            resource_ids=[expense_id] + child_ids,
            details={
                "entity": "travel_expense",
                "employeeId": employee_id,
                "expenseId": expense_id,
                "childIds": child_ids,
                "delivered": deliver,
                "created": created,
            },
        )


class CustomerDeleteWorkflow(BaseWorkflow):
    family = TaskFamily.CUSTOMERS_PRODUCTS
    entity_type = "customer"
    supported_operations = (Operation.DELETE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "customer")
        customer = await _find_single_customer(client, lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")

        await client.delete(f"/customer/{customer_id}")

        return WorkflowResult(
            name="customer_delete",
            intended_operations=["GET /customer", "DELETE /customer/{id}"],
            resource_ids=[customer_id],
            details={"entity": "customer", "deletedId": customer_id},
        )


class CustomerUpdateWorkflow(BaseWorkflow):
    family = TaskFamily.CUSTOMERS_PRODUCTS
    entity_type = "customer"
    supported_operations = (Operation.UPDATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "customer")
        fields = plan.fields_to_set

        customer = await _find_single_customer(client, lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")

        update_body = _compact_mapping(
            {
                "name": fields.get("name"),
                "organizationNumber": _normalize_org_number(fields.get("organizationNumber")),
                "email": fields.get("email"),
                "invoiceEmail": fields.get("invoiceEmail"),
                "phoneNumber": fields.get("phoneNumber"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "description": fields.get("description"),
                "language": _normalize_language(fields.get("language")),
                "postalAddress": _compact_address(_as_dict(fields.get("postalAddress"))),
                "physicalAddress": _compact_address(_as_dict(fields.get("physicalAddress"))),
            }
        )
        if not update_body:
            raise WorkflowExecutionError("Customer update requires at least one field to change")

        response = await client.put(f"/customer/{customer_id}", json_body=update_body)
        updated = client.unwrap_value(response)

        return WorkflowResult(
            name="customer_update",
            intended_operations=["GET /customer", "PUT /customer/{id}"],
            resource_ids=[customer_id],
            details={"entity": "customer", "customerId": customer_id, "updated": updated},
        )


class ProductDeleteWorkflow(BaseWorkflow):
    family = TaskFamily.CUSTOMERS_PRODUCTS
    entity_type = "product"
    supported_operations = (Operation.DELETE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "product")
        product = await _find_single_product(client, lookup)
        product_id = _extract_id(product)
        if product_id is None:
            raise WorkflowExecutionError("Matched product did not include an id")

        await client.delete(f"/product/{product_id}")

        return WorkflowResult(
            name="product_delete",
            intended_operations=["GET /product", "DELETE /product/{id}"],
            resource_ids=[product_id],
            details={"entity": "product", "deletedId": product_id},
        )


class EmployeeUpdateWorkflow(BaseWorkflow):
    family = TaskFamily.EMPLOYEES
    entity_type = "employee"
    supported_operations = (Operation.UPDATE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "employee")
        fields = plan.fields_to_set

        employee = await _find_single_employee(client, lookup)
        employee_id = _extract_id(employee)
        if employee_id is None:
            raise WorkflowExecutionError("Matched employee did not include an id")

        update_body = _compact_mapping(
            {
                "firstName": fields.get("firstName"),
                "lastName": fields.get("lastName"),
                "email": fields.get("email"),
                "phoneNumberMobile": fields.get("phoneNumberMobile"),
                "comments": fields.get("comments"),
            }
        )
        if not update_body:
            raise WorkflowExecutionError("Employee update requires at least one field to change")

        response = await client.put(f"/employee/{employee_id}", json_body=update_body)
        updated = client.unwrap_value(response)

        return WorkflowResult(
            name="employee_update",
            intended_operations=["GET /employee", "PUT /employee/{id}"],
            resource_ids=[employee_id],
            details={"entity": "employee", "employeeId": employee_id, "updated": updated},
        )


class DepartmentDeleteWorkflow(BaseWorkflow):
    family = TaskFamily.DEPARTMENTS
    entity_type = "department"
    supported_operations = (Operation.DELETE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "department")
        department = await _find_single_department(client, lookup)
        department_id = _extract_id(department)
        if department_id is None:
            raise WorkflowExecutionError("Matched department did not include an id")

        await client.delete(f"/department/{department_id}")

        return WorkflowResult(
            name="department_delete",
            intended_operations=["GET /department", "DELETE /department/{id}"],
            resource_ids=[department_id],
            details={"entity": "department", "deletedId": department_id},
        )


class ProjectDeleteWorkflow(BaseWorkflow):
    family = TaskFamily.PROJECTS
    entity_type = "project"
    supported_operations = (Operation.DELETE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "project")
        project = await _find_single_project(client, lookup)
        project_id = _extract_id(project)
        if project_id is None:
            raise WorkflowExecutionError("Matched project did not include an id")

        await client.delete(f"/project/{project_id}")

        return WorkflowResult(
            name="project_delete",
            intended_operations=["GET /project", "DELETE /project/{id}"],
            resource_ids=[project_id],
            details={"entity": "project", "deletedId": project_id},
        )


class VoucherReverseWorkflow(BaseWorkflow):
    family = TaskFamily.CORRECTIONS
    entity_type = "voucher"
    supported_operations = (Operation.REVERSE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "voucher")
        fields = plan.fields_to_set

        voucher = await _find_single_voucher(client, lookup)
        voucher_id = _extract_id(voucher)
        if voucher_id is None:
            raise WorkflowExecutionError("Matched voucher did not include an id")

        reversal_date = _normalize_date(fields.get("date")) or date.today().isoformat()
        response = await client.put(
            f"/ledger/voucher/{voucher_id}/:reverse",
            params={"date": reversal_date},
        )
        reversed_voucher = client.unwrap_value(response)

        return WorkflowResult(
            name="voucher_reverse",
            intended_operations=["GET /ledger/voucher", "PUT /ledger/voucher/{id}/:reverse"],
            resource_ids=[voucher_id],
            details={
                "entity": "voucher",
                "sourceVoucherId": voucher_id,
                "reversed": reversed_voucher,
            },
        )


class TravelExpenseDeleteWorkflow(BaseWorkflow):
    family = TaskFamily.TRAVEL_EXPENSES
    entity_type = "travel_expense"
    supported_operations = (Operation.DELETE,)

    async def execute(self, *, plan: TaskPlan, client: TripletexClient) -> WorkflowResult:
        lookup = _require_reference(plan, "travel_expense")
        expense = await _find_single_travel_expense(client, lookup)
        expense_id = _extract_id(expense)
        if expense_id is None:
            raise WorkflowExecutionError("Matched travel expense did not include an id")

        await client.delete(f"/travelExpense/{expense_id}")

        return WorkflowResult(
            name="travel_expense_delete",
            intended_operations=["GET /travelExpense", "DELETE /travelExpense/{id}"],
            resource_ids=[expense_id],
            details={"entity": "travel_expense", "deletedId": expense_id},
        )


async def _find_single_voucher(
    client: TripletexClient,
    lookup: dict[str, Any],
) -> dict[str, Any]:
    # Path 1: direct voucher id
    voucher_id = _coerce_int(lookup.get("id"))
    if voucher_id is not None:
        payload = await client.get(
            f"/ledger/voucher/{voucher_id}",
            params={"fields": client.select_fields("id", "voucherNumber", "date", "description")},
        )
        voucher = client.unwrap_value(payload)
        if isinstance(voucher, dict):
            return voucher
        raise WorkflowExecutionError(
            f"Voucher lookup by id {voucher_id} did not return a voucher"
        )

    # Path 2: voucher number
    voucher_number = _stringify_lookup_value(lookup.get("voucherNumber") or lookup.get("number"))
    if voucher_number:
        params = _compact_mapping(
            {
                "numberFrom": voucher_number,
                "numberTo": voucher_number,
                "count": 2,
                "fields": client.select_fields("id", "voucherNumber", "date", "description"),
            }
        )
        payload = await client.get("/ledger/voucher", params=params)
        matches = client.unwrap_values(payload)
        if len(matches) == 0:
            raise WorkflowExecutionError(f"No voucher matched lookup {lookup!r}")
        if len(matches) > 1:
            raise WorkflowExecutionError(f"Voucher lookup was ambiguous for {lookup!r}")
        return matches[0]

    # Path 3: customer name/org → find their most recent paid invoice → get payment voucher
    customer_name = lookup.get("name") or lookup.get("customerName")
    org_number = _normalize_org_number(lookup.get("organizationNumber"))
    if customer_name or org_number:
        customer_lookup: dict[str, Any] = {}
        if customer_name:
            customer_lookup["customerName"] = customer_name
        if org_number:
            customer_lookup["organizationNumber"] = org_number
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id for voucher lookup")

        # Find most recent invoice for this customer (paid ones have vouchers)
        inv_payload = await client.get(
            "/invoice",
            params={
                "customerId": customer_id,
                "count": 1,
                "sorting": "id desc",
                "fields": client.select_fields(
                    "id", "invoiceNumber", "voucher(id,voucherNumber,date)"
                ),
            },
        )
        invoices = client.unwrap_values(inv_payload)
        if not invoices:
            raise WorkflowExecutionError(
                f"No invoice found for customer to reverse voucher for {customer_name!r}"
            )
        invoice = invoices[0]
        voucher = invoice.get("voucher") if isinstance(invoice, dict) else None
        if isinstance(voucher, dict) and voucher.get("id"):
            return voucher

        # Fallback: search ledger vouchers by invoice number
        inv_number = invoice.get("invoiceNumber") if isinstance(invoice, dict) else None
        if inv_number:
            v_payload = await client.get(
                "/ledger/voucher",
                params={
                    "numberFrom": str(inv_number),
                    "numberTo": str(inv_number),
                    "count": 1,
                    "fields": client.select_fields("id", "voucherNumber", "date"),
                },
            )
            vouchers = client.unwrap_values(v_payload)
            if vouchers:
                return vouchers[0]

        raise WorkflowExecutionError(
            f"Could not find payment voucher for customer {customer_name!r}"
        )

    raise WorkflowExecutionError("Voucher lookup requires id, voucherNumber, or customer name")


async def _find_single_travel_expense(
    client: TripletexClient,
    lookup: dict[str, Any],
) -> dict[str, Any]:
    expense_id = _coerce_int(lookup.get("id"))
    if expense_id is not None:
        payload = await client.get(
            f"/travelExpense/{expense_id}",
            params={"fields": client.select_fields("id", "title")},
        )
        expense = client.unwrap_value(payload)
        if isinstance(expense, dict):
            return expense
        raise WorkflowExecutionError(
            f"Travel expense lookup by id {expense_id} did not return an expense"
        )

    params: dict[str, Any] = {
        "count": 2,
        "sorting": "id desc",
        "fields": client.select_fields("id", "title"),
    }

    title = lookup.get("title")
    if isinstance(title, str) and title.strip():
        params["title"] = title.strip()

    employee_lookup = _as_dict(lookup.get("employeeLookup"))
    if employee_lookup:
        employee = await _find_single_employee(client, employee_lookup)
        employee_id = _extract_id(employee)
        if employee_id is not None:
            params["employeeId"] = employee_id

    if set(params) <= {"count", "sorting", "fields"}:
        raise WorkflowExecutionError(
            "Travel expense lookup requires id, title, or employee reference"
        )

    payload = await client.get("/travelExpense", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No travel expense matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Travel expense lookup was ambiguous for {lookup!r}")
    return matches[0]


async def _find_default_employee(client: TripletexClient) -> dict[str, Any]:
    payload = await client.get(
        "/employee",
        params={
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
        raise WorkflowExecutionError("No default employee was available")
    return matches[0]


async def _find_single_project(
    client: TripletexClient, lookup: dict[str, Any]
) -> dict[str, Any]:
    params = _compact_mapping(
        {
            "id": lookup.get("id"),
            "name": lookup.get("name"),
            "number": lookup.get("number"),
            "count": 2,
            "sorting": "id",
            "fields": client.select_fields("id", "name", "number"),
        }
    )
    if not params or set(params) <= {"count", "sorting", "fields"}:
        raise WorkflowExecutionError("Project lookup requires id, name, or number")

    payload = await client.get("/project", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No project matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Project lookup was ambiguous for {lookup!r}")
    return matches[0]


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


async def _find_single_invoice(
    client: TripletexClient,
    lookup: dict[str, Any],
) -> dict[str, Any]:
    invoice_id = _coerce_int(lookup.get("id"))
    if invoice_id is not None:
        try:
            payload = await client.get(
                f"/invoice/{invoice_id}",
                params={
                    "fields": client.select_fields(
                        "id",
                        "invoiceNumber",
                        "invoiceDate",
                        "amount",
                        "amountOutstanding",
                        "isCreditNote",
                        "isCredited",
                    )
                },
            )
        except TripletexAPIError as exc:
            if exc.status_code != 404 or "invoiceNumber" in lookup:
                raise
            lookup = {**lookup, "invoiceNumber": str(invoice_id)}
        else:
            invoice = client.unwrap_value(payload)
            if isinstance(invoice, dict):
                return invoice
            raise WorkflowExecutionError(
                f"Invoice lookup by id {invoice_id} did not return an invoice"
            )

    params = _compact_mapping(
        {
            "invoiceDateFrom": _invoice_date_from_lookup(lookup),
            "invoiceDateTo": _invoice_date_to_lookup(lookup),
            "invoiceNumber": _stringify_lookup_value(lookup.get("invoiceNumber")),
            "count": 2,
            "fields": client.select_fields(
                "id",
                "invoiceNumber",
                "invoiceDate",
                "amount",
                "amountExcludingVat",
                "amountExcludingVatCurrency",
                "amountOutstanding",
                "isCreditNote",
                "isCredited",
            ),
        }
    )

    customer_lookup = _as_dict(lookup.get("customerLookup"))
    if customer_lookup:
        customer = await _find_single_customer(client, customer_lookup)
        customer_id = _extract_id(customer)
        if customer_id is None:
            raise WorkflowExecutionError("Matched customer did not include an id")
        params["customerId"] = customer_id

    if "invoiceNumber" not in params and "customerId" not in params:
        raise WorkflowExecutionError("Invoice lookup requires id, invoiceNumber, or customerLookup")

    payload = await client.get("/invoice", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No invoice matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Invoice lookup was ambiguous for {lookup!r}")
    return matches[0]


async def _find_invoice_payment_type(
    client: TripletexClient,
    lookup: dict[str, Any] | None,
) -> dict[str, Any]:
    fields = client.select_fields(
        "id",
        "description",
        "displayName",
        "sequence",
        "currencyCode",
        "debitAccount(number,name)",
    )
    payment_type_id = _coerce_int(lookup.get("id")) if lookup else None
    if payment_type_id is not None:
        payload = await client.get(
            f"/invoice/paymentType/{payment_type_id}",
            params={"fields": fields},
        )
        payment_type = client.unwrap_value(payload)
        if isinstance(payment_type, dict):
            return payment_type
        raise WorkflowExecutionError(
            f"Invoice payment type lookup by id {payment_type_id} did not return a payment type"
        )

    params = _compact_mapping(
        {
            "description": lookup.get("description") if lookup else None,
            "query": lookup.get("query") if lookup else None,
            "count": 10 if not lookup else 2,
            "sorting": "sequence,id",
            "fields": fields,
        }
    )

    payload = await client.get("/invoice/paymentType", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No invoice payment type matched lookup {lookup!r}")

    if lookup:
        exact_matches = _filter_payment_types(matches, lookup)
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise WorkflowExecutionError(
                f"Invoice payment type lookup was ambiguous for {lookup!r}"
            )
        if len(matches) == 1:
            return matches[0]
        raise WorkflowExecutionError(
            f"Invoice payment type lookup was ambiguous for {lookup!r}"
        )

    return _pick_default_payment_type(matches)


async def _resolve_project_manager(
    client: TripletexClient, lookup: dict[str, Any] | None
) -> dict[str, Any]:
    if lookup:
        return await _find_single_employee(client, lookup, require_assignable=True)
    return await _find_default_project_manager(client)


async def _resolve_employee_department(
    client: TripletexClient,
    fields: dict[str, Any],
) -> dict[str, Any]:
    department_lookup = _as_dict(fields.get("department"))
    department_id = _coerce_int(fields.get("departmentId"))
    if department_lookup is None and department_id is not None:
        department_lookup = {"id": department_id}
    if department_lookup:
        return await _find_single_department(client, department_lookup)
    return await _find_default_department(client)


async def _find_default_department(client: TripletexClient) -> dict[str, Any]:
    payload = await client.get(
        "/department",
        params={
            "count": 1,
            "sorting": "id",
            "fields": client.select_fields("id", "name", "departmentNumber"),
        },
    )
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError("No default department was available for employee creation")
    return matches[0]


async def _find_single_department(
    client: TripletexClient,
    lookup: dict[str, Any],
) -> dict[str, Any]:
    params = _compact_mapping(
        {
            "id": lookup.get("id"),
            "name": lookup.get("name"),
            "departmentNumber": lookup.get("departmentNumber") or lookup.get("number"),
            "count": 2,
            "sorting": "id",
            "fields": client.select_fields("id", "name", "departmentNumber"),
        }
    )
    if not params or set(params) <= {"count", "sorting", "fields"}:
        raise WorkflowExecutionError("Department lookup requires id, name, or departmentNumber")

    payload = await client.get("/department", params=params)
    matches = client.unwrap_values(payload)
    if len(matches) == 0:
        raise WorkflowExecutionError(f"No department matched lookup {lookup!r}")
    if len(matches) > 1:
        raise WorkflowExecutionError(f"Department lookup was ambiguous for {lookup!r}")
    return matches[0]


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


def _invoice_line_field_list(fields: dict[str, Any]) -> list[dict[str, Any]]:
    lines_raw = fields.get("lines")
    if isinstance(lines_raw, list) and lines_raw:
        return [_as_dict(line) or {} for line in lines_raw]
    return [_as_dict(fields.get("line")) or {}]


async def _build_invoice_order_lines(
    client: TripletexClient,
    line_fields_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    needs_vat = any(_coerce_number(line.get("vatPercent")) is not None for line in line_fields_list)
    vat_types = await _fetch_vat_types(client) if needs_vat else []
    return [
        await _build_invoice_order_line(client, line_fields, vat_types=vat_types)
        for line_fields in line_fields_list
    ]


def _invoice_date(fields: dict[str, Any]) -> str:
    return _normalize_date(fields.get("invoiceDate")) or date.today().isoformat()


def _invoice_due_date(fields: dict[str, Any], invoice_date: str) -> str:
    return _normalize_date(fields.get("invoiceDueDate")) or _add_days(
        invoice_date, _DEFAULT_INVOICE_DUE_DAYS
    )


def _invoice_delivery_date(fields: dict[str, Any], invoice_date: str) -> str:
    return _normalize_date(fields.get("deliveryDate")) or invoice_date


async def _invoice_from_order_conversion(
    *,
    client: TripletexClient,
    payload: Any,
    customer_lookup: dict[str, Any],
    invoice_date: str,
) -> dict[str, Any]:
    if isinstance(payload, dict):
        if _extract_id(payload) is not None:
            return payload
        for key in ("invoice", "createdInvoice"):
            nested = payload.get(key)
            if isinstance(nested, dict) and _extract_id(nested) is not None:
                return nested
        invoice_id = _coerce_int(payload.get("invoiceId"))
        if invoice_id is not None:
            return await _find_single_invoice(client, {"id": invoice_id})

    return await _find_single_invoice(
        client,
        {
            "customerLookup": customer_lookup,
            "invoiceDate": invoice_date,
        },
    )


def _resolve_invoice_payment_amount(
    fields: dict[str, Any],
    invoice: dict[str, Any],
    order_lines: list[dict[str, Any]] | None = None,
) -> float:
    paid_amount = _coerce_number(fields.get("paidAmount"))
    if paid_amount is not None and paid_amount > 0:
        normalized_paid_amount = _normalize_invoice_payment_amount(
            paid_amount=paid_amount,
            invoice=invoice,
            paid_amount_excluding_vat=fields.get("paidAmountExcludingVat") is True,
        )
        if normalized_paid_amount > 0:
            return normalized_paid_amount

    paid_amount = _coerce_number(invoice.get("amountOutstanding"))
    if paid_amount is not None and paid_amount > 0:
        return paid_amount

    paid_amount = _coerce_number(invoice.get("amount"))
    if paid_amount is not None and paid_amount > 0:
        return paid_amount

    total = 0.0
    for line in order_lines or []:
        count = _coerce_number(line.get("count")) or 1.0
        unit_price = _coerce_number(line.get("unitPriceExcludingVatCurrency"))
        if unit_price is not None:
            total += count * unit_price
    if total <= 0:
        raise WorkflowExecutionError("Invoice payment requires a positive paid amount")
    return total


def _normalize_invoice_payment_amount(
    *,
    paid_amount: float,
    invoice: dict[str, Any],
    paid_amount_excluding_vat: bool,
) -> float:
    if not paid_amount_excluding_vat:
        return paid_amount

    outstanding = _coerce_number(invoice.get("amountOutstanding"))
    if outstanding is None or outstanding <= 0:
        return paid_amount

    amount_excluding_vat = _coerce_number(invoice.get("amountExcludingVat"))
    if amount_excluding_vat is None:
        amount_excluding_vat = _coerce_number(invoice.get("amountExcludingVatCurrency"))

    tolerance = 0.01
    if amount_excluding_vat is not None and abs(amount_excluding_vat - paid_amount) <= tolerance:
        if outstanding + tolerance >= paid_amount:
            return outstanding

    return paid_amount


async def _fetch_vat_types(client: TripletexClient) -> list[dict[str, Any]]:
    """Fetch available VAT types from the Tripletex environment."""
    try:
        payload = await client.get(
            "/vat",
            params={
                "count": 20,
                "fields": client.select_fields("id", "number", "name", "percentage"),
            },
        )
        return client.unwrap_values(payload)
    except Exception:
        return []


def _resolve_vat_type_id(
    vat_types: list[dict[str, Any]], vat_percent: float | None
) -> int | None:
    if vat_percent is None or not vat_types:
        return None
    # Match by percentage field (e.g. 25.0 → id for 25% VAT type)
    for vt in vat_types:
        pct = vt.get("percentage")
        if isinstance(pct, (int, float)) and abs(float(pct) - vat_percent) < 0.1:
            return _extract_id(vt)
    return None


async def _build_invoice_order_line(
    client: TripletexClient,
    line_fields: dict[str, Any],
    *,
    vat_types: list[dict[str, Any]] | None = None,
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

    vat_type_id: int | None = None
    vat_percent = _coerce_number(line_fields.get("vatPercent"))
    if vat_percent is not None and vat_types:
        vat_type_id = _resolve_vat_type_id(vat_types, vat_percent)

    return _compact_mapping(
        {
            "product": {"id": product_id} if product_id is not None else None,
            "description": description.strip() if isinstance(description, str) else None,
            "count": normalized_count,
            "unitPriceExcludingVatCurrency": unit_price,
            "vatType": {"id": vat_type_id} if vat_type_id is not None else None,
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
        account
        for account in accounts
        if isinstance(account, dict) and account.get("isInvoiceAccount")
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


def _normalize_language(value: Any) -> str | None:
    """Normalise a language hint to a Tripletex-accepted code (NO or EN)."""
    if not isinstance(value, str):
        return None
    upper = value.strip().upper()
    if upper in {"NO", "NB", "NN", "NOR"}:
        return "NO"
    if upper in {"EN", "ENG", "ENGLISH"}:
        return "EN"
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


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
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


def _invoice_date_from_lookup(lookup: dict[str, Any]) -> str:
    explicit_from = _normalize_date(lookup.get("invoiceDateFrom"))
    if explicit_from is not None:
        return explicit_from

    exact_date = _normalize_date(lookup.get("invoiceDate"))
    if exact_date is not None:
        return exact_date

    return _DEFAULT_INVOICE_LOOKUP_DATE_FROM


def _invoice_date_to_lookup(lookup: dict[str, Any]) -> str:
    explicit_to = _normalize_date(lookup.get("invoiceDateTo"))
    if explicit_to is not None:
        return explicit_to

    exact_date = _normalize_date(lookup.get("invoiceDate"))
    if exact_date is not None:
        return _add_days(exact_date, 1)

    return _DEFAULT_INVOICE_LOOKUP_DATE_TO


def _stringify_lookup_value(value: Any) -> str | None:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _invoice_lookup_operation(lookup: dict[str, Any]) -> str:
    return "GET /invoice/{id}" if _coerce_int(lookup.get("id")) is not None else "GET /invoice"


def _filter_payment_types(
    payment_types: list[Any],
    lookup: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized_description = _normalize_lookup_text(lookup.get("description"))
    normalized_query = _normalize_lookup_text(lookup.get("query"))
    matches: list[dict[str, Any]] = []

    for payment_type in payment_types:
        if not isinstance(payment_type, dict):
            continue
        description = _normalize_lookup_text(payment_type.get("description"))
        display_name = _normalize_lookup_text(payment_type.get("displayName"))
        if normalized_description and normalized_description in {description, display_name}:
            matches.append(payment_type)
            continue
        if normalized_query and normalized_query in {description, display_name}:
            matches.append(payment_type)

    return matches


def _pick_default_payment_type(payment_types: list[Any]) -> dict[str, Any]:
    candidates = [payment_type for payment_type in payment_types if isinstance(payment_type, dict)]
    if not candidates:
        raise WorkflowExecutionError("No invoice payment types were available")

    for payment_type in candidates:
        text = " ".join(
            part
            for part in (
                _normalize_lookup_text(payment_type.get("description")),
                _normalize_lookup_text(payment_type.get("displayName")),
                _normalize_lookup_text(_nested_value(payment_type, "debitAccount", "name")),
                _normalize_lookup_text(_nested_value(payment_type, "debitAccount", "number")),
            )
            if part
        )
        if "bank" in text:
            return payment_type

    return candidates[0]


def _normalize_lookup_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.lower().split())


def _nested_value(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
