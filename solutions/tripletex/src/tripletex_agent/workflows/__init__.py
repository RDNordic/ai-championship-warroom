"""Workflow exports for the Tripletex scaffold."""

from .base import BaseWorkflow, WorkflowExecutionError, WorkflowResult
from .live import (
    CustomerCreateWorkflow,
    DepartmentCreateWorkflow,
    EmployeeCreateWorkflow,
    InvoiceCreateWorkflow,
    ProductCreateWorkflow,
    ProjectCreateWorkflow,
)
from .registry import WorkflowRegistry
from .stub import StubWorkflow

__all__ = [
    "BaseWorkflow",
    "CustomerCreateWorkflow",
    "DepartmentCreateWorkflow",
    "EmployeeCreateWorkflow",
    "InvoiceCreateWorkflow",
    "ProductCreateWorkflow",
    "ProjectCreateWorkflow",
    "StubWorkflow",
    "WorkflowExecutionError",
    "WorkflowRegistry",
    "WorkflowResult",
]
