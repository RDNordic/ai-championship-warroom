"""Durable solve-event logging for submission forensics."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from .models import SolveRequest
from .task_plan import TaskPlan

if TYPE_CHECKING:
    from .api_call_plan import ApiCallPlan
    from .workflows.base import WorkflowResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolveRequestContext:
    """Safe metadata about an incoming `/solve` request."""

    trace_id: str
    client_host: str | None = None
    forwarded_for: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    cf_ray: str | None = None


class SolveEventLogger:
    """Appends structured solve events to a JSONL file."""

    _write_lock = Lock()

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def record_received(self, *, request: SolveRequest, context: SolveRequestContext) -> None:
        self._append(
            {
                "event": "received",
                "trace_id": context.trace_id,
                "request": {
                    "prompt": request.prompt,
                    "attachments": [
                        {
                            "filename": attachment.filename,
                            "mime_type": attachment.mime_type,
                        }
                        for attachment in request.files
                    ],
                    "tripletex_base_url": request.tripletex_credentials.base_url,
                },
                "request_meta": _context_payload(context),
            }
        )

    def record_planned(
        self,
        *,
        plan: TaskPlan,
        workflow_name: str,
        context: SolveRequestContext,
    ) -> None:
        self._append(
            {
                "event": "planned",
                "trace_id": context.trace_id,
                "task_family": plan.task_family.value,
                "operation": plan.operation.value,
                "workflow": workflow_name,
                "plan": plan.model_dump(mode="json"),
                "request_meta": _context_payload(context),
            }
        )

    def record_completed(
        self,
        *,
        plan: TaskPlan | None = None,
        workflow_name: str,
        result: WorkflowResult,
        context: SolveRequestContext,
    ) -> None:
        payload: dict[str, Any] = {
            "event": "completed",
            "trace_id": context.trace_id,
            "workflow": workflow_name,
            "result": result.model_dump(mode="json"),
            "request_meta": _context_payload(context),
        }
        if plan is not None:
            payload["task_family"] = plan.task_family.value
            payload["operation"] = plan.operation.value
        self._append(payload)

    def record_api_call_plan(
        self,
        *,
        base_plan: TaskPlan,
        workflow_name: str,
        api_call_plan: ApiCallPlan,
        context: SolveRequestContext,
    ) -> None:
        self._append(
            {
                "event": "api_call_plan",
                "trace_id": context.trace_id,
                "task_family": base_plan.task_family.value,
                "operation": base_plan.operation.value,
                "workflow": workflow_name,
                "api_call_plan": api_call_plan.model_dump(mode="json"),
                "request_meta": _context_payload(context),
            }
        )

    def record_failed(
        self,
        *,
        error: Exception,
        context: SolveRequestContext,
        plan: TaskPlan | None = None,
        workflow_name: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": "failed",
            "trace_id": context.trace_id,
            "error": _error_payload(error),
            "request_meta": _context_payload(context),
        }
        if plan is not None:
            payload["task_family"] = plan.task_family.value
            payload["operation"] = plan.operation.value
            payload["plan"] = plan.model_dump(mode="json")
        if workflow_name is not None:
            payload["workflow"] = workflow_name
        self._append(payload)

    def record_tripletex_call(
        self,
        *,
        context: SolveRequestContext,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json_body: Any | None,
        status_code: int,
        duration_ms: int,
        expected_status: tuple[int, ...],
        response_payload: Any | None = None,
    ) -> None:
        self._append(
            {
                "event": "tripletex_call",
                "trace_id": context.trace_id,
                "call": {
                    "method": method,
                    "path": path,
                    "params": params,
                    "json_body": json_body,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "expected_status": list(expected_status),
                    "response": response_payload,
                },
                "request_meta": _context_payload(context),
            }
        )

    def _append(self, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(record, ensure_ascii=False, default=str)
            with self._write_lock:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(encoded)
                    handle.write("\n")
        except Exception:
            logger.exception("Failed to append solve event log path=%s", self._path)


def _context_payload(context: SolveRequestContext) -> dict[str, Any]:
    return {
        "client_host": context.client_host,
        "forwarded_for": context.forwarded_for,
        "user_agent": context.user_agent,
        "request_id": context.request_id,
        "cf_ray": context.cf_ray,
    }


def _error_payload(error: Exception) -> dict[str, Any]:
    payload = {
        "type": error.__class__.__name__,
        "message": str(error),
    }
    status_code = getattr(error, "status_code", None)
    detail = getattr(error, "detail", None)
    if status_code is not None:
        payload["status_code"] = status_code
    if detail is not None:
        payload["detail"] = detail
    return payload
