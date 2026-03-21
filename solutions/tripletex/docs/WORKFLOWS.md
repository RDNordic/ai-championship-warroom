# Workflows

Confidence levels used in this document:
- ✅ **Fully specced** — observed in logs, API sequence confirmed, known postconditions
- 🔶 **Structure known** — state machine understood from spec, implementation details TBD
- ❓ **Endpoint known** — relevant endpoints identified, task requirements unknown

---

## Family: customers_products ✅

### Customer create

**Planner extracts:** name, email, organizationNumber (if given), language, isSupplier,
isCustomer, phoneNumber, phoneNumberMobile, invoiceEmail

**API sequence:**
```
POST /customer
  body: { name, email, language, isCustomer: true, ...other extracted fields }
  expected: 201
```

**Postcondition:** response contains `value.id` and `value.name` matches input.

**Known field mappings:**
- "language English" / "langue anglais" / "Sprache Englisch" → `language: "EN"`
- "language Norwegian" / "norsk" → `language: "NO"`
- Always set `isCustomer: true` unless prompt explicitly says supplier only

**Failure modes:**
- Wrong `language` enum value (must be ISO 639-1 uppercase: EN, NO, DE, FR, ES, PT)
- Missing `isCustomer: true` — Tripletex requires this explicit flag

---

### Product create 🔶

**Planner extracts:** name, number (product code), priceExcludingVatCurrency,
vatType, unit

**API sequence:**
```
POST /product
  body: { name, number, priceExcludingVatCurrency, ...}
  expected: 201
```

**Failure modes:**
- Product number conflicts with existing — check before creating if number is specified

---

## Family: invoicing ✅

### Invoice create (without send)

**Planner extracts:** customerLookup (name + optionally orgNumber), line items
(description OR productLookup, count, unitPriceExcludingVatCurrency), invoiceDate,
invoiceDueDate

**API sequence:**
```
1. GET /customer?customerName={name}&count=2&fields=id,name,organizationNumber
   → resolve to single customer ID (fail if 0 or 2+ results)

2. POST /invoice?sendToCustomer=false
   body: {
     invoiceDate: today,
     invoiceDueDate: today + 14 days,
     customer: { id: <resolved> },
     orders: [{
       customer: { id: <resolved> },
       orderDate: today,
       deliveryDate: today,
       orderLines: [{ description, count, unitPriceExcludingVatCurrency }]
     }]
   }
   expected: 201
```

**Postcondition:** `value.id` exists, `value.customer.id` matches.

---

### Invoice create-and-send ✅

**Same as above but:**
```
POST /invoice?sendToCustomer=true
```

`sendToCustomer` is a query parameter on `POST /invoice`, not a body field.
Do NOT use `PUT /invoice/{id}/:send` as a separate step — use the query param
on creation. This saves one API call and is the efficient path.

**Postcondition check must verify:** invoice was sent, not only created.
Query `GET /invoice/{id}` and check `isCharged: true` or delivery status.

**Critical:** `action_semantics.send_to_customer` from the TaskPlan must drive this.
The workflow must NEVER hardcode `sendToCustomer=false`.

**Multilingual send triggers:** envoyez (FR), senden/schicken (DE), enviar (ES/PT),
send/sende (EN/NO)

---

### Invoice — register payment 🔶

**API sequence:**
```
1. GET /invoice?... → resolve invoice ID (or use ID from previous step)
2. PUT /invoice/{id}/:payment
   body: { paymentDate, paymentTypeId, paidAmount }
```

**Open question:** Which `paymentTypeId` values are valid in competition sandbox?
Need to query `GET /invoice/paymentType` first if not known.

---

### Invoice — credit note 🔶

**API sequence:**
```
1. Resolve existing invoice ID
2. PUT /invoice/{id}/:createCreditNote
   → returns new credit note invoice
```

**Note:** This creates a new invoice that nullifies the original. The original invoice
is also updated. Both changes happen in one call.

---

## Family: employees ✅

### Employee create

**Planner extracts:** firstName, lastName, email, employeeNumber, roles/entitlements,
department, startDate

**API sequence:**
```
1. POST /employee
   body: { firstName, lastName, email, employeeNumber (if given) }
   expected: 201

2. IF role/entitlement requested:
   PUT /employee/entitlement/:grantEntitlementsByTemplate
   body: { employeeId: <from step 1>, template: <role template name> }
```

**High-value scorer check:** The entitlement/role assignment is typically worth the
most points in employee tasks (confirmed: 5/10 pts in example). Always check for
role language in the prompt.

**Role detection (multilingual):**
- "administrator" / "kontoadministrator" / "administrateur" / "Kontoadministrator"
  → apply administrator entitlement template
- "accountant" / "regnskapsfører" → apply accountant template
- Check `GET /employee/entitlement/template` to see available templates if unsure

**Failure modes:**
- Creating employee without entitlement when role was requested → major score loss
- Missing `employeeNumber` when specified in prompt

---

### Employee update 🔶

**API sequence:**
```
1. GET /employee?email={email}&fields=id,firstName,lastName → resolve ID
2. PUT /employee/{id}
   body: { ...existing fields merged with updates }
```

**Note:** PUT in Tripletex is typically a full replacement, not a patch.
Fetch existing values first to avoid nulling unrelated fields.

---

## Family: travel_expenses 🔶

### Travel expense create

**Current status: StubWorkflow — not implemented. This is an active scoring gap.**

**Planner extracts:** employeeLookup (name + email), title/description, fromDate,
toDate, per diem days + rate, cost line items (type, amount, description),
mileage (distance, rate)

**API sequence:**
```
1. GET /employee?email={email}&firstName={first}&lastName={last}&count=2
   → resolve employee ID

2. POST /travelExpense
   body: { employee: {id}, description, travelDetails... }
   → get travelExpenseId

3. FOR EACH per diem:
   POST /travelExpense/perDiemCompensation
   body: { travelExpense: {id: travelExpenseId}, startDate, endDate, ... }

4. FOR EACH cost (flight, taxi, hotel receipt, etc.):
   POST /travelExpense/cost
   body: { travelExpense: {id: travelExpenseId}, costCategory, amountCurrencyIncVat, ... }

5. FOR EACH mileage:
   POST /travelExpense/mileageAllowance
   body: { travelExpense: {id: travelExpenseId}, date, km, ... }

6. IF "submit" / "deliver" in prompt:
   PUT /travelExpense/:deliver  body: { ids: [travelExpenseId] }

7. IF "approve" in prompt:
   PUT /travelExpense/:approve  body: { ids: [travelExpenseId] }
```

**Open questions:**
- Which `costCategory` IDs are valid? Need `GET /travelExpense/costCategory` first.
- Which per diem rates apply? Need `GET /travelExpense/rate` or
  `GET /travelExpense/rateCategory` to find standard rates.
- Does the scorer check delivery/approval status or just creation?

**Known from logs:** Spanish prompt received — employee Pablo Rodríguez, 5-day trip,
800 NOK/day per diem, flight 2750 NOK, taxi 700 NOK. Currently scores 0.

---

## Family: projects ✅

### Project create

**Planner extracts:** name, customerLookup, projectManagerLookup (name + email),
startDate, endDate, budget

**API sequence:**
```
1. GET /customer?customerName={name}&organizationNumber={org}&count=2
   → resolve customer ID

2. GET /employee?firstName={first}&lastName={last}&email={email}
              &assignableProjectManagers=true&count=2
   → resolve project manager employee ID

3. POST /project
   body: {
     name,
     startDate: today,
     customer: { id: <resolved> },
     projectManager: { id: <resolved> }
   }
   expected: 201
```

**Confirmed working** — observed in logs (German prompt, Windkraft GmbH).

**Failure modes:**
- Employee not found as project manager — `assignableProjectManagers=true` is required
  filter, not all employees are eligible

---

## Family: departments 🔶

### Department create

**API sequence:**
```
POST /department
  body: { name, departmentNumber (if given), manager: {id} (if specified) }
```

**Open question:** Are departments linked to modules that need enabling first?

---

## Family: corrections 🔶

### Delete entity

**Dependency order matters** — must delete in reverse dependency order:
1. Travel expenses
2. Invoices (only if not posted to ledger)
3. Orders
4. Projects
5. Products
6. Customers (only if no open invoices)
7. Employees
8. Departments

**API pattern:**
```
1. GET /{entity}?{searchParams} → resolve ID
2. DELETE /{entity}/{id}
   expected: 204 or 200
```

**Note:** Entities posted to the ledger cannot be deleted — they must be reversed.

### Reverse voucher 🔶

```
1. GET /ledger/voucher?... → resolve voucher ID
2. PUT /ledger/voucher/{id}/:reverse
   → returns reversed voucher
```

Cannot reverse salary vouchers.

---

## Family: ledger ❓

### Journal entry / voucher posting

**API sequence (inferred):**
```
1. POST /ledger/voucher
   body: {
     date, description,
     postings: [
       { account: {id}, amountGross, ... },  # debit
       { account: {id}, amountGross, ... },  # credit
     ]
   }

2. PUT /ledger/voucher/{id}/:sendToLedger
```

**Open questions:**
- How are account IDs resolved from natural language account names?
- What are the valid account IDs in competition sandbox?
- Does the scorer test this as Tier 2 or Tier 3?

---

## Family: Tier 3 — bank reconciliation ❓

**Known:** Tasks involve CSV bank statements (file attachment).
**Known endpoints:**
- `POST /bank/statement/import` — upload bank statement file
- `POST /bank/reconciliation` — create reconciliation
- `PUT /bank/reconciliation/match/:suggest` — auto-suggest matches
- `POST /bank/reconciliation/match` — create individual match

**Approach (speculative):**
1. Parse CSV attachment → extract transactions
2. Upload via `/bank/statement/import`
3. Create reconciliation for the relevant account
4. Use suggest endpoint to auto-match

**Confidence: very low. Do not implement until Tier 1/2 are solid.**

---

## Family: Tier 3 — year-end / salary ❓

**Known endpoints:** `/yearEnd`, `/salary/...`, `/salary/holidayAllowance/...`
**Task requirements: entirely unknown.**
**Recommendation: skip until explicit task examples are observed.**

---

## Workflow selection logic

```python
WORKFLOW_MAP = {
    ("customers_products", "create", "customer"):   CustomerCreateWorkflow,
    ("customers_products", "create", "product"):    ProductCreateWorkflow,
    ("customers_products", "update", "customer"):   CustomerUpdateWorkflow,
    ("invoicing", "create"):                        InvoiceCreateWorkflow,
    ("invoicing", "payment"):                       InvoicePaymentWorkflow,
    ("invoicing", "credit"):                        InvoiceCreditNoteWorkflow,
    ("employees", "create"):                        EmployeeCreateWorkflow,
    ("employees", "update"):                        EmployeeUpdateWorkflow,
    ("travel_expenses", "create"):                  TravelExpenseCreateWorkflow,
    ("projects", "create"):                         ProjectCreateWorkflow,
    ("departments", "create"):                      DepartmentCreateWorkflow,
    ("corrections", "delete"):                      DeleteWorkflow,
    ("corrections", "reverse"):                     ReverseVoucherWorkflow,
}

def select_workflow(plan: TaskPlan):
    key = (plan.task_family, plan.operation)
    workflow = WORKFLOW_MAP.get(key) or WORKFLOW_MAP.get(key + (plan.primary_entity,))
    if workflow is None:
        raise StubWorkflowError(f"No workflow for {key}")
    return workflow
```
