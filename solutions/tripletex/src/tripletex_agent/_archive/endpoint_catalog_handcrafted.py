"""Curated Tripletex endpoint catalog used by the LLM executor and validator."""

from __future__ import annotations

from typing import Any

ENDPOINT_CATALOG: list[dict[str, Any]] = [
    # ── Customer ──────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/customer",
        "params": [
            "id", "name", "email", "organizationNumber",
            "customerAccountNumber", "isSupplier", "isCustomer",
            "fields", "from", "count",
        ],
        "description": "Search customers by name, email, or org number.",
    },
    {
        "method": "POST",
        "path": "/customer",
        "required_fields": ["name"],
        "optional_fields": [
            "email", "organizationNumber", "isCustomer", "isSupplier",
            "phoneNumber", "language", "customerAccountNumber",
            "invoiceEmail", "postalAddress", "physicalAddress",
        ],
        "description": "Create a new customer.",
    },
    {
        "method": "PUT",
        "path": "/customer/{id}",
        "required_fields": ["id", "name"],
        "optional_fields": [
            "email", "organizationNumber", "isCustomer", "isSupplier",
            "phoneNumber", "language",
        ],
        "description": "Update an existing customer.",
    },
    {
        "method": "DELETE",
        "path": "/customer/{id}",
        "description": "Delete a customer.",
    },
    # ── Product ───────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/product",
        "params": [
            "number", "name", "fields", "from", "count",
        ],
        "description": "Search products by name or number.",
    },
    {
        "method": "POST",
        "path": "/product",
        "required_fields": ["name"],
        "optional_fields": [
            "number", "priceExcludingVatCurrency", "priceIncludingVatCurrency",
            "costExcludingVatCurrency", "vatType", "productUnit", "description",
            "isInactive", "weight", "weightUnit",
        ],
        "description": "Create a new product.",
    },
    {
        "method": "PUT",
        "path": "/product/{id}",
        "required_fields": ["id", "name"],
        "optional_fields": [
            "number", "priceExcludingVatCurrency", "priceIncludingVatCurrency",
            "costExcludingVatCurrency", "vatType", "description",
        ],
        "description": "Update an existing product.",
    },
    {
        "method": "DELETE",
        "path": "/product/{id}",
        "description": "Delete a product.",
    },
    # ── Employee ──────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/employee",
        "params": [
            "id", "firstName", "lastName", "employeeNumber",
            "fields", "from", "count",
        ],
        "description": "Search employees by name or employee number.",
    },
    {
        "method": "POST",
        "path": "/employee",
        "required_fields": ["firstName", "lastName"],
        "optional_fields": [
            "employeeNumber", "email", "phoneNumberMobile",
            "dateOfBirth", "department", "address",
        ],
        "description": "Create a new employee.",
    },
    {
        "method": "PUT",
        "path": "/employee/{id}",
        "required_fields": ["id", "firstName", "lastName"],
        "optional_fields": [
            "employeeNumber", "email", "phoneNumberMobile",
            "dateOfBirth", "department",
        ],
        "description": "Update an existing employee.",
    },
    {
        "method": "POST",
        "path": "/employee/employment",
        "required_fields": ["employeeId", "startDate", "employmentType"],
        "optional_fields": [
            "endDate", "percentageOfFullTimeEquivalent", "division",
        ],
        "description": "Create an employment record for an employee.",
    },
    {
        "method": "GET",
        "path": "/employee/entitlement",
        "params": ["employeeId", "fields", "from", "count"],
        "description": "List entitlements for an employee.",
    },
    {
        "method": "POST",
        "path": "/employee/entitlement/:grantEntitlementsByTemplate",
        "required_fields": ["employeeId"],
        "optional_fields": [],
        "description": "Grant entitlements to an employee by template.",
    },
    # ── Department ────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/department",
        "params": ["id", "name", "departmentNumber", "fields", "from", "count"],
        "description": "Search departments by name or number.",
    },
    {
        "method": "POST",
        "path": "/department",
        "required_fields": ["name", "departmentNumber"],
        "optional_fields": ["departmentManagerId"],
        "description": "Create a new department.",
    },
    {
        "method": "DELETE",
        "path": "/department/{id}",
        "description": "Delete a department.",
    },
    # ── Project ───────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/project",
        "params": ["id", "name", "number", "projectManagerId", "fields", "from", "count"],
        "description": "Search projects by name or number.",
    },
    {
        "method": "POST",
        "path": "/project",
        "required_fields": ["name", "number", "projectManager"],
        "optional_fields": [
            "description", "startDate", "endDate",
            "projectCategory", "customer", "isClosed",
            "fixedPrice",
        ],
        "description": (
            "Create a new project. 'projectManager' must be an object: "
            '{"id": <employee_id>}. '
            "Example body: "
            '{"name": "My Project", "number": "P001", '
            '"projectManager": {"id": 5}, "fixedPrice": 100000}'
        ),
    },
    {
        "method": "PUT",
        "path": "/project/{id}",
        "required_fields": ["id", "name", "number", "projectManager"],
        "optional_fields": [
            "description", "startDate", "endDate", "isClosed",
            "fixedPrice",
        ],
        "description": (
            "Update an existing project. 'projectManager' must be an object: "
            '{"id": <employee_id>}.'
        ),
    },
    {
        "method": "DELETE",
        "path": "/project/{id}",
        "description": "Delete a project.",
    },
    # ── Invoice ───────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/invoice",
        "params": [
            "id", "invoiceNumber", "customerId",
            "fields", "from", "count",
        ],
        "description": "Search invoices by number or customer ID.",
    },
    {
        "method": "POST",
        "path": "/invoice",
        "params": ["sendToCustomer"],
        "required_fields": ["invoiceDate", "invoiceDueDate", "orders"],
        "optional_fields": ["comment", "paymentTypeId"],
        "description": (
            "Create an invoice from existing orders. 'orders' is a list of order "
            "references: [{\"id\": <order_id>}]. The customer is inferred from the order. "
            "Pass ?sendToCustomer=false to create without sending. "
            "For partial invoicing (e.g. 33%), set the order line amounts to the "
            "partial amount before invoicing. "
            "Example body: "
            "{\"invoiceDate\": \"2026-03-20\", \"invoiceDueDate\": \"2026-04-20\", "
            "\"orders\": [{\"id\": 1}]}"
        ),
    },
    {
        "method": "GET",
        "path": "/invoice/paymentType",
        "params": ["fields", "from", "count"],
        "description": "List available invoice payment types.",
    },
    {
        "method": "PUT",
        "path": "/invoice/{id}/:payment",
        "required_fields": ["paymentDate", "paymentTypeId", "paidAmount"],
        "optional_fields": ["paidAmountCurrency"],
        "description": "Register payment on an invoice.",
    },
    {
        "method": "PUT",
        "path": "/invoice/{id}/:createCreditNote",
        "required_fields": ["invoiceId", "creditNoteDate"],
        "optional_fields": ["comment"],
        "description": "Create a credit note for an invoice.",
    },
    # ── Order ─────────────────────────────────────────────────
    {
        "method": "GET",
        "path": "/order",
        "params": ["id", "number", "customerId", "fields", "from", "count"],
        "description": "Search orders.",
    },
    {
        "method": "POST",
        "path": "/order",
        "required_fields": ["customer", "orderDate", "deliveryDate"],
        "optional_fields": ["orderLines", "receiver", "project"],
        "description": (
            "Create an order. 'customer' must be {\"id\": <customer_id>}. "
            "'project' must be {\"id\": <project_id>} (optional, links order to project). "
            "Each order line needs 'product': {\"id\": <id>}, 'count', and optional "
            "'unitPriceExcludingVatCurrency'. "
            "Example body: "
            "{\"customer\": {\"id\": 1}, \"orderDate\": \"2026-03-20\", "
            "\"deliveryDate\": \"2026-03-20\", \"project\": {\"id\": 5}, "
            "\"orderLines\": [{\"product\": {\"id\": 1}, \"count\": 1, "
            "\"unitPriceExcludingVatCurrency\": 50000}]}"
        ),
    },
    {
        "method": "POST",
        "path": "/order/orderline",
        "required_fields": ["order", "product", "count"],
        "optional_fields": [
            "unitPriceExcludingVatCurrency", "description", "vatType",
        ],
        "description": "Add an order line to an existing order.",
    },
    # ── Travel Expense ────────────────────────────────────────
    {
        "method": "GET",
        "path": "/travelExpense",
        "params": ["employeeId", "status", "fields", "from", "count"],
        "description": "Search travel expenses.",
    },
    {
        "method": "POST",
        "path": "/travelExpense",
        "required_fields": ["employee", "title", "departureDate", "returnDate"],
        "optional_fields": [
            "project", "department", "isCompleted",
            "travelAdvance", "paymentType",
        ],
        "description": (
            "Create a travel expense report. The 'employee' field should be "
            "{\"id\": <employee_id>}."
        ),
    },
    {
        "method": "PUT",
        "path": "/travelExpense/{id}",
        "required_fields": ["id", "employee", "title", "departureDate", "returnDate"],
        "optional_fields": ["project", "department", "isCompleted"],
        "description": "Update a travel expense report.",
    },
    {
        "method": "DELETE",
        "path": "/travelExpense/{id}",
        "description": "Delete a travel expense report.",
    },
    {
        "method": "POST",
        "path": "/travelExpense/cost",
        "required_fields": ["travelExpense", "vatType", "currency", "costCategory", "date"],
        "optional_fields": [
            "rate", "count", "amount", "amountCurrencyIncVat",
            "paymentType", "isRefund", "description",
        ],
        "description": (
            "Add a cost line to a travel expense. 'travelExpense' should be "
            "{\"id\": <travel_expense_id>}."
        ),
    },
    {
        "method": "POST",
        "path": "/travelExpense/mileageAllowance",
        "required_fields": [
            "travelExpense", "rateType", "rateCategory",
            "date", "km", "departureLocation", "destination",
        ],
        "optional_fields": ["isCompanyCar", "passengers", "tollCost"],
        "description": (
            "Add a mileage allowance to a travel expense. 'travelExpense' should be "
            "{\"id\": <travel_expense_id>}."
        ),
    },
    {
        "method": "POST",
        "path": "/travelExpense/perDiemCompensation",
        "required_fields": [
            "travelExpense", "rateType", "rateCategory",
            "countryCode", "travelExpenseZoneId", "overnightAccommodation",
            "location", "dateFrom", "dateTo",
        ],
        "optional_fields": ["isDeductionForBreakfast", "isLunchDeduction", "isDinnerDeduction"],
        "description": "Add a per-diem compensation to a travel expense.",
    },
    {
        "method": "POST",
        "path": "/travelExpense/accommodationAllowance",
        "required_fields": [
            "travelExpense", "rateType", "rateCategory",
            "countryCode", "travelExpenseZoneId",
            "location", "dateFrom", "dateTo",
        ],
        "optional_fields": ["address", "count"],
        "description": "Add an accommodation allowance to a travel expense.",
    },
    # ── Ledger / Voucher ──────────────────────────────────────
    {
        "method": "GET",
        "path": "/ledger/account",
        "params": ["id", "number", "fields", "from", "count"],
        "description": "Search ledger accounts by number.",
    },
    {
        "method": "PUT",
        "path": "/ledger/account/{id}",
        "required_fields": ["id", "number"],
        "optional_fields": ["bankAccountNumber", "bankAccountCountry"],
        "description": "Update a ledger account (e.g., set bank account number).",
    },
    {
        "method": "GET",
        "path": "/ledger/voucher",
        "params": ["id", "dateFrom", "dateTo", "fields", "from", "count"],
        "description": "Search ledger vouchers by date range.",
    },
    {
        "method": "POST",
        "path": "/ledger/voucher",
        "required_fields": ["date", "description"],
        "optional_fields": ["postings"],
        "description": (
            "Create a ledger voucher with postings. Each posting needs "
            "'debit' or 'credit' amounts and an 'account' reference."
        ),
    },
    {
        "method": "DELETE",
        "path": "/ledger/voucher/{id}",
        "description": "Delete a ledger voucher.",
    },
    {
        "method": "POST",
        "path": "/ledger/voucher/{id}/:reverse",
        "required_fields": ["date"],
        "optional_fields": [],
        "description": "Reverse a ledger voucher.",
    },
    # ── Company / Modules ─────────────────────────────────────
    {
        "method": "GET",
        "path": "/company/salesmodules",
        "params": ["fields", "from", "count"],
        "description": "List enabled company modules (sales, invoice, travel, etc.).",
    },
    {
        "method": "PUT",
        "path": "/company/salesmodules",
        "required_fields": [],
        "optional_fields": ["name", "isActive"],
        "description": "Enable or disable a company sales module.",
    },
]


def catalog_as_text() -> str:
    """Render the catalog as a human-readable text block for the LLM system prompt."""
    lines: list[str] = []
    for ep in ENDPOINT_CATALOG:
        method = ep["method"]
        path = ep["path"]
        desc = ep.get("description", "")
        lines.append(f"{method} {path}")
        lines.append(f"  Description: {desc}")
        if ep.get("params"):
            lines.append(f"  Query params: {', '.join(ep['params'])}")
        if ep.get("required_fields"):
            lines.append(f"  Required body fields: {', '.join(ep['required_fields'])}")
        if ep.get("optional_fields"):
            lines.append(f"  Optional body fields: {', '.join(ep['optional_fields'])}")
        lines.append("")
    return "\n".join(lines)
