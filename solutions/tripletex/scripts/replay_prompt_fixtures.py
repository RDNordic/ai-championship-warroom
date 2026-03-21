#!/usr/bin/env python3
"""Replay known prompt fixtures through the planner and workflow selector."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tripletex_agent.config import AppSettings  # noqa: E402
from tripletex_agent.models import AttachmentFile  # noqa: E402
from tripletex_agent.planner import KeywordTaskPlanner, build_default_planner  # noqa: E402
from tripletex_agent.service import build_default_workflow_registry  # noqa: E402

DEFAULT_FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "replay_prompt_fixtures.json"


def _attachments_from_fixture(raw_attachments: list[dict[str, Any]] | None) -> list[AttachmentFile]:
    attachments: list[AttachmentFile] = []
    for attachment in raw_attachments or []:
        attachments.append(
            AttachmentFile(
                filename=str(attachment["filename"]),
                mime_type=str(attachment["mime_type"]),
                content_base64="aGVsbG8=",
            )
        )
    return attachments


def _actual_result(
    prompt: str,
    *,
    keyword_only: bool,
    attachments: list[AttachmentFile] | None = None,
) -> dict[str, Any]:
    planner = KeywordTaskPlanner() if keyword_only else build_default_planner(AppSettings.load())
    registry = build_default_workflow_registry()
    plan = planner.plan(prompt, attachments or [])
    workflow = registry.for_plan(plan)

    return {
        "task_family": plan.task_family.value,
        "operation": plan.operation.value,
        "workflow": workflow.__class__.__name__,
        "lookup": plan.entities_to_find[0].lookup if plan.entities_to_find else {},
        "fields_to_set": plan.fields_to_set,
        "completion_checks": [
            f"{check.kind}:{check.entity_type}" for check in plan.completion_checks
        ],
    }


def _collect_mismatches(expected: Any, actual: Any, *, path: str = "") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '<root>'}: expected object, got {type(actual).__name__}"]
        mismatches: list[str] = []
        for key, value in expected.items():
            child_path = f"{path}.{key}" if path else key
            if key not in actual:
                mismatches.append(f"{child_path}: missing")
                continue
            mismatches.extend(_collect_mismatches(value, actual[key], path=child_path))
        return mismatches

    if expected != actual:
        return [f"{path or '<root>'}: expected {expected!r}, got {actual!r}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-file",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to a JSON fixture file",
    )
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="Use the keyword planner instead of the configured default planner",
    )
    args = parser.parse_args()

    fixtures = json.loads(args.fixture_file.read_text(encoding="utf-8"))
    failures: list[dict[str, Any]] = []

    for fixture in fixtures:
        actual = _actual_result(
            fixture["prompt"],
            keyword_only=args.keyword_only,
            attachments=_attachments_from_fixture(fixture.get("attachments")),
        )
        mismatches = _collect_mismatches(fixture["expected"], actual)
        status = "PASS" if not mismatches else "FAIL"
        print(f"[{status}] {fixture['id']}")
        if mismatches:
            failures.append(
                {
                    "id": fixture["id"],
                    "mismatches": mismatches,
                    "actual": actual,
                }
            )

    if failures:
        print(json.dumps(failures, indent=2, ensure_ascii=False))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
