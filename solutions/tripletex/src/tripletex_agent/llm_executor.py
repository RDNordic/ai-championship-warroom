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

RECIPES:

## Employee Creation
1. GET /department (find any). 2. POST /employee (firstName, lastName, department ref, userType: "NO_ACCESS").

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

## Ledger Voucher
Postings: row starts at 1 (NOT 0). All amount fields must match. \
1500-accounts need customer ref. 2400-accounts need supplier ref.

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
    """Extract a value from a nested dict using a dot-separated path."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


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


def _parse_steps(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of step dicts."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse LLM response as JSON array: {text[:200]}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

    return parsed


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
            response = self._client.messages.create(
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

        response = self._client.messages.create(
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

            # Validate and clean json_body against swagger schema
            step_fixes: list[str] = []
            step_removed: list[str] = []
            if json_body and isinstance(json_body, dict) and method in ("POST", "PUT"):
                schema_result = self._schema_validator.validate_and_clean(
                    method, path, json_body
                )
                json_body = schema_result.cleaned_body
                step_fixes = schema_result.fixes_applied
                step_removed = schema_result.fields_removed
                if step_fixes:
                    all_details[f"step_{step_id}_fixes"] = step_fixes
                if not schema_result.valid:
                    all_details[f"step_{step_id}_validation_warnings"] = schema_result.errors

            logger.info(
                "Executing step %s: %s %s params=%s body_keys=%s",
                step_id,
                method,
                path,
                list(params.keys()) if params else None,
                list(json_body.keys()) if isinstance(json_body, dict) else None,
            )

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
                error_msg = str(exc)
                logger.error("Step %s failed: %s", step_id, exc)
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

            executed_operations.append(f"{method} {path}")
            all_details["steps_executed"] = all_details.get("steps_executed", 0) + 1

            if save_fields and isinstance(save_fields, dict) and response_payload:
                for var_name, field_path in save_fields.items():
                    value = _resolve_value(response_payload, field_path)
                    if value is not None:
                        saved_vars[var_name] = value
                        logger.info("Saved %s = %s", var_name, value)
                        if isinstance(value, int) and field_path.endswith(".id"):
                            resource_ids.append(value)
                    else:
                        logger.warning(
                            "Could not extract %s from response via path '%s'",
                            var_name,
                            field_path,
                        )

        return None

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

        # For correction, use a simple message without tools
        # (the LLM already has the schema from the correction prompt)
        correction_messages: list[dict[str, Any]] = [
            {"role": "user", "content": correction_prompt},
        ]

        logger.info("Requesting LLM correction for step %s", failed_step_id)

        response = self._client.messages.create(
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
