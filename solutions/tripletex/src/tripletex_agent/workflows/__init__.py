"""Workflow exports for the Tripletex scaffold."""

from .base import BaseWorkflow, WorkflowExecutionError, WorkflowResult
from .live import (
    CustomerCreateWorkflow,
    DepartmentCreateWorkflow,
    EmployeeCreateWorkflow,
    InvoiceCreateWorkflow,
    InvoiceCreditNoteWorkflow,
    InvoicePaymentWorkflow,
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
    "InvoiceCreditNoteWorkflow",
    "InvoiceCreateWorkflow",
    "InvoicePaymentWorkflow",
    "ProductCreateWorkflow",
    "ProjectCreateWorkflow",
    "StubWorkflow",
    "WorkflowExecutionError",
    "WorkflowRegistry",
    "WorkflowResult",
]
