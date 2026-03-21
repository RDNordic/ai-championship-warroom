"""OpenAI-backed dry-run API call planning for unsupported tasks."""

from __future__ import annotations

import json
from typing import Protocol

from .api_call_plan import ApiCallPlan
from .config import AppSettings
from .models import AttachmentFile
from .task_plan import TaskPlan

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at import time
    OpenAI = None

_API_CALL_PLAN_SYSTEM_PROMPT = """
You are planning Tripletex API calls for a digital accounting assistant.

You are not executing anything. You are producing a DRY-RUN plan only.

Rules:
- Output only the structured schema.
- Never include credentials, full URLs, or secrets.
- Prefer the minimum number of calls needed to solve the task safely.
- If a step needs an ID from a previous response, use save_response_fields_as.
- If the prompt is ambiguous, reflect that in assumptions and lower confidence.
- Use only path templates from this curated catalog unless the task is clearly impossible:
  - GET /customer
  - POST /customer
  - PUT /customer/{id}
  - GET /product
  - POST /product
  - GET /employee
  - POST /employee
  - PUT /employee/{id}
  - GET /department
  - POST /department
  - GET /project
  - POST /project
  - GET /invoice
  - POST /invoice
  - PUT /invoice/{id}/:payment
  - PUT /invoice/{id}/:createCreditNote
  - GET /travelExpense
  - POST /travelExpense
  - PUT /travelExpense/{id}
  - DELETE /travelExpense/{id}
  - POST /travelExpense/cost
  - POST /travelExpense/mileageAllowance
- If the task cannot be planned safely from the supported catalog, return an empty steps list.
- This is a planning prototype for unsupported tasks, so be explicit about assumptions.
""".strip()


class ApiCallPlanner(Protocol):
    """Shared interface for dry-run API call planners."""

    def plan(
        self,
        prompt: str,
        attachments: list[AttachmentFile],
        base_plan: TaskPlan,
    ) -> ApiCallPlan | None:
        """Return a dry-run API call plan for the prompt."""


class OpenAIApiCallPlanner:
    """Structured dry-run Tripletex API planner backed by the OpenAI API."""

    def __init__(self, *, api_key: str, model: str) -> None:
        if OpenAI is None:  # pragma: no cover - depends on installed dependencies
            raise RuntimeError("openai package is required for OpenAIApiCallPlanner")

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def plan(
        self,
        prompt: str,
        attachments: list[AttachmentFile],
        base_plan: TaskPlan,
    ) -> ApiCallPlan | None:
        base_plan_json = json.dumps(
            base_plan.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        attachment_lines = "\n".join(
            f"- {attachment.filename} ({attachment.mime_type})" for attachment in attachments
        )
        attachment_section = (
            f"\nAttachments:\n{attachment_lines}" if attachment_lines else "\nAttachments:\n- none"
        )

        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": _API_CALL_PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Generate a dry-run Tripletex ApiCallPlan for this prompt.\n"
                        "The existing deterministic planner could not map it to a live "
                        "workflow.\n\n"
                        f"Prompt:\n{prompt}\n\n"
                        "Existing planner output:\n"
                        f"{base_plan_json}\n"
                        f"{attachment_section}"
                    ),
                },
            ],
            text_format=ApiCallPlan,
            temperature=0,
        )
        return response.output_parsed


def build_default_api_call_planner(settings: AppSettings) -> ApiCallPlanner | None:
    if not settings.enable_api_call_plan or not settings.openai_api_key:
        return None
    try:
        return OpenAIApiCallPlanner(
            api_key=settings.openai_api_key,
            model=settings.api_call_plan_model,
        )
    except Exception:
        return None
