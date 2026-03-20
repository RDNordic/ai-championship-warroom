"""LLM-driven API executor using Claude Haiku for uncovered task types."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .api_validator import ApiCallValidator
from .client import TripletexClient
from .endpoint_catalog import catalog_as_text
from .models import AttachmentFile
from .task_plan import TaskPlan
from .workflows.base import WorkflowResult

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

_SYSTEM_PROMPT = """\
You are a Tripletex API assistant. Given a task prompt \
(often in Norwegian), produce the exact API calls needed.

AVAILABLE ENDPOINTS:
{catalog}

RULES:
- Use ONLY endpoints from the catalog above.
- Minimize API calls — fewer is better.
- Chain IDs: when step N needs an ID from step M, use \
save_response_fields_as to save it, then reference as \
"$variable_name" in later steps' json_body or path.
- Never guess field names — use only documented fields.
- POST /invoice accepts ?sendToCustomer=true|false as query param.
- You may need to create prerequisites first \
(customer before invoice, product before order line).
- For entity references in body, use object format: \
{{"id": <id>}} or {{"id": "$saved_var"}}.
- For dates, use ISO format: "YYYY-MM-DD".
- For currency/amounts, use numeric values (not strings).
- vatType should be an object like {{"id": 3}} for 25% MVA.
- GET uses query params. POST/PUT uses json_body.
- If a GET is needed to find an ID first, include it as a step.

OUTPUT FORMAT:
Return a JSON array of steps. Each step has:
- "step_id": string identifier (e.g., "1", "2", "3")
- "method": "GET" | "POST" | "PUT" | "DELETE"
- "path": the API path (e.g., "/customer")
- "params": optional dict of query parameters
- "json_body": optional dict of request body (for POST/PUT)
- "save_response_fields_as": optional dict mapping var names \
to response paths (e.g., {{"customer_id": "value.id"}})

Example for creating a customer then an invoice:
[
  {{
    "step_id": "1",
    "method": "POST",
    "path": "/customer",
    "json_body": {{"name": "Acme AS", "isCustomer": true}},
    "save_response_fields_as": {{"customer_id": "value.id"}}
  }},
  {{
    "step_id": "2",
    "method": "POST",
    "path": "/order",
    "json_body": {{
      "customer": {{"id": "$customer_id"}},
      "orderDate": "2026-03-20",
      "deliveryDate": "2026-03-20",
      "orderLines": [{{"product": {{"id": 1}}, "count": 1}}]
    }},
    "save_response_fields_as": {{"order_id": "value.id"}}
  }},
  {{
    "step_id": "3",
    "method": "POST",
    "path": "/invoice",
    "params": {{"sendToCustomer": "false"}},
    "json_body": {{
      "invoiceDate": "2026-03-20",
      "invoiceDueDate": "2026-04-20",
      "customer": {{"id": "$customer_id"}},
      "orders": [{{"id": "$order_id"}}]
    }},
    "save_response_fields_as": {{"invoice_id": "value.id"}}
  }}
]

Return ONLY the JSON array, no markdown fences, no explanatory text."""


def _build_system_prompt() -> str:
    return _SYSTEM_PROMPT.format(catalog=catalog_as_text())


def _resolve_value(obj: Any, path: str) -> Any:
    """Extract a value from a nested dict using a dot-separated path.

    E.g., _resolve_value({"value": {"id": 42}}, "value.id") → 42
    """
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
        # Also handle embedded references like "/customer/$customer_id"
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
    # Strip markdown fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove first and last lines (fences)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse LLM response as JSON array: {text[:200]}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

    return parsed


class LLMApiExecutor:
    """Executes Tripletex API calls planned by Claude Haiku."""

    def __init__(self, *, api_key: str, model: str) -> None:
        if anthropic is None:
            raise RuntimeError("anthropic package is required for LLMApiExecutor")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._validator = ApiCallValidator()
        self._system_prompt = _build_system_prompt()

    async def execute(
        self,
        *,
        prompt: str,
        attachments: list[AttachmentFile],
        plan: TaskPlan,
        tripletex_client: TripletexClient,
    ) -> WorkflowResult:
        """Ask Haiku to plan API calls, validate, then execute them."""

        # 1. Build user message with context
        plan_json = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)
        attachment_section = ""
        if attachments:
            att_lines = [f"- {a.filename} ({a.mime_type})" for a in attachments]
            attachment_section = "\nAttachments:\n" + "\n".join(att_lines)

        user_message = (
            f"Task prompt:\n{prompt}\n\n"
            f"Planner analysis:\n{plan_json}"
            f"{attachment_section}\n\n"
            "Produce the JSON array of API call steps to accomplish this task."
        )

        # 2. Call Claude Haiku
        logger.info("Calling LLM for API plan: model=%s prompt_len=%d", self._model, len(prompt))
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_response = response.content[0].text
        logger.info("LLM response length: %d chars", len(raw_response))

        # 3. Parse steps
        try:
            steps = _parse_steps(raw_response)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse LLM response: %s", exc)
            return WorkflowResult(
                name="llm_executor",
                completed=False,
                details={"error": f"Failed to parse LLM response: {exc}"},
            )

        logger.info("Parsed %d API call steps from LLM", len(steps))

        # 4. Validate the plan
        validation = self._validator.validate_plan(steps)
        if not validation.valid:
            logger.warning(
                "LLM plan validation failed: %s — executing anyway",
                validation.errors,
            )
            # Log but don't block — some validation warnings are non-fatal

        # 5. Execute steps sequentially, chaining saved variables
        saved_vars: dict[str, Any] = {}
        executed_operations: list[str] = []
        resource_ids: list[int] = []
        all_details: dict[str, Any] = {
            "steps_planned": len(steps),
            "steps_executed": 0,
            "llm_model": self._model,
            "validation_errors": validation.errors,
        }

        for step in steps:
            step_id = step.get("step_id", "?")
            method = step.get("method", "GET")
            path = step.get("path", "")
            params = step.get("params")
            json_body = step.get("json_body")
            save_fields = step.get("save_response_fields_as", {})

            # Substitute saved variables into path, params, and body
            path = _substitute_vars(path, saved_vars)
            if params:
                params = _substitute_vars(params, saved_vars)
            if json_body:
                json_body = _substitute_vars(json_body, saved_vars)

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
            except Exception as exc:
                logger.error("Step %s failed: %s", step_id, exc)
                all_details[f"step_{step_id}_error"] = str(exc)
                # Continue with remaining steps — some may still work
                executed_operations.append(f"{method} {path} [FAILED]")
                continue

            executed_operations.append(f"{method} {path}")
            all_details["steps_executed"] = all_details.get("steps_executed", 0) + 1

            # Extract and save response fields
            if save_fields and isinstance(save_fields, dict) and response_payload:
                for var_name, field_path in save_fields.items():
                    value = _resolve_value(response_payload, field_path)
                    if value is not None:
                        saved_vars[var_name] = value
                        logger.info("Saved %s = %s", var_name, value)
                        # Track created resource IDs
                        if isinstance(value, int) and field_path.endswith(".id"):
                            resource_ids.append(value)
                    else:
                        logger.warning(
                            "Could not extract %s from response via path '%s'",
                            var_name,
                            field_path,
                        )

        all_details["saved_vars"] = {k: str(v) for k, v in saved_vars.items()}

        completed = all_details.get("steps_executed", 0) > 0
        return WorkflowResult(
            name="llm_executor",
            completed=completed,
            intended_operations=executed_operations,
            resource_ids=resource_ids,
            details=all_details,
        )
