from __future__ import annotations

import json
from datetime import date, timedelta

import httpx
import pytest

from tripletex_agent.client import TripletexClient
from tripletex_agent.task_plan import (
    ActionSemantics,
    EntityPayload,
    EntityReference,
    Operation,
    TaskFamily,
    TaskPlan,
)
from tripletex_agent.workflows import (
    CustomerCreateWorkflow,
    EmployeeCreateWorkflow,
    InvoiceCreateWorkflow,
    InvoiceCreditNoteWorkflow,
    InvoicePaymentWorkflow,
    ProductCreateWorkflow,
    ProjectCreateWorkflow,
    TravelExpenseCreateWorkflow,
)


@pytest.mark.asyncio
async def test_customer_create_workflow_posts_expected_payload() -> None:
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v2/customer"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["name"] == "ACME AS"
        assert payload["organizationNumber"] == "123456789"
        return httpx.Response(200, json={"value": {"id": 101, "name": "ACME AS"}})

    workflow = CustomerCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.CUSTOMERS_PRODUCTS,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="customer",
                fields={
                    "name": "ACME AS",
                    "organizationNumber": "123 456 789",
                    "email": "finance@acme.test",
                },
            )
        ],
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [101]
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_product_create_workflow_posts_expected_payload() -> None:
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v2/product"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["name"] == "Consulting Hour"
        assert payload["number"] == "CONS-001"
        assert payload["priceExcludingVatCurrency"] == 1500.0
        return httpx.Response(200, json={"value": {"id": 202, "name": "Consulting Hour"}})

    workflow = ProductCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.CUSTOMERS_PRODUCTS,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="product",
                fields={
                    "name": "Consulting Hour",
                    "number": "CONS-001",
                    "priceExcludingVatCurrency": 1500.0,
                },
            )
        ],
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [202]
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_employee_create_workflow_resolves_default_department_and_sets_user_type() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/department":
            return httpx.Response(
                200,
                json={"values": [{"id": 854238, "name": "Default Department"}]},
            )
        if request.method == "POST" and request.url.path == "/v2/employee":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["firstName"] == "Ola"
            assert payload["lastName"] == "Nordmann"
            assert payload["email"] == "ola@example.test"
            assert payload["userType"] == "NO_ACCESS"
            assert payload["department"] == {"id": 854238}
            return httpx.Response(
                200,
                json={"value": {"id": 303, "displayName": "Ola Nordmann"}},
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = EmployeeCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.EMPLOYEES,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="employee",
                fields={
                    "firstName": "Ola",
                    "lastName": "Nordmann",
                    "email": "ola@example.test",
                },
            )
        ],
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [303]
    assert recorded == [("GET", "/v2/department"), ("POST", "/v2/employee")]


@pytest.mark.asyncio
async def test_invoice_create_workflow_posts_invoice_without_bank_account_mutation_by_default(
) -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 555, "name": "ACME AS"}]})
        if request.method == "POST" and request.url.path == "/v2/invoice":
            assert request.url.params["sendToCustomer"] == "false"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["customer"] == {"id": 555}
            assert payload["orders"][0]["orderLines"][0]["description"] == "Maintenance"
            assert payload["orders"][0]["orderLines"][0]["unitPriceExcludingVatCurrency"] == 8750.0
            return httpx.Response(200, json={"value": {"id": 909, "invoiceNumber": 1}})
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = InvoiceCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "customerLookup": {"customerName": "ACME AS"},
                    "line": {
                        "description": "Maintenance",
                        "unitPriceExcludingVatCurrency": 8750.0,
                    },
                },
            )
        ],
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [909]
    assert result.details["sendToCustomer"] is False
    assert result.details["invoiceBankAccountUpdated"] is False
    assert recorded == [("GET", "/v2/customer"), ("POST", "/v2/invoice")]


@pytest.mark.asyncio
async def test_invoice_create_workflow_configures_bank_account_and_sends_invoice_when_requested(
) -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 555, "name": "ACME AS"}]})
        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": [{"id": 202, "name": "Consulting Hour"}]})
        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 11,
                            "number": 1920,
                            "name": "Bankinnskudd",
                            "isBankAccount": True,
                            "isInvoiceAccount": True,
                            "bankAccountNumber": "",
                        }
                    ]
                },
            )
        if request.method == "PUT" and request.url.path == "/v2/ledger/account/11":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["bankAccountNumber"] == "12345678903"
            return httpx.Response(
                200,
                json={
                    "value": {
                        "id": 11,
                        "isInvoiceAccount": True,
                        "bankAccountNumber": "12345678903",
                    }
                },
            )
        if request.method == "POST" and request.url.path == "/v2/invoice":
            assert request.url.params["sendToCustomer"] == "true"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["customer"] == {"id": 555}
            assert payload["invoiceDate"] == date.today().isoformat()
            assert payload["invoiceDueDate"] == (date.today() + timedelta(days=14)).isoformat()
            order = payload["orders"][0]
            assert order["customer"] == {"id": 555}
            assert order["deliveryDate"] == date.today().isoformat()
            assert order["orderLines"][0]["product"] == {"id": 202}
            assert order["orderLines"][0]["count"] == 2
            return httpx.Response(200, json={"value": {"id": 909, "invoiceNumber": 1}})
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = InvoiceCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="invoice",
                fields={
                    "customerLookup": {"customerName": "ACME AS"},
                    "line": {
                        "productLookup": {"name": "Consulting Hour"},
                        "count": 2,
                    },
                },
            )
        ],
        action_semantics=ActionSemantics(send_to_customer=True),
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [909]
    assert result.details["sendToCustomer"] is True
    assert result.details["invoiceBankAccountId"] == 11
    assert result.details["invoiceBankAccountUpdated"] is True
    assert recorded == [
        ("GET", "/v2/customer"),
        ("GET", "/v2/product"),
        ("GET", "/v2/ledger/account"),
        ("PUT", "/v2/ledger/account/11"),
        ("POST", "/v2/invoice"),
    ]


@pytest.mark.asyncio
async def test_invoice_payment_workflow_looks_up_invoice_and_registers_payment() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/invoice":
            assert request.url.params["invoiceNumber"] == "2"
            assert request.url.params["invoiceDateFrom"] == "2000-01-01"
            assert request.url.params["invoiceDateTo"] == "2100-01-01"
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 909,
                            "invoiceNumber": 2,
                            "amount": 1250.0,
                            "amountOutstanding": 1250.0,
                            "isCreditNote": False,
                        }
                    ]
                },
            )
        if request.method == "GET" and request.url.path == "/v2/invoice/paymentType":
            assert request.url.params["description"] == "Betalt til bank"
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 33535763,
                            "description": "Betalt til bank",
                            "displayName": "Betalt til bank",
                        }
                    ]
                },
            )
        if request.method == "PUT" and request.url.path == "/v2/invoice/909/:payment":
            assert request.url.params["paymentDate"] == "2026-03-20"
            assert request.url.params["paymentTypeId"] == "33535763"
            assert request.url.params["paidAmount"] == "1250.0"
            return httpx.Response(200, json={"value": {"id": 909, "amountOutstanding": 0.0}})
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = InvoicePaymentWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.REGISTER_PAYMENT,
        entities_to_find=[EntityReference(entity_type="invoice", lookup={"invoiceNumber": "2"})],
        fields_to_set={
            "paymentDate": "2026-03-20",
            "paidAmount": 1250.0,
            "paymentTypeLookup": {"description": "Betalt til bank"},
        },
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [909]
    assert recorded == [
        ("GET", "/v2/invoice"),
        ("GET", "/v2/invoice/paymentType"),
        ("PUT", "/v2/invoice/909/:payment"),
    ]


@pytest.mark.asyncio
async def test_invoice_payment_workflow_falls_back_from_numeric_id_to_invoice_number() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/invoice/3":
            return httpx.Response(404, json={"message": "Object not found"})
        if request.method == "GET" and request.url.path == "/v2/invoice":
            assert request.url.params["invoiceNumber"] == "3"
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 909,
                            "invoiceNumber": 3,
                            "amount": 625.0,
                            "amountOutstanding": 625.0,
                            "isCreditNote": False,
                        }
                    ]
                },
            )
        if request.method == "GET" and request.url.path == "/v2/invoice/paymentType":
            return httpx.Response(
                200,
                json={"values": [{"id": 33535763, "description": "Betalt til bank"}]},
            )
        if request.method == "PUT" and request.url.path == "/v2/invoice/909/:payment":
            return httpx.Response(200, json={"value": {"id": 909, "amountOutstanding": 0.0}})
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = InvoicePaymentWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.REGISTER_PAYMENT,
        entities_to_find=[EntityReference(entity_type="invoice", lookup={"id": 3})],
        fields_to_set={"paymentDate": "2026-03-20", "paidAmount": 625.0},
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [909]
    assert recorded == [
        ("GET", "/v2/invoice/3"),
        ("GET", "/v2/invoice"),
        ("GET", "/v2/invoice/paymentType"),
        ("PUT", "/v2/invoice/909/:payment"),
    ]


@pytest.mark.asyncio
async def test_invoice_credit_note_workflow_creates_credit_note() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/invoice":
            assert request.url.params["invoiceNumber"] == "2"
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 909,
                            "invoiceNumber": 2,
                            "amountOutstanding": 1250.0,
                            "isCreditNote": False,
                        }
                    ]
                },
            )
        if request.method == "PUT" and request.url.path == "/v2/invoice/909/:createCreditNote":
            assert request.url.params["date"] == "2026-03-20"
            assert request.url.params["comment"] == "Customer cancellation"
            assert request.url.params["sendToCustomer"] == "false"
            return httpx.Response(
                200,
                json={"value": {"id": 910, "invoiceNumber": 3, "creditedInvoice": {"id": 909}}},
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = InvoiceCreditNoteWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.INVOICING,
        operation=Operation.CREATE_CREDIT_NOTE,
        entities_to_find=[EntityReference(entity_type="invoice", lookup={"invoiceNumber": "2"})],
        fields_to_set={
            "creditNoteDate": "2026-03-20",
            "comment": "Customer cancellation",
        },
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [910]
    assert recorded == [
        ("GET", "/v2/invoice"),
        ("PUT", "/v2/invoice/909/:createCreditNote"),
    ]


@pytest.mark.asyncio
async def test_project_create_workflow_resolves_customer_before_posting() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {"id": 555, "name": "ACME AS", "organizationNumber": "123456789"}
                    ]
                },
            )
        if request.method == "GET" and request.url.path == "/v2/employee":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 999,
                            "displayName": "Manager Example",
                            "email": "manager@example.test",
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/v2/project":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["name"] == "Migration Project"
            assert payload["customer"] == {"id": 555}
            assert payload["projectManager"] == {"id": 999}
            assert payload["startDate"] == date.today().isoformat()
            return httpx.Response(200, json={"value": {"id": 777, "name": "Migration Project"}})
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = ProjectCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.PROJECTS,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="project",
                fields={
                    "name": "Migration Project",
                    "customerLookup": {"customerName": "ACME AS"},
                },
            )
        ],
        confidence=0.9,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [777]
    assert recorded == [("GET", "/v2/customer"), ("GET", "/v2/employee"), ("POST", "/v2/project")]


@pytest.mark.asyncio
async def test_travel_expense_create_workflow_with_default_employee() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/employee":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 303,
                            "firstName": "Ola",
                            "lastName": "Nordmann",
                            "displayName": "Ola Nordmann",
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/v2/travelExpense":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["employee"] == {"id": 303}
            assert payload["title"] == "Business trip to Bergen"
            assert payload["departureDateTime"] == "2026-03-15"
            assert payload["returnDateTime"] == "2026-03-17"
            return httpx.Response(
                201,
                json={"value": {"id": 500, "title": "Business trip to Bergen"}},
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = TravelExpenseCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="travel_expense",
                fields={
                    "title": "Business trip to Bergen",
                    "departureDate": "2026-03-15",
                    "returnDate": "2026-03-17",
                },
            )
        ],
        confidence=0.8,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids == [500]
    assert result.details["employeeId"] == 303
    assert result.details["expenseId"] == 500
    assert result.details["delivered"] is False
    assert recorded == [("GET", "/v2/employee"), ("POST", "/v2/travelExpense")]


@pytest.mark.asyncio
async def test_travel_expense_create_workflow_with_employee_lookup_and_costs() -> None:
    recorded: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/employee":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 303,
                            "firstName": "Kari",
                            "lastName": "Hansen",
                            "displayName": "Kari Hansen",
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/v2/travelExpense":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["employee"] == {"id": 303}
            return httpx.Response(
                201,
                json={"value": {"id": 500, "title": "Trip"}},
            )
        if request.method == "POST" and request.url.path == "/v2/travelExpense/cost":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["travelExpense"] == {"id": 500}
            assert payload["amountNOKInclVAT"] in [2000.0, 500.0]
            return httpx.Response(
                201,
                json={"value": {"id": len(recorded) + 600}},
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url.path}")

    workflow = TravelExpenseCreateWorkflow()
    plan = TaskPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.CREATE,
        entities_to_create=[
            EntityPayload(
                entity_type="travel_expense",
                fields={
                    "title": "Trip",
                    "departureDate": "2026-03-15",
                    "returnDate": "2026-03-17",
                    "employeeLookup": {
                        "firstName": "Kari",
                        "lastName": "Hansen",
                    },
                    "costs": [
                        {"description": "Hotel", "amount": 2000.0},
                        {"description": "Meals", "amount": 500.0},
                    ],
                },
            )
        ],
        confidence=0.8,
    )

    async with TripletexClient(
        base_url="https://example.test/v2",
        session_token="token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await workflow.execute(plan=plan, client=client)

    assert result.resource_ids[0] == 500
    assert len(result.details["childIds"]) == 2
    assert recorded == [
        ("GET", "/v2/employee"),
        ("POST", "/v2/travelExpense"),
        ("POST", "/v2/travelExpense/cost"),
        ("POST", "/v2/travelExpense/cost"),
    ]
