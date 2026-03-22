"""Unified LLM-driven API executor — the single execution path for all tasks."""

from __future__ import annotations

import ast
import base64
import json
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from .api_validator import ApiCallValidator
from .client import TripletexAPIError, TripletexClient
from .endpoint_catalog import catalog_index_text
from .models import AttachmentFile
from .schema_validator import SchemaValidator
from .swagger_tools import SWAGGER_TOOLS, SwaggerQueryService

_PROMPTS_DIR = Path(__file__).parent / "prompts"

from .workflows.base import WorkflowResult

# Retry config for transient Anthropic API errors (529 overloaded, 503 unavailable)
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0  # seconds

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

_SYSTEM_PROMPT = """\
You are a Tripletex API assistant. Given a task prompt \
(in Norwegian, English, Spanish, Portuguese, German, French, or Nynorsk), \
produce the exact API calls needed.

Today's date is {today}.

AVAILABLE ENDPOINTS (use lookup_endpoint tool for full field details):
{endpoint_index}

TOOLS — use sparingly (max 3-5 lookups):
- lookup_endpoint(method, path): Get full schema (fields, types, required). \
Call this for each POST/PUT endpoint you plan to use.
- get_model_schema(model_name): Get nested model fields (e.g. "Posting", "OrderLine").
- search_endpoints(keyword): Only if you can't find an endpoint in the list above.

RULES:
- Minimize API calls — fewer is better. Every extra call hurts efficiency score.
- Chain IDs: use save_response_fields_as to save IDs, reference as "$var_name".
- CRITICAL: Entity references in POST/PUT bodies use nested object format: \
{{"customer": {{"id": 1}}}}, NOT flat IDs like {{"customerId": 1}}.
- Dates: ISO "YYYY-MM-DD". European: "3. mars 2026" → "2026-03-03".
- Amounts: numeric, not strings. European: "1.500,00" → 1500.00.
- vatType: {{"id": 3}} for 25% MVA.
- GET list responses: "values" array → "values.0.id". \
Single responses: "value" object → "value.id".
- Do NOT send read-only fields.
- CRITICAL: Numbers in parentheses like "Produkt (5664)" are product NUMBERS, \
not IDs. Always GET /product?number=5664 first to get the actual ID. \
Same for employee numbers, department numbers, etc. Never use a number as an ID.
- save_response_fields_as format: {{"my_var": "value.id"}} — key is your variable \
name, value is the dot-path into the response. For lists: "values.0.id".

RECIPES:

## Employee Creation
1. If a specific department is named: GET /department?name=X. \
If that returns empty, GET /department?count=1&sorting=id to get ANY department. \
If no department is named: GET /department?count=1&sorting=id directly. \
A department is ALWAYS required — never skip this step.
2. POST /employee with firstName, lastName, department: {{"id": $dept_id}}, \
userType: "NO_ACCESS", dateOfBirth (if known), email, etc.

## Project Creation
POST /project requires: name, projectManager, customer, startDate, isInternal.

## Invoice Creation
POST /invoice needs: invoiceDate, invoiceDueDate, embedded orders with orderLines. \
?sendToCustomer=true|false. Bank account must be configured first for sending.

## Invoice Payment
CRITICAL: PUT /invoice/{{id}}/:payment uses QUERY PARAMS (paymentDate, paymentTypeId, paidAmount).
GET /invoice REQUIRES invoiceDateFrom + invoiceDateTo.

## Bank Reconciliation
To find invoices, NEVER hardcode invoice numbers. Instead:
1. GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo={today}&count=100 to list ALL invoices
2. Match by customer name and amount from the bank statement
3. For supplier invoices: GET /supplierInvoice?invoiceDateFrom=2020-01-01&invoiceDateTo={today}&count=100
4. PUT /invoice/{{id}}/:payment with paymentDate, paymentTypeId, paidAmount as QUERY PARAMS
5. For supplier invoice payment: POST /supplierInvoice/{{id}}/:addPayment with paymentDate, paymentTypeId, paidAmount, paidAmountCurrency as QUERY PARAMS

## Invoice Credit Note
CRITICAL: PUT /invoice/{{id}}/:createCreditNote uses QUERY PARAMS (date, sendToCustomer).

## Account Lookup
Norwegian accounts are ALWAYS 4 digits. NEVER use 5-digit numbers.
ALWAYS use the 'number' parameter for exact lookups: GET /ledger/account?number=1720
Only use 'query' for text/name search when you don't know the number: GET /ledger/account?query=<keyword>&count=5
Common Norwegian expense accounts:
- 1240: Inventar (furniture/fixtures)
- 1920: Bankinnskudd (bank deposit)
- 2400: Leverandørgjeld (accounts payable)
- 2710: Inngående mva, høy sats (input VAT 25%)
- 2910/2960: Kredittkort/bedriftskort (credit card)
- 6300: Leie lokaler (rent)
- 6540: Inventar (equipment, furniture expense)
- 6800: Kontorrekvisita (office supplies)
- 7100: Bilkostnader (vehicle costs)
- 7140: Reisekostnader (travel costs)

## Ledger Voucher (Journal Entry)
CRITICAL posting rules:
- row: starts at 1, NOT 0
- EVERY posting MUST have ALL FOUR amount fields:
  amount (net excl VAT), amountCurrency (=amount for NOK), \
  amountGross (gross incl VAT), amountGrossCurrency (=amountGross for NOK)
- Do NOT use amountVatCurrency — this field does not exist
- For postings WITH vatType: amount=net, amountGross=gross (net+VAT)
- For postings WITHOUT vatType: amount=amountGross (same value)
- Postings MUST balance: sum of all amount fields = 0
- 1500-accounts need customer ref. 2400-accounts need supplier ref.
- Example: supplier invoice 10000 NOK + 25% VAT = 12500 gross:
  Row 1 (expense): amount=10000, amountGross=12500, vatType:{{"id":3}}
  Row 2 (payable): amount=-12500, amountGross=-12500, supplier:{{"id":$id}}

## Expense Receipt Voucher (Utleggsbilag)
For posting expense receipts (kvittering) paid by employee/company card:
- Use the 2-posting pattern with vatType on the expense row:
  Row 1 (expense): amount=net, amountGross=gross, amountCurrency=net, \
    amountGrossCurrency=gross, vatType:{{"id":3}}, \
    account:{{"id":$expense_account}}, employee:{{"id":$emp_id}}, \
    department:{{"id":$dept_id}}
  Row 2 (payment): amount=-gross, amountGross=-gross, \
    amountCurrency=-gross, amountGrossCurrency=-gross, \
    account:{{"id":$bank_or_card_account}}, employee:{{"id":$emp_id}}
- CRITICAL: 25% VAT math: net = gross / 1.25 (e.g., 6750 gross → net=5400)
- CRITICAL: EVERY posting MUST include employee:{{"id":$emp_id}}
- If no specific employee, GET /employee?count=1 to get any employee
- Sum of amount must = 0: net + (-gross) ≠ 0, so you MUST include vatType \
  on Row 1 so Tripletex auto-handles the VAT difference

## Salary / Payroll (Lønnskjøring)
For payroll processing, create a voucher with MULTIPLE postings:
1. GET /employee (by email/name) to find employee ID
2. GET /ledger/account?number=5000 → Lønn til ansatte (salary expense)
3. GET /ledger/account?number=1920 → Bankinnskudd (bank, for net pay)
4. POST /ledger/voucher with these postings:
  Row 1: account 5000, DEBIT gross salary (amount=gross, amountGross=gross)
  Row 2: account 2780, CREDIT tax withholding ~30% of gross \
    (amount=-tax, amountGross=-tax). Forskuddstrekk.
  Row 3: account 2770, CREDIT employer social security ~14.1% of gross \
    (amount=-aga, amountGross=-aga). Skyldig arbeidsgiveravgift.
  Row 4: account 5400, DEBIT employer social security expense ~14.1% of gross \
    (amount=aga, amountGross=aga). Arbeidsgiveravgift.
  Row 5: account 1920, CREDIT net pay = gross - tax \
    (amount=-net, amountGross=-net)
- EVERY posting MUST include employee:{{"id":$emp_id}}
- All amounts are NOK, no vatType on any posting
- Postings MUST balance: gross - tax - aga + aga - net = 0 \
  (i.e., gross - tax - net = 0, so net = gross - tax)
- If bonus is mentioned, add it to gross salary in posting 1

## Travel Expense (Reiseregning)
CRITICAL: To create a travel report (reiseregning), you MUST include travelDetails. \
Without it, Tripletex creates an "ansattutlegg" (employee expense) which CANNOT \
have per diem or mileage allowances.
1. GET /employee (by email) to find employee ID
2. POST /travelExpense with:
   - employee: {{"id": $emp_id}}
   - title: "description of trip"
   - travelDetails: {{"departureDate": "YYYY-MM-DD", "returnDate": "YYYY-MM-DD", \
     "destination": "city name", "departureFrom": "origin city", \
     "purpose": "trip purpose"}}
3. POST /travelExpense/perDiemCompensation (for daily allowances):
   - travelExpense: {{"id": $travel_id}}
   - overnightAccommodation: "HOTEL"
   - location: "city name"
   - count: number_of_days
   - NOTE: Do NOT include rateCategory — it is auto-assigned
4. POST /travelExpense/cost (for each expense like flight, taxi):
   - travelExpense: {{"id": $travel_id}}
   - date: "YYYY-MM-DD"
   - description: "what was purchased"
   - amount: cost_amount
   - paymentType: {{"id": 0}}
   - category: {{"id": $category_id}} — use GET /travelExpense/costCategory to find

## Timesheet Entry
1. GET /employee (by email or name) to find employee ID.
2. GET /project (by name or customer) to find project ID.
3. GET /activity (by name) to find activity ID.
4. POST /timesheet/entry with: employee ref, project ref, activity ref, \
date, hours. Use lookup_endpoint to check exact fields.

## Supplier Registration
POST /supplier (NOT /customer) with name, organizationNumber, email. \
Use isSupplier: true only on /customer if creating a customer who is also a supplier.

WORKFLOW:
1. Look up schemas for the 2-3 POST/PUT endpoints you need (use lookup_endpoint).
2. Return the JSON array of API steps.

OUTPUT FORMAT:
JSON array of steps: [{{"step_id", "method", "path", "params", "json_body", \
"save_response_fields_as"}}].
Return ONLY the JSON array."""


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    return _SYSTEM_PROMPT.format(today=today, endpoint_index=catalog_index_text())


# Mime types that Claude can process as native content blocks
_PDF_TYPES = {"application/pdf"}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
_TEXT_TYPES = {"text/csv", "text/plain", "text/tab-separated-values"}

# Max tool-use rounds — keep tight to avoid slow exploratory loops
_MAX_TOOL_ROUNDS = 5


def _build_user_content(
    prompt: str, attachments: list[AttachmentFile]
) -> list[dict[str, Any]]:
    """Build the user message content blocks with inline attachments."""
    blocks: list[dict[str, Any]] = []

    for att in attachments:
        mime = att.mime_type.lower()

        if mime in _PDF_TYPES:
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": att.content_base64,
                },
            })
            logger.info("Attached PDF: %s", att.filename)

        elif mime in _IMAGE_TYPES:
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": att.content_base64,
                },
            })
            logger.info("Attached image: %s", att.filename)

        elif mime in _TEXT_TYPES:
            try:
                text_content = base64.b64decode(att.content_base64).decode("utf-8")
            except Exception:
                text_content = base64.b64decode(att.content_base64).decode(
                    "latin-1", errors="replace"
                )
            if len(text_content) > 10_000:
                text_content = text_content[:10_000] + "\n... (truncated)"
            blocks.append({
                "type": "text",
                "text": f"=== File: {att.filename} ===\n{text_content}",
            })
            logger.info("Attached text file: %s (%d chars)", att.filename, len(text_content))

        else:
            logger.warning("Skipping unsupported attachment type: %s (%s)", att.filename, mime)
            blocks.append({
                "type": "text",
                "text": f"[Attachment: {att.filename} ({mime}) — unsupported format]",
            })

    blocks.append({
        "type": "text",
        "text": (
            f"Task prompt:\n{prompt}\n\n"
            "First use the tools to look up the endpoint schemas you need, "
            "then produce the JSON array of API call steps."
        ),
    })

    return blocks


def _resolve_value(obj: Any, path: str) -> Any:
    """Extract a value from a nested dict using a dot-separated path.

    Handles:
    - Dot-separated paths: "values.0.id"
    - Bracket notation: "values[0].id"
    - Single-object responses: tries "value.id" if "values.0.id" fails
    """
    # Normalize bracket notation: "values[0].id" → "values.0.id"
    normalized = re.sub(r"\[(\d+)\]", r".\1", path)
    parts = normalized.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    if current is not None:
        return current

    # Fallback: if path starts with "values.0.", try "value." instead
    # (single-object POST responses use "value", not "values")
    if normalized.startswith("values.0."):
        alt_path = "value." + normalized[len("values.0."):]
        return _resolve_value(obj, alt_path)

    return None


def _substitute_vars(obj: Any, saved_vars: dict[str, Any]) -> Any:
    """Recursively replace "$var_name" references in strings/dicts/lists."""
    if isinstance(obj, str):
        if obj.startswith("$") and obj[1:] in saved_vars:
            return saved_vars[obj[1:]]
        for var_name, var_value in saved_vars.items():
            obj = obj.replace(f"${var_name}", str(var_value))
        return obj
    if isinstance(obj, dict):
        return {k: _substitute_vars(v, saved_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_vars(item, saved_vars) for item in obj]
    return obj


def _call_anthropic_with_retry(client: Any, **kwargs: Any) -> Any:
    """Call the Anthropic API with retry on transient errors (529, 503)."""
    import time as _time

    last_exc = None
    for attempt in range(_LLM_MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:
            exc_str = str(exc)
            if "529" in exc_str or "overloaded" in exc_str.lower() or "503" in exc_str:
                last_exc = exc
                delay = _LLM_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Anthropic API transient error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, _LLM_MAX_RETRIES, delay, exc_str[:100],
                )
                _time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


def _find_unresolved_vars(
    path: Any, params: Any, json_body: Any
) -> list[str]:
    """Find any $variable references that weren't substituted."""
    import re as _re
    unresolved: list[str] = []

    def _scan(obj: Any) -> None:
        if isinstance(obj, str):
            for match in _re.findall(r'\$([a-zA-Z_][a-zA-Z0-9_]*)', obj):
                unresolved.append(f"${match}")
        elif isinstance(obj, dict):
            for v in obj.values():
                _scan(v)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)

    _scan(path)
    _scan(params)
    _scan(json_body)
    return unresolved


_VAR_TOKEN_SYNONYMS = {
    "acc": "account",
    "acct": "account",
    "cust": "customer",
    "dept": "department",
    "emp": "employee",
    "inv": "invoice",
}

_ENTITY_TOKENS = {"account", "customer", "department", "employee", "invoice", "supplier"}


def _tokenize_var_name(name: str) -> list[str]:
    """Normalize a variable name into comparable tokens."""
    cleaned = name[1:] if name.startswith("$") else name
    raw_tokens = re.findall(r"[a-z]+|\d+", cleaned.lower())
    return [_VAR_TOKEN_SYNONYMS.get(token, token) for token in raw_tokens]


def _parse_saved_structure(value: Any) -> Any:
    """Parse a saved list/dict that may have been stringified."""
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value

    try:
        return json.loads(stripped)
    except Exception:
        try:
            return ast.literal_eval(stripped)
        except Exception:
            return value


def _coerce_saved_objects(value: Any) -> list[dict[str, Any]]:
    """Return a list of dict objects from a saved value or response payload."""
    parsed = _parse_saved_structure(value)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        values = parsed.get("values")
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
    return []


def _extract_object_id(obj: dict[str, Any], entity: str) -> Any:
    """Extract an entity id from a saved object using common field layouts."""
    candidate_paths = [
        f"{entity}.id",
        f"{entity}Id",
        f"order.{entity}.id",
        f"order.{entity}Id",
        f"orders.0.{entity}.id",
        f"orders.0.{entity}Id",
        f"value.{entity}.id",
        f"value.{entity}Id",
    ]
    for path in candidate_paths:
        value = _resolve_value(obj, path)
        if value is not None:
            return value
    return None


def _find_saved_object_by_id(saved_vars: dict[str, Any], object_id: Any) -> dict[str, Any] | None:
    """Search saved vars for an object with the given id."""
    for value in saved_vars.values():
        parsed = _parse_saved_structure(value)
        if isinstance(parsed, dict) and parsed.get("id") == object_id:
            return parsed
        for item in _coerce_saved_objects(parsed):
            if item.get("id") == object_id:
                return item
    return None


def _find_prefixed_saved_id(
    saved_vars: dict[str, Any],
    *,
    prefix_tokens: list[str],
    entity: str,
) -> tuple[str, Any] | None:
    """Find a saved entity id whose variable name matches the unresolved prefix."""
    matches: list[tuple[str, Any]] = []
    prefix_set = set(prefix_tokens)
    for name, value in saved_vars.items():
        tokens = _tokenize_var_name(name)
        if entity not in tokens or "id" not in tokens:
            continue
        if prefix_set and not prefix_set.issubset(set(tokens)):
            continue
        matches.append((name, value))
    if len(matches) == 1:
        return matches[0]
    return None


def _select_invoice_candidate(var_name: str, invoices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select an invoice object from a cached list using number or ordinal hints."""
    if not invoices:
        return None

    numbers = [int(token) for token in _tokenize_var_name(var_name) if token.isdigit()]
    for number in numbers:
        for invoice in invoices:
            if invoice.get("invoiceNumber") == number or invoice.get("number") == number:
                return invoice

    for number in numbers:
        ordinal = number % 1000 if number >= 1000 else number
        if 1 <= ordinal <= len(invoices):
            return invoices[ordinal - 1]

    if len(invoices) == 1:
        return invoices[0]
    return None


def _find_alias_source(
    var_name: str,
    saved_vars: dict[str, Any],
) -> tuple[str, Any] | None:
    """Find a safe alias source for an unresolved variable."""
    target_tokens = _tokenize_var_name(var_name)
    target_set = set(target_tokens)
    exact_matches: list[tuple[str, Any]] = []
    subset_matches: list[tuple[str, Any]] = []

    for saved_name, saved_value in saved_vars.items():
        saved_tokens = _tokenize_var_name(saved_name)
        saved_set = set(saved_tokens)
        if saved_tokens == target_tokens:
            exact_matches.append((saved_name, saved_value))
            continue
        if target_set and target_set.issubset(saved_set):
            subset_matches.append((saved_name, saved_value))

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(subset_matches) == 1:
        return subset_matches[0]
    return None


def _derive_unresolved_value(
    var_name: str,
    saved_vars: dict[str, Any],
) -> tuple[Any, str] | None:
    """Derive an unresolved variable from previously saved invoice context."""
    tokens = _tokenize_var_name(var_name)
    if not tokens or "id" not in tokens:
        return None

    if "customer" in tokens:
        prefix_tokens = tokens[:tokens.index("customer")]
        invoice_match = _find_prefixed_saved_id(
            saved_vars, prefix_tokens=prefix_tokens, entity="invoice"
        )
        if invoice_match is None:
            return None
        invoice_name, invoice_id = invoice_match
        invoice_obj = _find_saved_object_by_id(saved_vars, invoice_id)
        if invoice_obj is None:
            return None
        customer_id = _extract_object_id(invoice_obj, "customer")
        if customer_id is not None:
            return customer_id, f"{invoice_name} -> customer.id"
        return None

    if "invoice" not in tokens:
        return None

    prefix_tokens = tokens[:tokens.index("invoice")]
    supplier_invoices = _coerce_saved_objects(saved_vars.get("all_supplier_invoices"))
    if supplier_invoices:
        supplier_match = _find_prefixed_saved_id(
            saved_vars, prefix_tokens=prefix_tokens, entity="supplier"
        )
        if supplier_match is not None:
            supplier_name, supplier_id = supplier_match
            filtered = [
                invoice
                for invoice in supplier_invoices
                if _extract_object_id(invoice, "supplier") == supplier_id
            ]
            selected = _select_invoice_candidate(var_name, filtered)
            if selected is not None and selected.get("id") is not None:
                return selected["id"], f"all_supplier_invoices via {supplier_name}"

    invoices = _coerce_saved_objects(saved_vars.get("all_invoices"))
    selected = _select_invoice_candidate(var_name, invoices)
    if selected is not None and selected.get("id") is not None:
        return selected["id"], "all_invoices"
    return None


def _recover_unresolved_step_vars(
    path: Any,
    params: Any,
    json_body: Any,
    saved_vars: dict[str, Any],
) -> tuple[Any, Any, Any, list[str], list[str]]:
    """Recover unresolved step vars using saved aliases and cached invoice context."""
    recovery_notes: list[str] = []

    unresolved = _find_unresolved_vars(path, params, json_body)
    for unresolved_var in unresolved:
        var_name = unresolved_var[1:]
        if var_name in saved_vars:
            continue
        alias_match = _find_alias_source(var_name, saved_vars)
        if alias_match is None:
            continue
        source_name, source_value = alias_match
        saved_vars[var_name] = source_value
        recovery_notes.append(f"Recovered ${var_name} from alias ${source_name}")

    path = _substitute_vars(path, saved_vars)
    if params:
        params = _substitute_vars(params, saved_vars)
    if json_body:
        json_body = _substitute_vars(json_body, saved_vars)

    unresolved = _find_unresolved_vars(path, params, json_body)
    for unresolved_var in unresolved:
        var_name = unresolved_var[1:]
        if var_name in saved_vars:
            continue
        derived = _derive_unresolved_value(var_name, saved_vars)
        if derived is None:
            continue
        derived_value, source = derived
        saved_vars[var_name] = derived_value
        recovery_notes.append(f"Derived ${var_name} from {source}")

    path = _substitute_vars(path, saved_vars)
    if params:
        params = _substitute_vars(params, saved_vars)
    if json_body:
        json_body = _substitute_vars(json_body, saved_vars)

    return path, params, json_body, recovery_notes, _find_unresolved_vars(path, params, json_body)


def _normalize_save_fields(save_fields: dict[str, str]) -> dict[str, str]:
    """Fix inverted save_response_fields_as mappings.

    Correct format: {"my_var_name": "value.id"}
    Inverted format: {"value.id": "my_var_name"}

    Heuristic: the value should be a response path (contains dots or brackets),
    the key should be a variable name (no dots).
    """
    normalized = {}
    for key, val in save_fields.items():
        if not isinstance(val, str):
            normalized[key] = str(val)
            continue

        key_is_path = "." in key or "[" in key
        val_is_path = "." in val or "[" in val

        if key_is_path and not val_is_path:
            # Inverted: {"value.id": "my_var"} → flip
            normalized[val] = key
        elif val_is_path and not key_is_path:
            # Correct: {"my_var": "value.id"} → keep
            normalized[key] = val
        elif key_is_path and val_is_path:
            # Both look like paths — keep as-is, best guess
            normalized[key] = val
        else:
            # Neither has dots — assume value is a simple field name
            normalized[key] = val
    return normalized


def _fix_invoice_orders(json_body: dict[str, Any], fixes: list[str]) -> None:
    """Inject required orderDate/deliveryDate into invoice order objects."""
    from datetime import date as _date
    today = _date.today().isoformat()
    orders = json_body.get("orders")
    if not isinstance(orders, list):
        return
    for order in orders:
        if not isinstance(order, dict):
            continue
        if "orderDate" not in order:
            order["orderDate"] = today
            fixes.append("Injected missing 'orderDate' with today's date")
        if "deliveryDate" not in order:
            order["deliveryDate"] = today
            fixes.append("Injected missing 'deliveryDate' with today's date")


def _voucher_balance_errors(json_body: dict[str, Any]) -> list[str]:
    """Return voucher balance errors for amount and amountGross sums."""
    postings = json_body.get("postings")
    if not isinstance(postings, list) or len(postings) < 2:
        return []

    sum_amount = 0.0
    sum_amount_gross = 0.0
    has_numeric_amount = False
    has_numeric_amount_gross = False

    for posting in postings:
        if not isinstance(posting, dict):
            continue
        amount = posting.get("amount")
        amount_gross = posting.get("amountGross")
        if isinstance(amount, (int, float)):
            sum_amount += float(amount)
            has_numeric_amount = True
        if isinstance(amount_gross, (int, float)):
            sum_amount_gross += float(amount_gross)
            has_numeric_amount_gross = True

    errors: list[str] = []
    tolerance = 0.01
    if has_numeric_amount and abs(sum_amount) > tolerance:
        errors.append(f"Postings amount sum={sum_amount:.2f} does not balance to 0")
    if has_numeric_amount_gross and abs(sum_amount_gross) > tolerance:
        errors.append(f"Postings amountGross sum={sum_amount_gross:.2f} does not balance to 0")
    return errors


def _voucher_balances_in_tripletex(json_body: dict[str, Any]) -> bool:
    """Check voucher balance using Tripletex VAT semantics."""
    postings = json_body.get("postings")
    if not isinstance(postings, list) or len(postings) < 2:
        return False

    effective_sum = 0.0
    has_numeric_amounts = False

    for posting in postings:
        if not isinstance(posting, dict):
            continue

        amount = posting.get("amount")
        if not isinstance(amount, (int, float)):
            return False

        if "vatType" in posting:
            amount_gross = posting.get("amountGross")
            if not isinstance(amount_gross, (int, float)):
                return False
            effective_sum += float(amount_gross)
        else:
            effective_sum += float(amount)
        has_numeric_amounts = True

    return has_numeric_amounts and abs(effective_sum) <= 0.01


def _fix_voucher_vat_amounts(json_body: dict[str, Any], step_fixes: list[str]) -> None:
    """Ensure voucher postings have correct net amounts based on VAT type.

    For postings WITH vatType: amount = amountGross / (1 + rate)
    For postings WITHOUT vatType: amount = amountGross (no VAT component)
    """
    postings = json_body.get("postings")
    if not isinstance(postings, list):
        return

    vat_rates = {
        1: 1.25, 3: 1.25,   # 25% (input/output)
        5: 1.15, 12: 1.15,  # 15% (food)
        31: 1.12,            # 12%
        6: 1.0, 0: 1.0,     # 0% (exempt)
    }

    any_fixed = False
    for posting in postings:
        if not isinstance(posting, dict):
            continue

        amount_gross = posting.get("amountGross")
        if not isinstance(amount_gross, (int, float)):
            continue
        gross = float(amount_gross)

        if "vatType" in posting:
            # Extract VAT type ID
            vat_type = posting.get("vatType")
            vat_type_id = None
            if isinstance(vat_type, dict):
                vid = vat_type.get("id")
                vat_type_id = int(vid) if isinstance(vid, (int, str)) and str(vid).isdigit() else None
            elif isinstance(vat_type, (int, str)) and str(vat_type).isdigit():
                vat_type_id = int(vat_type)

            divisor = vat_rates.get(vat_type_id or 3, 1.25)
            correct_amount = round(gross / divisor, 2)
        else:
            # No VAT: amount = amountGross
            correct_amount = gross

        old_amount = posting.get("amount")
        if isinstance(old_amount, (int, float)) and round(float(old_amount), 2) == correct_amount:
            continue  # Already correct

        posting["amount"] = correct_amount
        posting["amountCurrency"] = correct_amount
        if isinstance(old_amount, (int, float)):
            step_fixes.append(f"Auto-corrected VAT: amount {float(old_amount):.2f} -> {correct_amount:.2f}")
            any_fixed = True

    if any_fixed:
        logger.info("VAT auto-correction applied to voucher postings")


def _normalize_text(text: str) -> str:
    """Lowercase and strip accents for keyword matching."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def _find_saved_account_number(saved_vars: dict[str, Any], account_id: Any) -> int | None:
    """Recover an account number from saved account-id variables."""
    for name, value in saved_vars.items():
        if value != account_id:
            continue
        match = re.fullmatch(r"account_(\d+)_id", name)
        if match:
            return int(match.group(1))
    return None


def _prompt_mentions_account_number(prompt: str, account_number: int | None) -> bool:
    """Return True when the user prompt explicitly specifies an account number."""
    if account_number is None:
        return False
    normalized = _normalize_text(prompt)
    patterns = (
        rf"\b(account|konto|compte|cuenta|conta)\s+{account_number}\b",
        rf"\b{account_number}\s*(account|konto|compte|cuenta|conta)\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _infer_supplier_invoice_account_query(*texts: str) -> str | None:
    """Infer a semantic account-search query from supplier-invoice line text."""
    combined = _normalize_text(" ".join(text for text in texts if text))
    if not combined:
        return None

    keyword_groups = (
        (("programvare", "software", "lisens", "license", "saas"), "programvare"),
        (("it-konsulent", "it konsulent", "consult", "consulting", "konsulent"), "konsulent"),
        (("nettverk", "network"), "data"),
        (("kontor", "office", "bureau"), "kontor"),
    )
    for keywords, query in keyword_groups:
        if any(keyword in combined for keyword in keywords):
            return query
    return None


def _select_best_account_candidate(
    accounts: list[dict[str, Any]],
    *,
    query: str,
    description_text: str,
) -> dict[str, Any] | None:
    """Pick the most relevant account from a query search result."""
    query_tokens = set(re.findall(r"[a-z]+", _normalize_text(query)))
    description_tokens = set(re.findall(r"[a-z]+", _normalize_text(description_text)))
    blocked_numbers = {6300, 6340}

    best: tuple[int, dict[str, Any]] | None = None
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_id = account.get("id")
        account_number = account.get("number")
        if account_id is None or not isinstance(account_number, int):
            continue
        if account.get("type") != "OPERATING_EXPENSES":
            continue
        if account.get("isInactive"):
            continue

        text = " ".join(
            str(account.get(key, ""))
            for key in ("name", "displayName", "description")
        )
        account_tokens = set(re.findall(r"[a-z]+", _normalize_text(text)))
        score = 0
        score += 6 * len(query_tokens & account_tokens)
        score += 2 * len(description_tokens & account_tokens)
        if account_number in blocked_numbers:
            score -= 10
        if best is None or score > best[0]:
            best = (score, account)

    if best is not None and best[0] > 0:
        return best[1]

    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_number = account.get("number")
        if (
            isinstance(account.get("id"), int)
            and isinstance(account_number, int)
            and account.get("type") == "OPERATING_EXPENSES"
            and not account.get("isInactive")
            and account_number not in blocked_numbers
        ):
            return account
    return None


async def _maybe_fix_supplier_invoice_account(
    *,
    prompt: str,
    json_body: dict[str, Any],
    saved_vars: dict[str, Any],
    tripletex_client: TripletexClient,
    step_fixes: list[str],
) -> None:
    """Repair obviously wrong supplier-invoice expense accounts before posting."""
    if "vendorInvoiceNumber" not in json_body:
        return

    postings = json_body.get("postings")
    if not isinstance(postings, list):
        return

    expense_posting = None
    for posting in postings:
        if not isinstance(posting, dict):
            continue
        account = posting.get("account")
        supplier = posting.get("supplier")
        amount_gross = posting.get("amountGross")
        if (
            isinstance(account, dict)
            and supplier
            and posting.get("vatType")
            and isinstance(amount_gross, (int, float))
            and float(amount_gross) > 0
        ):
            expense_posting = posting
            break

    if expense_posting is None:
        return

    account = expense_posting.get("account")
    if not isinstance(account, dict):
        return
    account_id = account.get("id")
    if account_id is None:
        return

    account_number = _find_saved_account_number(saved_vars, account_id)
    if account_number not in {6300, 6340}:
        return
    if _prompt_mentions_account_number(prompt, account_number):
        return

    description_text = " ".join(
        str(value)
        for value in (
            expense_posting.get("description"),
            json_body.get("description"),
        )
        if value
    )
    query = _infer_supplier_invoice_account_query(description_text)
    if query is None:
        return

    payload = await tripletex_client.request(
        "GET",
        "/ledger/account",
        params={"query": query, "count": 10},
        expected_status=(200,),
    )
    candidates = payload.get("values", []) if isinstance(payload, dict) else []
    replacement = _select_best_account_candidate(
        candidates,
        query=query,
        description_text=description_text,
    )
    if replacement is None:
        return

    replacement_id = replacement.get("id")
    replacement_number = replacement.get("number")
    if replacement_id is None or replacement_id == account_id:
        return

    expense_posting["account"] = {"id": replacement_id}
    if isinstance(replacement_number, int):
        saved_vars[f"account_{replacement_number}_id"] = replacement_id
        step_fixes.append(
            f"Re-routed supplier invoice expense account {account_number} -> {replacement_number} based on '{query}'"
        )
    else:
        step_fixes.append(
            f"Re-routed supplier invoice expense account {account_number} using query '{query}'"
        )


def _parse_steps(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of step dicts."""
    text = raw_text.strip()

    def _validated_step_list(parsed: Any) -> list[dict[str, Any]]:
        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

        non_dict_indexes = [
            str(index) for index, step in enumerate(parsed)
            if not isinstance(step, dict)
        ]
        if non_dict_indexes:
            raise ValueError(
                "Expected JSON array of step objects, found non-object items at indexes: "
                + ", ".join(non_dict_indexes)
            )
        return parsed

    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
        return _validated_step_list(parsed)
    except json.JSONDecodeError:
        pass
    except ValueError:
        raise

    # Find the first complete JSON array using bracket matching
    start = text.find("[")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i + 1])
                        return _validated_step_list(parsed)
                    except json.JSONDecodeError:
                        break

    # Last resort: greedy regex
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return _validated_step_list(parsed)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse LLM response as JSON array: {text[:200]}")


def _step_id_as_int(step_id: Any) -> int | None:
    """Best-effort numeric step_id parsing without raising."""
    try:
        return int(str(step_id).strip())
    except (TypeError, ValueError):
        return None


class LLMApiExecutor:
    """Unified executor: one LLM call with tool use to plan API steps."""

    def __init__(
        self, *, api_key: str, tool_model: str, executor_model: str
    ) -> None:
        if anthropic is None:
            raise RuntimeError("anthropic package is required for LLMApiExecutor")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._tool_model = tool_model          # Haiku: fast tool calling
        self._executor_model = executor_model  # Sonnet: precise step generation
        self._validator = ApiCallValidator()
        self._schema_validator = SchemaValidator()
        self._swagger_query = SwaggerQueryService()

    async def execute(
        self,
        *,
        prompt: str,
        attachments: list[AttachmentFile],
        tripletex_client: TripletexClient,
    ) -> WorkflowResult:
        """Plan API calls via LLM with tool use, validate, then execute them."""

        # Pre-flight: ensure sandbox has a bank account configured
        # (required for invoice creation, fails with 'bankkontonummer' error otherwise)
        await self._ensure_bank_account(tripletex_client)

        system_prompt = _build_system_prompt()
        content_blocks = _build_user_content(prompt, attachments)

        logger.info(
            "Calling LLM for API plan: tool_model=%s executor_model=%s prompt_len=%d attachments=%d",
            self._tool_model, self._executor_model, len(prompt), len(attachments),
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": content_blocks}]

        # Tool-use loop: let the LLM call swagger tools before producing steps
        steps = await self._call_llm_with_tools(messages, system_prompt)
        if steps is None:
            return WorkflowResult(
                name="unified_executor",
                completed=False,
                details={"error": "Failed to parse LLM response"},
            )

        logger.info("Parsed %d API call steps from LLM", len(steps))

        # Validate route-level
        validation = self._validator.validate_plan(steps)
        validation_messages = validation.errors + [
            warning
            for step_result in validation.step_results
            for warning in step_result.warnings
        ]
        if not validation.valid:
            logger.warning(
                "LLM plan validation failed: %s",
                validation_messages,
            )
            return WorkflowResult(
                name="unified_executor",
                completed=False,
                details={
                    "error": "Invalid API plan",
                    "validation_messages": validation_messages,
                },
            )

        # Execute steps
        saved_vars: dict[str, Any] = {}
        executed_operations: list[str] = []
        resource_ids: list[int] = []
        all_details: dict[str, Any] = {
            "steps_planned": len(steps),
            "steps_executed": 0,
            "tool_model": self._tool_model,
            "executor_model": self._executor_model,
            "validation_messages": validation_messages,
        }

        execution_failure = await self._execute_steps(
            steps=steps,
            prompt=prompt,
            tripletex_client=tripletex_client,
            saved_vars=saved_vars,
            executed_operations=executed_operations,
            resource_ids=resource_ids,
            all_details=all_details,
        )

        # Self-correction on failure (max 1 retry)
        if execution_failure is not None and not all_details.get("retried"):
            failed_step_id = execution_failure["step_id"]
            failed_step_id_int = _step_id_as_int(failed_step_id)
            logger.info(
                "Step %s failed — requesting LLM self-correction",
                failed_step_id,
            )
            all_details["retried"] = True

            correction_steps = await self._request_correction(
                messages=messages,
                system_prompt=system_prompt,
                completed_steps=executed_operations,
                saved_vars=saved_vars,
                failed_step_id=failed_step_id,
                failed_method=execution_failure["method"],
                failed_path=execution_failure["path"],
                error_detail=execution_failure["error"],
                auto_fixes=execution_failure["auto_fixes"],
                fields_removed=execution_failure["fields_removed"],
                remaining_steps=[
                    s for s in steps
                    if (
                        s.get("step_id") == failed_step_id
                        or (
                            failed_step_id_int is not None
                            and _step_id_as_int(s.get("step_id")) is not None
                            and _step_id_as_int(s.get("step_id")) > failed_step_id_int
                        )
                    )
                ],
            )

            if correction_steps:
                logger.info(
                    "LLM produced %d corrected steps, retrying",
                    len(correction_steps),
                )
                all_details["correction_steps"] = len(correction_steps)
                execution_failure = await self._execute_steps(
                    steps=correction_steps,
                    prompt=prompt,
                    tripletex_client=tripletex_client,
                    saved_vars=saved_vars,
                    executed_operations=executed_operations,
                    resource_ids=resource_ids,
                    all_details=all_details,
                )

        all_details["saved_vars"] = {k: str(v) for k, v in saved_vars.items()}
        if execution_failure is not None:
            all_details["error"] = execution_failure["error"]
            all_details["failed_step_id"] = execution_failure["step_id"]

        completed = execution_failure is None
        return WorkflowResult(
            name="unified_executor",
            completed=completed,
            intended_operations=executed_operations,
            resource_ids=resource_ids,
            details=all_details,
        )

    async def _call_llm_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
    ) -> list[dict[str, Any]] | None:
        """Two-phase LLM call: Haiku for tool lookups, Sonnet for step generation."""
        tool_calls_made = 0
        tool_context_parts: list[str] = []

        # Phase 1: Haiku does the tool calling (fast, cheap)
        tool_messages = list(messages)
        for round_num in range(_MAX_TOOL_ROUNDS):
            response = _call_anthropic_with_retry(self._client,
                model=self._tool_model,
                max_tokens=4096,
                system=system_prompt,
                messages=tool_messages,
                tools=SWAGGER_TOOLS,
            )

            tool_use_blocks = []
            text_blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_use_blocks.append(block)
                elif block.type == "text":
                    text_blocks.append(block.text)

            if not tool_use_blocks:
                # Haiku is done with tools — move to phase 2
                break

            tool_messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                tool_result = self._handle_tool_call(
                    tool_block.name, tool_block.input
                )
                tool_calls_made += 1
                logger.info(
                    "Tool call %d [%s]: %s(%s) → %d chars",
                    tool_calls_made,
                    self._tool_model,
                    tool_block.name,
                    json.dumps(tool_block.input),
                    len(json.dumps(tool_result)),
                )
                # Collect tool results as context for Sonnet
                tool_context_parts.append(
                    f"## {tool_block.name}({json.dumps(tool_block.input)})\n"
                    f"{json.dumps(tool_result, ensure_ascii=False, indent=2)}"
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

            tool_messages.append({"role": "user", "content": tool_results})

        logger.info(
            "Phase 1 complete [%s]: %d tool calls. Starting phase 2 [%s]",
            self._tool_model, tool_calls_made, self._executor_model,
        )

        # Phase 2: Sonnet generates the final steps (precise, with full schema context)
        schema_context = "\n\n".join(tool_context_parts)
        generation_content = list(messages[0]["content"])  # Copy original user content
        if schema_context:
            generation_content.append({
                "type": "text",
                "text": (
                    f"\n\nAPI SCHEMA CONTEXT (from endpoint lookups):\n\n"
                    f"{schema_context}\n\n"
                    "Now produce the JSON array of API call steps. "
                    "Use ONLY the field names shown in the schemas above. "
                    "Return ONLY the JSON array."
                ),
            })

        generation_messages: list[dict[str, Any]] = [
            {"role": "user", "content": generation_content}
        ]

        response = _call_anthropic_with_retry(self._client,
            model=self._executor_model,
            max_tokens=4096,
            system=system_prompt,
            messages=generation_messages,
        )

        raw_text = response.content[0].text
        logger.info(
            "LLM response [%s] (after %d tool calls): %d chars",
            self._executor_model, tool_calls_made, len(raw_text),
        )
        try:
            return _parse_steps(raw_text)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse LLM response: %s", exc)
            return None

    def _handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """Dispatch a tool call to the swagger query service."""
        if tool_name == "lookup_endpoint":
            return self._swagger_query.lookup_endpoint(
                method=tool_input["method"],
                path=tool_input["path"],
            )
        if tool_name == "search_endpoints":
            return self._swagger_query.search_endpoints(
                keyword=tool_input["keyword"],
            )
        if tool_name == "get_model_schema":
            return self._swagger_query.get_model_schema(
                model_name=tool_input["model_name"],
            )
        return {"error": f"Unknown tool: {tool_name}"}

    async def _execute_steps(
        self,
        *,
        steps: list[dict[str, Any]],
        prompt: str,
        tripletex_client: TripletexClient,
        saved_vars: dict[str, Any],
        executed_operations: list[str],
        resource_ids: list[int],
        all_details: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute steps sequentially.

        Returns None on success, or a dict with failure context.
        """
        for step in steps:
            if not isinstance(step, dict):
                logger.warning("Skipping non-dict step: %s", type(step).__name__)
                continue
            step_id = step.get("step_id", "?")
            method = step.get("method", "GET")
            path = step.get("path", "")
            params = step.get("params")
            json_body = step.get("json_body")
            save_fields_raw = step.get("save_response_fields_as", {})
            # Haiku sometimes outputs save_response_fields_as as a list or string
            # instead of a dict. Normalize it.
            if isinstance(save_fields_raw, dict):
                save_fields = save_fields_raw
            elif isinstance(save_fields_raw, list):
                # Try to convert list of {key: path} dicts
                save_fields = {}
                for item in save_fields_raw:
                    if isinstance(item, dict):
                        save_fields.update(item)
            elif isinstance(save_fields_raw, str):
                save_fields = {}
            else:
                save_fields = {}

            path = _substitute_vars(path, saved_vars)
            if params:
                params = _substitute_vars(params, saved_vars)
            if json_body:
                json_body = _substitute_vars(json_body, saved_vars)
            path, params, json_body, recovery_notes, unresolved = _recover_unresolved_step_vars(
                path, params, json_body, saved_vars
            )

            # Strip empty dicts — LLM sometimes generates {} instead of null
            if isinstance(params, dict) and not params:
                params = None
            if isinstance(json_body, dict) and not json_body:
                json_body = None
            # Never send json_body on GET/DELETE — proxies reject it
            if method in ("GET", "DELETE"):
                json_body = None
            # Strip 'fields' param from GETs — LLM often hallucinates field
            # names (e.g. 'payments' on InvoiceDTO), causing silent failures
            # where the needed field is absent from the response.
            if method == "GET" and isinstance(params, dict) and "fields" in params:
                logger.info("Stripping 'fields' param from GET %s to avoid hallucinated field names", path)
                del params["fields"]

            # Fix account lookups: LLM uses 'query' with a number, but the
            # Tripletex 'query' param does a text search and returns wrong
            # accounts.  Convert to 'number' param for exact match.
            if (
                method == "GET"
                and "/ledger/account" in path
                and isinstance(params, dict)
                and "query" in params
                and "number" not in params
            ):
                q = str(params["query"]).strip()
                if q.isdigit() and 3 <= len(q) <= 4:
                    logger.info(
                        "Converting account lookup query=%s to number=%s for exact match",
                        q, q,
                    )
                    params["number"] = q
                    del params["query"]

            # Validate and clean json_body against swagger schema
            step_fixes: list[str] = []
            step_removed: list[str] = []
            if recovery_notes:
                step_fixes.extend(recovery_notes)
                logger.info("Recovered step %s vars: %s", step_id, recovery_notes)

            # Check for unresolved $variable references — don't send if found
            if unresolved:
                error_msg = f"Unresolved variables: {unresolved}. Saved vars: {list(saved_vars.keys())}"
                logger.error("Step %s has unresolved vars — skipping: %s", step_id, error_msg)
                all_details[f"step_{step_id}_error"] = error_msg
                executed_operations.append(f"{method} {path} [SKIPPED: unresolved vars]")
                return {
                    "step_id": str(step_id),
                    "method": method,
                    "path": path,
                    "error": error_msg,
                    "auto_fixes": step_fixes,
                    "fields_removed": step_removed,
                }
            if json_body and isinstance(json_body, dict) and method in ("POST", "PUT"):
                # Auto-fix invoice orders: inject required date fields
                if method == "POST" and "/invoice" in path:
                    _fix_invoice_orders(json_body, step_fixes)
                # Auto-fix voucher: inject date if missing + propagate employee refs
                if method == "POST" and "/voucher" in path:
                    await _maybe_fix_supplier_invoice_account(
                        prompt=prompt,
                        json_body=json_body,
                        saved_vars=saved_vars,
                        tripletex_client=tripletex_client,
                        step_fixes=step_fixes,
                    )
                    _fix_voucher_vat_amounts(json_body, step_fixes)
                    from datetime import date as _date
                    if "date" not in json_body:
                        json_body["date"] = _date.today().isoformat()
                        step_fixes.append("Injected missing 'date' field with today's date")
                    # Auto-inject employee ref across all postings if any have it
                    postings = json_body.get("postings")
                    if isinstance(postings, list):
                        emp_refs = [p.get("employee") for p in postings if isinstance(p, dict) and p.get("employee")]
                        if emp_refs:
                            for p in postings:
                                if isinstance(p, dict) and not p.get("employee"):
                                    p["employee"] = emp_refs[0]
                                    step_fixes.append("Propagated employee ref to posting")
                        elif not emp_refs and saved_vars:
                            # No employee on any posting — try to find one from saved vars
                            for vname, vid in saved_vars.items():
                                if "employee" in vname or "emp" in vname:
                                    for p in postings:
                                        if isinstance(p, dict) and not p.get("employee"):
                                            p["employee"] = {"id": int(vid) if str(vid).isdigit() else vid}
                                            step_fixes.append(f"Injected employee from ${vname}")
                                    break
                schema_result = self._schema_validator.validate_and_clean(
                    method, path, json_body
                )
                json_body = schema_result.cleaned_body
                step_fixes = schema_result.fixes_applied + step_fixes
                step_removed = schema_result.fields_removed
                if "/voucher" in path:
                    balance_errors = [e for e in schema_result.errors if "does not balance" in e]
                    if balance_errors and _voucher_balances_in_tripletex(json_body):
                        schema_result.errors = [
                            e for e in schema_result.errors if "does not balance" not in e
                        ]
                        schema_result.valid = len(schema_result.errors) == 0
                if step_fixes:
                    all_details[f"step_{step_id}_fixes"] = step_fixes
                if not schema_result.valid:
                    # Block vouchers with balance errors — they will always fail
                    balance_errors = [e for e in schema_result.errors if "does not balance" in e]
                    if balance_errors and "/voucher" in path:
                        error_msg = f"Voucher blocked: {balance_errors}"
                        logger.error("Step %s blocked due to balance error: %s", step_id, error_msg)
                        all_details[f"step_{step_id}_error"] = error_msg
                        executed_operations.append(f"{method} {path} [BLOCKED: balance error]")
                        return {
                            "step_id": str(step_id), "method": method, "path": path,
                            "error": error_msg, "auto_fixes": step_fixes,
                            "fields_removed": step_removed,
                        }
                    all_details[f"step_{step_id}_validation_warnings"] = schema_result.errors

            logger.info(
                ">>> Step %s REQUEST: %s %s params=%s body=%s",
                step_id,
                method,
                path,
                json.dumps(params, ensure_ascii=False, default=str) if params else None,
                json.dumps(json_body, ensure_ascii=False, default=str) if json_body else None,
            )
            if step_fixes:
                logger.info("    Auto-fixes applied: %s", step_fixes)

            try:
                response_payload = await tripletex_client.request(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    expected_status=(200, 201, 202, 204),
                )
            except TripletexAPIError as exc:
                error_msg = (
                    f"HTTP {exc.status_code}: {exc.detail}"
                    if exc.status_code
                    else str(exc)
                )
                logger.error(
                    "Step %s failed (API error): status=%s detail=%s",
                    step_id,
                    exc.status_code,
                    exc.detail,
                )
                all_details[f"step_{step_id}_error"] = error_msg
                executed_operations.append(f"{method} {path} [FAILED: {exc.status_code}]")
                return {
                    "step_id": str(step_id),
                    "method": method,
                    "path": path,
                    "error": error_msg,
                    "auto_fixes": step_fixes,
                    "fields_removed": step_removed,
                }
            except Exception as exc:
                error_msg = str(exc) or f"{type(exc).__name__}: {repr(exc)}"
                logger.error("Step %s failed (%s): %s", step_id, type(exc).__name__, repr(exc))
                all_details[f"step_{step_id}_error"] = error_msg
                executed_operations.append(f"{method} {path} [FAILED]")
                return {
                    "step_id": str(step_id),
                    "method": method,
                    "path": path,
                    "error": error_msg,
                    "auto_fixes": step_fixes,
                    "fields_removed": step_removed,
                }

            # Log the response (truncate large responses)
            response_str = json.dumps(response_payload, ensure_ascii=False, default=str)
            if len(response_str) > 1000:
                response_str = response_str[:1000] + "... (truncated)"
            logger.info("<<< Step %s RESPONSE: %s", step_id, response_str)

            executed_operations.append(f"{method} {path}")
            all_details["steps_executed"] = all_details.get("steps_executed", 0) + 1

            if save_fields and isinstance(save_fields, dict) and response_payload:
                # Auto-detect inverted save_response_fields_as
                # Correct: {"my_var": "value.id"}
                # Inverted: {"value.id": "my_var"}
                save_fields = _normalize_save_fields(save_fields)
                for var_name, field_path in save_fields.items():
                    value = _resolve_value(response_payload, field_path)
                    # Fallback: if a deeply nested path like
                    # "values.0.orders.0.customer.id" fails, try
                    # collapsing to "values.0.customer.id" — the LLM
                    # often nests through ref arrays that don't contain
                    # the desired field.
                    if value is None and field_path.count(".") >= 4:
                        parts = field_path.split(".")
                        # Try removing intermediate array traversals
                        # e.g. "values.0.orders.0.customer.id" → "values.0.customer.id"
                        for i in range(2, len(parts) - 2):
                            shorter = ".".join(parts[:2] + parts[i + 1:])
                            value = _resolve_value(response_payload, shorter)
                            if value is not None:
                                logger.info(
                                    "Fallback path %s → %s resolved %s",
                                    field_path, shorter, value,
                                )
                                break
                    if value is not None:
                        saved_vars[var_name] = value
                        logger.info("Saved %s = %s", var_name, value)
                        if isinstance(value, int) and field_path.endswith(".id"):
                            resource_ids.append(value)
                    else:
                        # Auto-retry on empty GET responses
                        if (
                            method == "GET"
                            and isinstance(response_payload, dict)
                            and response_payload.get("fullResultSize", -1) == 0
                            and isinstance(params, dict)
                        ):
                            retry_payload = None
                            retry_desc = ""
                            try:
                                if "/ledger/account" in path and "number" in params:
                                    # Account lookup: retry with query search
                                    retry_desc = f"account number {params['number']}"
                                    retry_payload = await tripletex_client.request(
                                        "GET", "/ledger/account",
                                        params={"query": str(params["number"]), "count": 5},
                                        expected_status=(200,),
                                    )
                                elif "/department" in path and "name" in params:
                                    # Department lookup: retry getting any department
                                    retry_desc = f"department '{params['name']}'"
                                    retry_payload = await tripletex_client.request(
                                        "GET", "/department",
                                        params={"count": 1, "sorting": "id"},
                                        expected_status=(200,),
                                    )
                                elif "/employee" in path:
                                    # Employee lookup: retry getting any employee
                                    retry_desc = "employee"
                                    retry_payload = await tripletex_client.request(
                                        "GET", "/employee",
                                        params={"count": 1},
                                        expected_status=(200,),
                                    )

                                if retry_payload is not None:
                                    logger.info("Empty result for %s, retrying with broader search", retry_desc)
                                    retry_value = _resolve_value(retry_payload, field_path)
                                    if retry_value is not None:
                                        saved_vars[var_name] = retry_value
                                        logger.info("Saved %s = %s (via fallback retry)", var_name, retry_value)
                                        if isinstance(retry_value, int) and field_path.endswith(".id"):
                                            resource_ids.append(retry_value)
                                        continue
                            except Exception as exc:
                                logger.warning("Fallback retry failed for %s: %s", retry_desc, exc)

                        logger.warning(
                            "Could not extract %s from response via path '%s'",
                            var_name,
                            field_path,
                        )

        return None

    @staticmethod
    async def _ensure_bank_account(tripletex_client: TripletexClient) -> None:
        """Ensure the sandbox has a bank account number configured.

        Without this, invoice creation fails with:
        'Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer.'
        """
        try:
            payload = await tripletex_client.request(
                "GET", "/ledger/account",
                params={"isBankAccount": True, "count": 10, "sorting": "number"},
                expected_status=(200,),
            )
            accounts = payload.get("values", []) if isinstance(payload, dict) else []
            invoice_accounts = [
                a for a in accounts
                if isinstance(a, dict) and a.get("isInvoiceAccount")
            ]
            if not invoice_accounts:
                return  # No invoice account found — can't fix, move on

            account = invoice_accounts[0]
            existing = account.get("bankAccountNumber")
            if isinstance(existing, str) and existing.strip():
                return  # Already configured

            account_id = account.get("id")
            if account_id is None:
                return

            await tripletex_client.request(
                "PUT", f"/ledger/account/{account_id}",
                json_body={"bankAccountNumber": "12345678903"},
                expected_status=(200,),
            )
            logger.info("Pre-flight: configured bank account on ledger account %s", account_id)
        except Exception as exc:
            logger.warning("Pre-flight bank account setup failed (non-fatal): %s", exc)

    async def _request_correction(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        completed_steps: list[str],
        saved_vars: dict[str, Any],
        failed_step_id: str,
        failed_method: str,
        failed_path: str,
        error_detail: str,
        auto_fixes: list[str],
        fields_removed: list[str],
        remaining_steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Ask the LLM to fix the failed step with schema context."""
        retry_prompt_path = _PROMPTS_DIR / "retry_correction.md"
        try:
            template = retry_prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Skipping LLM correction because retry prompt could not be loaded from %s: %s",
                retry_prompt_path,
                exc,
            )
            return None

        endpoint_schema = self._schema_validator.describe_endpoint_fields(
            failed_method, failed_path
        )

        correction_prompt = template.format(
            failed_step_id=failed_step_id,
            error_detail=error_detail,
            completed_steps=json.dumps(completed_steps, indent=2),
            saved_vars=json.dumps(
                {k: str(v) for k, v in saved_vars.items()}, indent=2
            ),
            auto_fixes=("\n".join(f"- {f}" for f in auto_fixes) if auto_fixes
                        else "- None"),
            fields_removed=("\n".join(f"- {f}" for f in fields_removed) if fields_removed
                           else "- None"),
            failed_method=failed_method,
            failed_path=failed_path,
            endpoint_schema=endpoint_schema,
            remaining_steps=json.dumps(remaining_steps, indent=2),
        )

        # Include original user content (with attachments like PDFs)
        # so the LLM can still access extracted data during correction.
        original_content = messages[0]["content"]
        if isinstance(original_content, list):
            correction_content = list(original_content) + [
                {"type": "text", "text": correction_prompt}
            ]
        else:
            correction_content = f"{original_content}\n\n{correction_prompt}"

        correction_messages: list[dict[str, Any]] = [
            {"role": "user", "content": correction_content},
        ]

        logger.info("Requesting LLM correction for step %s", failed_step_id)

        response = _call_anthropic_with_retry(self._client,
            model=self._executor_model,
            max_tokens=4096,
            system=system_prompt,
            messages=correction_messages,
        )
        raw_response = response.content[0].text
        logger.info("LLM correction response: %d chars", len(raw_response))

        try:
            return _parse_steps(raw_response)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse correction response: %s", exc)
            return None
