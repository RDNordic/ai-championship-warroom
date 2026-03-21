# Testing Rig

## Purpose

Enable rapid iteration without spending competition submissions. The sandbox
Tripletex account allows unlimited API calls — this rig uses it to validate
workflows before any real submission.

## Components

```
scripts/
  reset_sandbox.py       # Bring sandbox to clean baseline state
  run_prompt.py          # Execute a prompt against local /solve + sandbox
  replay_logs.py         # Re-run prompts from solve-events.jsonl
  generate_prompts.py    # Synthesise prompt variants from templates
  verify_sandbox.py      # Check postconditions in sandbox after execution
tests/
  fixtures/
    prompts/             # Curated prompt library (JSON)
    files/               # Synthetic PDFs, CSVs for attachment testing
  test_workflows.py      # Unit tests per workflow
  test_planner.py        # Planner extraction tests
  test_integration.py    # Full /solve → sandbox → verify round-trips
```

## Sandbox reset strategy

### Why this is hard

The sandbox is stateful. Entities accumulate across test runs. Customer lookups
start returning unexpected results. Invoice creation fails because a referenced
customer has open invoices that can't be deleted.

### Baseline state

Before building the reset script, manually explore the sandbox and document:
- What chart of accounts exists by default?
- What VAT types are pre-configured?
- What company settings are already set?
- What (if anything) cannot be deleted?

This baseline is what `reset_sandbox.py` restores to — not a completely empty state.

**Action:** Log into `https://kkpqfuj-amager.tripletex.dev`, explore Settings and
Chart of Accounts, and document the baseline in this file under "Known baseline state."

### Delete dependency order

Entities must be deleted in reverse dependency order. Deleting a customer with open
invoices will fail. The correct order:

```
1. Travel expenses (and sub-resources: costs, mileage, per diem, accommodation)
2. Supplier invoices
3. Invoices (only if not posted to ledger — posted ones need voucher reversal)
4. Orders and order lines
5. Projects
6. Products
7. Customers (only if no remaining linked records)
8. Employees (check for linked timesheets, salary entries)
9. Departments
10. Vouchers that are not linked to other entities
```

### Reset script design

```python
# scripts/reset_sandbox.py

import requests

SAFE_ENTITY_TYPES = [
    # (endpoint, search_params, id_field)
    ("/travelExpense", {"count": 100}, "id"),
    ("/invoice", {"count": 100}, "id"),
    ("/order", {"count": 100}, "id"),
    ("/project", {"count": 100}, "id"),
    ("/product", {"count": 100}, "id"),
    ("/customer", {"count": 100}, "id"),
    ("/employee", {"count": 100}, "id"),
    ("/department", {"count": 100}, "id"),
]

def reset(base_url, session_token):
    auth = ("0", session_token)
    deleted = {}
    
    for endpoint, params, id_field in SAFE_ENTITY_TYPES:
        resp = requests.get(f"{base_url}{endpoint}", auth=auth, params=params)
        entities = resp.json().get("values", [])
        
        deleted[endpoint] = []
        for entity in entities:
            entity_id = entity[id_field]
            del_resp = requests.delete(
                f"{base_url}{endpoint}/{entity_id}", auth=auth
            )
            if del_resp.status_code in (200, 204):
                deleted[endpoint].append(entity_id)
            else:
                print(f"Could not delete {endpoint}/{entity_id}: {del_resp.status_code}")
                # Some entities can't be deleted — log and continue
    
    return deleted
```

**Important:** Some entities will be undeletable (posted to ledger, linked records).
The script must handle these gracefully — log and skip, don't crash.

### Pre-seeding baseline data

Some tests require specific entities to exist before running. For example:
- A customer to create an invoice for
- An employee to assign as project manager
- A product to reference in an invoice line

Rather than letting tests create their own prerequisites unpredictably, maintain a
`fixtures/seed_data.json` that the rig creates after reset:

```json
{
  "customers": [
    { "name": "Test Customer AS", "email": "test@example.no", "isCustomer": true }
  ],
  "employees": [
    { "firstName": "Test", "lastName": "Manager", "email": "manager@example.no" }
  ],
  "products": [
    { "name": "Test Product", "priceExcludingVatCurrency": 1000 }
  ]
}
```

## Prompt library

### Structure

```json
{
  "id": "invoice-create-send-fr-001",
  "task_family": "invoicing",
  "operation": "create",
  "tier": 2,
  "language": "fr",
  "prompt": "Créez et envoyez une facture au client {customer_name} de {amount} NOK hors TVA. La facture concerne {description}.",
  "variables": {
    "customer_name": "Test Customer AS",
    "amount": 5000,
    "description": "Services de conseil"
  },
  "expected_api_sequence": [
    { "method": "GET", "path": "/customer" },
    { "method": "POST", "path": "/invoice", "params": { "sendToCustomer": true } }
  ],
  "postconditions": [
    { "check": "entity_created", "entity": "invoice" },
    { "check": "field_equals", "path": "GET /invoice/{id}", "field": "customer.id", "source": "customer_lookup" }
  ],
  "forbidden_calls": [
    { "method": "GET", "path": "/ledger/account" },
    { "method": "PUT", "path": "/ledger/account/*" }
  ]
}
```

### Seeding the library

1. **From logs:** For each confirmed trace in `solve-events.jsonl`, create a
   parametric fixture that generalises the prompt pattern.
2. **From docs examples:** Create fixtures for every task type named in the
   hackathon docs, in all 7 languages.
3. **Synthetic variants:** Use `generate_prompts.py` to produce variants with
   different entity names, amounts, and edge cases.

### Synthetic prompt generation

```python
# scripts/generate_prompts.py
# Use the Anthropic API to generate realistic prompt variants

def generate_variants(task_type: str, languages: list[str], count: int = 8):
    """
    Given a task type, generate `count` prompt variants per language.
    Variants should use realistic but fictional entity names and amounts.
    Output: list of prompt fixtures ready for the library.
    """
    system = """You generate realistic accounting task prompts for testing.
    Each prompt should be different but test the same core workflow.
    Use realistic fictional names (people, companies), amounts, and dates.
    Output only valid JSON matching the fixture schema."""
    
    # ... LLM call with task description and fixture schema
```

## Integration test runner

```python
# scripts/run_prompt.py

def run_prompt(prompt: str, base_url: str, session_token: str,
               solve_url: str = "http://localhost:8000/solve"):
    """
    Send a prompt to the local /solve endpoint using sandbox credentials.
    Returns: { plan, api_calls, postcondition_results }
    """
    response = requests.post(solve_url, json={
        "prompt": prompt,
        "files": [],
        "tripletex_credentials": {
            "base_url": base_url,
            "session_token": session_token
        }
    })
    
    # The trace is emitted to solve-events.jsonl by the agent itself
    # Parse the last trace from the log for inspection
    return parse_latest_trace("logs/solve-events.jsonl")
```

## Postcondition verification

After each test run, verify the outcome in the sandbox:

```python
# scripts/verify_sandbox.py

def verify_postconditions(conditions: list, base_url: str, session_token: str,
                          context: dict) -> list[dict]:
    """
    Check each postcondition against the live sandbox.
    context: IDs and values from the test run (e.g. created entity IDs)
    Returns: list of { check, passed, actual, expected }
    """
    results = []
    for condition in conditions:
        if condition["check"] == "entity_created":
            # Verify the entity exists and has expected fields
            ...
        elif condition["check"] == "field_equals":
            # Fetch entity and compare field value
            ...
        elif condition["check"] == "invoice_sent":
            # Query invoice and check isCharged or send status
            ...
    return results
```

## Attachment test fixtures

### Bank statement CSV (for Tier 3 bank reconciliation)

```csv
Date,Description,Amount,Balance
2026-03-01,Invoice payment ACME AS,15000.00,115000.00
2026-03-02,Supplier payment Vendor X,-8500.00,106500.00
2026-03-05,Salary payment,-45000.00,61500.00
```

Store in `tests/fixtures/files/bank_statement_template.csv`.
`generate_prompts.py` should be able to produce populated variants.

### Invoice PDF (for attachment extraction testing)

A minimal PDF containing:
- Vendor name and org number
- Invoice number and date
- Line items with amounts
- VAT breakdown
- Total amount

Use `reportlab` or a static template PDF for synthetic generation.

## Known baseline state

*To be filled in after manual sandbox exploration.*

```
Default chart of accounts: TBD
Default VAT types: TBD
Pre-existing company settings: TBD
Entities that cannot be deleted: TBD
```

## Running the full test cycle

```bash
# 1. Reset sandbox
python scripts/reset_sandbox.py --base-url $SANDBOX_URL --token $SANDBOX_TOKEN

# 2. Seed baseline fixtures
python scripts/seed_sandbox.py --base-url $SANDBOX_URL --token $SANDBOX_TOKEN

# 3. Start local agent
uvicorn src.tripletex_agent.app:app --port 8000 &

# 4. Run prompt library against local agent + sandbox
python scripts/run_prompt_library.py \
  --base-url $SANDBOX_URL \
  --token $SANDBOX_TOKEN \
  --solve-url http://localhost:8000/solve \
  --fixture-dir tests/fixtures/prompts/

# 5. Inspect results
python scripts/inspect_solve_logs.py recent --limit 20
```
