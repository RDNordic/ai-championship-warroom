"""Helpers for inspecting solve-event logs."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_NUMERIC_TOKEN_RE = re.compile(r"(?<!\w)#?\d[\d.-]*\b")

_PROMPT_SLOT_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\b(?:named|med navn|with name|som heter|called)\s+([^,\n]+)",
        "named <value>",
    ),
    (
        r"\b(?:for|til)\s+(?:customer|kunde)\s+([^,\n]+)",
        "for customer <value>",
    ),
    (
        r"\b(?:project manager|prosjektleder)\s+([^,\n]+)",
        "project manager <value>",
    ),
    (
        r"\b(?:invoice comment|fakturakommentar)\s+([^,\n]+)",
        "invoice comment <value>",
    ),
    (
        r"\b(?:comment|kommentar)\s+([^,\n]+)",
        "comment <value>",
    ),
)

OutcomeFilter = Literal["any", "completed", "failed"]


@dataclass(frozen=True)
class TraceSummary:
    """Human-oriented summary of one traced solve request."""

    trace_id: str
    prompt: str
    received_at: str | None
    workflow: str | None
    task_family: str | None
    operation: str | None
    outcome: str
    api_call_count: int
    api_error_count: int
    api_calls: list[dict[str, Any]]
    result_resources: list[int]
    error: dict[str, Any] | None


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        events.append(json.loads(stripped))
    return events


def group_events_by_trace(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        trace_id = event.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            grouped[trace_id].append(event)

    for trace_events in grouped.values():
        trace_events.sort(key=lambda event: str(event.get("timestamp", "")))
    return dict(grouped)


def summarize_trace(trace_id: str, trace_events: list[dict[str, Any]]) -> TraceSummary:
    received = _first_event(trace_events, "received")
    planned = _last_event(trace_events, "planned")
    completed = _last_event(trace_events, "completed")
    failed = _last_event(trace_events, "failed")
    call_events = [event for event in trace_events if event.get("event") == "tripletex_call"]

    result_resources: list[int] = []
    if completed is not None:
        resource_ids = completed.get("result", {}).get("resource_ids", [])
        if isinstance(resource_ids, list):
            result_resources = [item for item in resource_ids if isinstance(item, int)]

    error = (
        failed.get("error")
        if failed is not None and isinstance(failed.get("error"), dict)
        else None
    )
    outcome = (
        "completed"
        if completed is not None
        else "failed" if failed is not None else "unknown"
    )

    api_calls = [_api_call_summary(event) for event in call_events]
    api_error_count = sum(1 for call in api_calls if call["status_code"] >= 400)

    request_payload = received.get("request", {}) if isinstance(received, dict) else {}
    prompt = request_payload.get("prompt") if isinstance(request_payload, dict) else None

    return TraceSummary(
        trace_id=trace_id,
        prompt=prompt if isinstance(prompt, str) else "",
        received_at=received.get("timestamp") if isinstance(received, dict) else None,
        workflow=_coalesce_str(
            planned.get("workflow") if planned is not None else None,
            completed.get("workflow") if completed is not None else None,
            failed.get("workflow") if failed is not None else None,
        ),
        task_family=_coalesce_str(
            planned.get("task_family") if planned is not None else None,
            completed.get("task_family") if completed is not None else None,
            failed.get("task_family") if failed is not None else None,
        ),
        operation=_coalesce_str(
            planned.get("operation") if planned is not None else None,
            completed.get("operation") if completed is not None else None,
            failed.get("operation") if failed is not None else None,
        ),
        outcome=outcome,
        api_call_count=len(api_calls),
        api_error_count=api_error_count,
        api_calls=api_calls,
        result_resources=result_resources,
        error=error,
    )


def recent_trace_summaries(
    events: list[dict[str, Any]],
    *,
    limit: int = 10,
    outcome: OutcomeFilter = "any",
) -> list[TraceSummary]:
    grouped = group_events_by_trace(events)
    summaries = [
        summarize_trace(trace_id, trace_events)
        for trace_id, trace_events in grouped.items()
    ]
    summaries = [summary for summary in summaries if _matches_outcome(summary, outcome)]
    summaries.sort(key=lambda summary: summary.received_at or "", reverse=True)
    return summaries[:limit]


def prompt_pattern_counts(
    events: list[dict[str, Any]],
    *,
    top: int = 10,
    outcome: OutcomeFilter = "any",
) -> list[dict[str, Any]]:
    summaries = recent_trace_summaries(
        events,
        limit=len(group_events_by_trace(events)),
        outcome=outcome,
    )
    counter: Counter[str] = Counter()
    completed_counter: Counter[str] = Counter()
    failed_counter: Counter[str] = Counter()
    examples: dict[str, str] = {}
    trace_ids: dict[str, str] = {}
    latest_seen_at: dict[str, str | None] = {}
    workflow_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
    task_family_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
    operation_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for summary in summaries:
        if not summary.prompt:
            continue
        pattern = normalize_prompt_shape(summary.prompt)
        counter[pattern] += 1
        if summary.outcome == "completed":
            completed_counter[pattern] += 1
        if summary.outcome == "failed":
            failed_counter[pattern] += 1
        examples.setdefault(pattern, summary.prompt)
        trace_ids.setdefault(pattern, summary.trace_id)
        latest_seen_at[pattern] = _latest_timestamp(
            latest_seen_at.get(pattern),
            summary.received_at,
        )
        if summary.workflow:
            workflow_counter[pattern][summary.workflow] += 1
        if summary.task_family:
            task_family_counter[pattern][summary.task_family] += 1
        if summary.operation:
            operation_counter[pattern][summary.operation] += 1

    results: list[dict[str, Any]] = []
    for pattern, count in counter.most_common(top):
        results.append(
            {
                "pattern": pattern,
                "count": count,
                "completed_count": completed_counter[pattern],
                "failed_count": failed_counter[pattern],
                "latest_received_at": latest_seen_at.get(pattern),
                "top_workflow": _top_counter_value(workflow_counter[pattern]),
                "top_task_family": _top_counter_value(task_family_counter[pattern]),
                "top_operation": _top_counter_value(operation_counter[pattern]),
                "example_prompt": examples[pattern],
                "example_trace_id": trace_ids[pattern],
            }
        )
    return results


def normalize_prompt_shape(prompt: str) -> str:
    normalized = prompt.strip().lower()
    normalized = _EMAIL_RE.sub("<email>", normalized)
    normalized = _UUID_RE.sub("<uuid>", normalized)
    normalized = _ISO_DATE_RE.sub("<date>", normalized)
    normalized = _TIME_RE.sub("<time>", normalized)

    for pattern, replacement in _PROMPT_SLOT_PATTERNS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    normalized = _NUMERIC_TOKEN_RE.sub("<num>", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def _first_event(trace_events: list[dict[str, Any]], event_name: str) -> dict[str, Any] | None:
    for event in trace_events:
        if event.get("event") == event_name:
            return event
    return None


def _last_event(trace_events: list[dict[str, Any]], event_name: str) -> dict[str, Any] | None:
    for event in reversed(trace_events):
        if event.get("event") == event_name:
            return event
    return None


def _coalesce_str(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _api_call_summary(event: dict[str, Any]) -> dict[str, Any]:
    call = event.get("call", {})
    if not isinstance(call, dict):
        call = {}
    return {
        "method": call.get("method"),
        "path": call.get("path"),
        "status_code": call.get("status_code", 0),
        "duration_ms": call.get("duration_ms"),
        "params": call.get("params"),
        "json_body": call.get("json_body"),
    }


def _matches_outcome(summary: TraceSummary, outcome: OutcomeFilter) -> bool:
    if outcome == "any":
        return True
    return summary.outcome == outcome


def _latest_timestamp(left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _top_counter_value(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]
