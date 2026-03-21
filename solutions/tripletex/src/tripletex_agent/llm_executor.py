"""Unified LLM-driven API executor — the single execution path for all tasks."""

from __future__ import annotations

import base64
import json
import logging
import re
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

## Invoice Credit Note
CRITICAL: PUT /invoice/{{id}}/:createCreditNote uses QUERY PARAMS (date, sendToCustomer).

## Account Lookup
Norwegian accounts are ALWAYS 4 digits. NEVER use 5-digit numbers.
If unsure of the exact number, search by name: GET /ledger/account?query=<keyword>&count=5
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


def _parse_steps(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of step dicts."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

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
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        break

    # Last resort: greedy regex
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse LLM response as JSON array: {text[:200]}")


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
        if not validation.valid:
            logger.warning(
                "LLM plan validation failed: %s — executing anyway",
                validation.errors,
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
            "validation_errors": validation.errors,
        }

        result = await self._execute_steps(
            steps=steps,
            tripletex_client=tripletex_client,
            saved_vars=saved_vars,
            executed_operations=executed_operations,
            resource_ids=resource_ids,
            all_details=all_details,
        )

        # Self-correction on failure (max 1 retry)
        if result is not None and not all_details.get("retried"):
            failed_step_id = result["step_id"]
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
                failed_method=result["method"],
                failed_path=result["path"],
                error_detail=result["error"],
                auto_fixes=result["auto_fixes"],
                fields_removed=result["fields_removed"],
                remaining_steps=[
                    s for s in steps
                    if int(s.get("step_id", "0")) > int(failed_step_id)
                    or s.get("step_id") == failed_step_id
                ],
            )

            if correction_steps:
                logger.info(
                    "LLM produced %d corrected steps, retrying",
                    len(correction_steps),
                )
                all_details["correction_steps"] = len(correction_steps)
                await self._execute_steps(
                    steps=correction_steps,
                    tripletex_client=tripletex_client,
                    saved_vars=saved_vars,
                    executed_operations=executed_operations,
                    resource_ids=resource_ids,
                    all_details=all_details,
                )

        all_details["saved_vars"] = {k: str(v) for k, v in saved_vars.items()}

        completed = all_details.get("steps_executed", 0) > 0
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

            # Validate and clean json_body against swagger schema
            step_fixes: list[str] = []
            step_removed: list[str] = []

            # Check for unresolved $variable references — don't send if found
            unresolved = _find_unresolved_vars(path, params, json_body)
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
                # Auto-fix voucher: inject date if missing
                if method == "POST" and "/voucher" in path and "date" not in json_body:
                    from datetime import date as _date
                    json_body["date"] = _date.today().isoformat()
                    step_fixes.append("Injected missing 'date' field with today's date")
                schema_result = self._schema_validator.validate_and_clean(
                    method, path, json_body
                )
                json_body = schema_result.cleaned_body
                step_fixes = schema_result.fixes_applied + step_fixes
                step_removed = schema_result.fields_removed
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
        template = (_PROMPTS_DIR / "retry_correction.md").read_text(encoding="utf-8")

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
