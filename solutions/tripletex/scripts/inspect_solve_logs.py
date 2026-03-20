#!/usr/bin/env python3
"""Inspect recorded `/solve` traces and prompt patterns."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tripletex_agent.config import AppSettings  # noqa: E402
from tripletex_agent.log_analysis import (  # noqa: E402
    group_events_by_trace,
    load_events,
    normalize_prompt_shape,
    prompt_pattern_counts,
    recent_trace_summaries,
    summarize_trace,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="Override solve-events JSONL path",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    recent_parser = subparsers.add_parser("recent", help="List recent traces")
    recent_parser.add_argument("--limit", type=int, default=10)
    recent_parser.add_argument(
        "--outcome",
        choices=("any", "completed", "failed"),
        default="any",
        help="Filter traces by final outcome",
    )

    trace_parser = subparsers.add_parser("trace", help="Show one trace in detail")
    trace_parser.add_argument("trace_id")
    trace_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the trace summary as JSON",
    )

    patterns_parser = subparsers.add_parser(
        "patterns",
        help="Show the most common normalized prompt patterns",
    )
    patterns_parser.add_argument("--top", type=int, default=10)
    patterns_parser.add_argument(
        "--outcome",
        choices=("any", "completed", "failed"),
        default="any",
        help="Filter patterns by final trace outcome",
    )

    args = parser.parse_args()

    settings = AppSettings.load()
    log_path = args.log_path or settings.solve_event_log_path
    events = load_events(log_path)
    if not events:
        print(f"No solve events found in {log_path}")
        return 1

    if args.command == "recent":
        return _print_recent(events, limit=args.limit, outcome=args.outcome)
    if args.command == "trace":
        return _print_trace(events, trace_id=args.trace_id, as_json=args.json)
    if args.command == "patterns":
        return _print_patterns(events, top=args.top, outcome=args.outcome)

    parser.error(f"Unknown command {args.command!r}")
    return 2


def _print_recent(events: list[dict[str, object]], *, limit: int, outcome: str) -> int:
    for summary in recent_trace_summaries(events, limit=limit, outcome=outcome):
        print(
            json.dumps(
                {
                    "trace_id": summary.trace_id,
                    "received_at": summary.received_at,
                    "outcome": summary.outcome,
                    "workflow": summary.workflow,
                    "task_family": summary.task_family,
                    "operation": summary.operation,
                    "api_call_count": summary.api_call_count,
                    "api_error_count": summary.api_error_count,
                    "prompt": summary.prompt,
                    "normalized_prompt": normalize_prompt_shape(summary.prompt),
                },
                ensure_ascii=False,
            )
        )
    return 0


def _print_trace(events: list[dict[str, object]], *, trace_id: str, as_json: bool) -> int:
    grouped = group_events_by_trace(events)
    trace_events = grouped.get(trace_id)
    if not trace_events:
        print(f"Trace not found: {trace_id}", file=sys.stderr)
        return 1

    summary = summarize_trace(trace_id, trace_events)
    if as_json:
        print(
            json.dumps(
                {
                    "trace_id": summary.trace_id,
                    "received_at": summary.received_at,
                    "outcome": summary.outcome,
                    "prompt": summary.prompt,
                    "normalized_prompt": normalize_prompt_shape(summary.prompt),
                    "workflow": summary.workflow,
                    "task_family": summary.task_family,
                    "operation": summary.operation,
                    "api_call_count": summary.api_call_count,
                    "api_error_count": summary.api_error_count,
                    "api_call_plan": summary.api_call_plan,
                    "result_resources": summary.result_resources,
                    "error": summary.error,
                    "api_calls": summary.api_calls,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"trace_id: {summary.trace_id}")
    print(f"received_at: {summary.received_at}")
    print(f"outcome: {summary.outcome}")
    print(f"workflow: {summary.workflow}")
    print(f"task_family: {summary.task_family}")
    print(f"operation: {summary.operation}")
    print(f"api_call_count: {summary.api_call_count}")
    print(f"api_error_count: {summary.api_error_count}")
    print(f"result_resources: {summary.result_resources}")
    print("prompt:")
    print(summary.prompt)
    print("normalized_prompt:")
    print(normalize_prompt_shape(summary.prompt))
    if summary.api_call_plan:
        print("api_call_plan:")
        print(json.dumps(summary.api_call_plan, ensure_ascii=False, indent=2))
    if summary.error:
        print("error:")
        print(json.dumps(summary.error, ensure_ascii=False, indent=2))
    print("api_calls:")
    for index, call in enumerate(summary.api_calls, start=1):
        print(
            json.dumps(
                {
                    "index": index,
                    **call,
                },
                ensure_ascii=False,
            )
        )
    return 0


def _print_patterns(events: list[dict[str, object]], *, top: int, outcome: str) -> int:
    patterns = prompt_pattern_counts(events, top=top, outcome=outcome)
    for pattern in patterns:
        print(json.dumps(pattern, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
