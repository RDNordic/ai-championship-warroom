#!/usr/bin/env python3
"""Plan or execute a Tripletex prompt locally against the sandbox."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tripletex_agent.client import (  # noqa: E402
    TripletexAPIError,  # noqa: E402
    TripletexClient,  # noqa: E402
)
from tripletex_agent.config import AppSettings  # noqa: E402
from tripletex_agent.planner import build_default_planner  # noqa: E402
from tripletex_agent.task_plan import TaskFamily  # noqa: E402
from tripletex_agent.workflows import (  # noqa: E402
    CustomerCreateWorkflow,
    CustomerDeleteWorkflow,
    CustomerUpdateWorkflow,
    DepartmentCreateWorkflow,
    DepartmentDeleteWorkflow,
    EmployeeCreateWorkflow,
    EmployeeUpdateWorkflow,
    InvoiceCreateWorkflow,
    InvoiceCreditNoteWorkflow,
    InvoicePaymentWorkflow,
    OrderInvoicePaymentWorkflow,
    ProductCreateWorkflow,
    ProductDeleteWorkflow,
    ProjectCreateWorkflow,
    ProjectDeleteWorkflow,
    StubWorkflow,
    TravelExpenseCreateWorkflow,
    TravelExpenseDeleteWorkflow,
    WorkflowRegistry,
)
from tripletex_agent.workflows.base import WorkflowExecutionError  # noqa: E402


def build_registry() -> WorkflowRegistry:
    return WorkflowRegistry(
        workflows=[
            CustomerCreateWorkflow(),
            ProductCreateWorkflow(),
            EmployeeCreateWorkflow(),
            DepartmentCreateWorkflow(),
            ProjectCreateWorkflow(),
            OrderInvoicePaymentWorkflow(),
            InvoiceCreateWorkflow(),
            InvoicePaymentWorkflow(),
            InvoiceCreditNoteWorkflow(),
            TravelExpenseCreateWorkflow(),
            CustomerUpdateWorkflow(),
            EmployeeUpdateWorkflow(),
            CustomerDeleteWorkflow(),
            ProductDeleteWorkflow(),
            DepartmentDeleteWorkflow(),
            ProjectDeleteWorkflow(),
            TravelExpenseDeleteWorkflow(),
        ],
        fallback=StubWorkflow(TaskFamily.UNKNOWN),
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Task prompt to plan or execute")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the selected workflow against the configured sandbox",
    )
    args = parser.parse_args()

    settings = AppSettings.load()
    planner = build_default_planner(settings)
    plan = planner.plan(args.prompt, [])

    print("Task plan:")
    print(json.dumps(plan.model_dump(), indent=2))

    registry = build_registry()
    workflow = registry.for_plan(plan)
    print(f"Selected workflow: {workflow.__class__.__name__}")

    if not args.execute:
        print("Dry run only. Re-run with --execute to call Tripletex.")
        return 0

    credentials = settings.tripletex_credentials()
    async with TripletexClient.from_credentials(credentials) as client:
        try:
            result = await workflow.execute(plan=plan, client=client)
        except WorkflowExecutionError as exc:
            print(f"Workflow failed: {exc}", file=sys.stderr)
            return 1
        except TripletexAPIError as exc:
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

    print("Workflow result:")
    print(json.dumps(result.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
