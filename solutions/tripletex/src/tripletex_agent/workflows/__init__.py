"""Workflow exports for the Tripletex scaffold."""

from .base import BaseWorkflow, WorkflowExecutionError, WorkflowResult
from .live import (
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
    ProductCreateWorkflow,
    ProductDeleteWorkflow,
    ProjectCreateWorkflow,
    ProjectDeleteWorkflow,
    TravelExpenseCreateWorkflow,
    TravelExpenseDeleteWorkflow,
)
from .registry import WorkflowRegistry
from .stub import StubWorkflow

__all__ = [
    "BaseWorkflow",
    "CustomerCreateWorkflow",
    "CustomerDeleteWorkflow",
    "CustomerUpdateWorkflow",
    "DepartmentCreateWorkflow",
    "DepartmentDeleteWorkflow",
    "EmployeeCreateWorkflow",
    "EmployeeUpdateWorkflow",
    "InvoiceCreditNoteWorkflow",
    "InvoiceCreateWorkflow",
    "InvoicePaymentWorkflow",
    "ProductCreateWorkflow",
    "ProductDeleteWorkflow",
    "ProjectCreateWorkflow",
    "ProjectDeleteWorkflow",
    "StubWorkflow",
    "TravelExpenseCreateWorkflow",
    "TravelExpenseDeleteWorkflow",
    "WorkflowExecutionError",
    "WorkflowRegistry",
    "WorkflowResult",
]
