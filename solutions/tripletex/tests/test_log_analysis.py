from __future__ import annotations

from tripletex_agent.log_analysis import (
    group_events_by_trace,
    normalize_prompt_shape,
    prompt_pattern_counts,
    recent_trace_summaries,
    summarize_trace,
)


def _sample_events() -> list[dict[str, object]]:
    return [
        {
            "timestamp": "2026-03-20T11:37:05+00:00",
            "event": "received",
            "trace_id": "trace-customer-1",
            "request": {
                "prompt": (
                    "Add customer named ACME AS, email finance@acme.test "
                    "on 2026-03-20 at 11:37 invoice #42"
                ),
            },
        },
        {
            "timestamp": "2026-03-20T11:37:06+00:00",
            "event": "planned",
            "trace_id": "trace-customer-1",
            "workflow": "CustomerCreateWorkflow",
            "task_family": "customers_products",
            "operation": "create",
        },
        {
            "timestamp": "2026-03-20T11:37:07+00:00",
            "event": "tripletex_call",
            "trace_id": "trace-customer-1",
            "call": {
                "method": "POST",
                "path": "/customer",
                "status_code": 201,
                "duration_ms": 120,
                "params": None,
                "json_body": {"name": "ACME AS"},
            },
        },
        {
            "timestamp": "2026-03-20T11:37:08+00:00",
            "event": "completed",
            "trace_id": "trace-customer-1",
            "workflow": "CustomerCreateWorkflow",
            "task_family": "customers_products",
            "operation": "create",
            "result": {"resource_ids": [101]},
        },
        {
            "timestamp": "2026-03-20T11:39:05+00:00",
            "event": "received",
            "trace_id": "trace-customer-2",
            "request": {
                "prompt": (
                    "Add customer named Beta AS, email beta@acme.test "
                    "on 2026-03-21 at 12:01 invoice #43"
                ),
            },
        },
        {
            "timestamp": "2026-03-20T11:39:06+00:00",
            "event": "planned",
            "trace_id": "trace-customer-2",
            "workflow": "CustomerCreateWorkflow",
            "task_family": "customers_products",
            "operation": "create",
        },
        {
            "timestamp": "2026-03-20T11:39:07+00:00",
            "event": "tripletex_call",
            "trace_id": "trace-customer-2",
            "call": {
                "method": "POST",
                "path": "/customer",
                "status_code": 201,
                "duration_ms": 118,
                "params": None,
                "json_body": {"name": "Beta AS"},
            },
        },
        {
            "timestamp": "2026-03-20T11:39:08+00:00",
            "event": "completed",
            "trace_id": "trace-customer-2",
            "workflow": "CustomerCreateWorkflow",
            "task_family": "customers_products",
            "operation": "create",
            "result": {"resource_ids": [102]},
        },
        {
            "timestamp": "2026-03-20T11:40:05+00:00",
            "event": "received",
            "trace_id": "trace-invoice-1",
            "request": {
                "prompt": (
                    "Pay invoice #77 for customer Beta AS on 2026-03-22 "
                    "at 08:45"
                ),
            },
        },
        {
            "timestamp": "2026-03-20T11:40:06+00:00",
            "event": "planned",
            "trace_id": "trace-invoice-1",
            "workflow": "InvoicePaymentWorkflow",
            "task_family": "invoicing",
            "operation": "pay",
        },
        {
            "timestamp": "2026-03-20T11:40:07+00:00",
            "event": "tripletex_call",
            "trace_id": "trace-invoice-1",
            "call": {
                "method": "POST",
                "path": "/payment",
                "status_code": 422,
                "duration_ms": 70,
                "params": None,
                "json_body": {"invoiceId": 77},
            },
        },
        {
            "timestamp": "2026-03-20T11:40:08+00:00",
            "event": "failed",
            "trace_id": "trace-invoice-1",
            "workflow": "InvoicePaymentWorkflow",
            "task_family": "invoicing",
            "operation": "pay",
            "error": {"type": "TripletexAPIError", "message": "Missing paymentDate"},
        },
    ]


def test_normalize_prompt_shape_masks_variable_slots() -> None:
    normalized = normalize_prompt_shape(
        "Create employee named Ola Nordmann, email ola@example.org "
        "on 2026-03-20 at 11:37 invoice #42"
    )

    assert normalized == (
        "create employee named <value>, email <email> on <date> at <time> invoice <num>"
    )


def test_normalize_prompt_shape_preserves_org_language_vat_and_send_intent() -> None:
    normalized = normalize_prompt_shape(
        "Create and send an invoice to customer ACME AS organization number 123 456 789 "
        "email finance@acme.test language English for 8750 NOK excluding VAT."
    )

    assert "send" in normalized
    assert "for customer <value>" in normalized
    assert "organization number <orgnum>" in normalized
    assert "email <email>" in normalized
    assert "language <language>" in normalized
    assert "excluding vat" in normalized


def test_normalize_prompt_shape_keeps_logged_french_invoice_send_semantics_visible() -> None:
    normalized = normalize_prompt_shape(
        "Créez et envoyez une facture au client Lumière SARL "
        "(nº org. 827689114) de 8750 NOK hors TVA. "
        "La facture concerne Maintenance."
    )

    assert "send" in normalized
    assert "for customer <value>" in normalized
    assert "organization number <orgnum>" in normalized
    assert "excluding vat" in normalized


def test_summarize_trace_counts_api_errors_and_resources() -> None:
    grouped = group_events_by_trace(_sample_events())

    summary = summarize_trace("trace-invoice-1", grouped["trace-invoice-1"])

    assert summary.outcome == "failed"
    assert summary.workflow == "InvoicePaymentWorkflow"
    assert summary.task_family == "invoicing"
    assert summary.operation == "pay"
    assert summary.api_call_count == 1
    assert summary.api_error_count == 1
    assert summary.result_resources == []
    assert summary.error == {"type": "TripletexAPIError", "message": "Missing paymentDate"}


def test_recent_trace_summaries_can_filter_outcome() -> None:
    summaries = recent_trace_summaries(_sample_events(), limit=5, outcome="failed")

    assert [summary.trace_id for summary in summaries] == ["trace-invoice-1"]


def test_prompt_pattern_counts_group_typical_prompts_and_support_outcome_filter() -> None:
    patterns = prompt_pattern_counts(_sample_events(), top=5)

    assert patterns[0]["pattern"] == (
        "add customer named <value>, email <email> on <date> at <time> invoice <num>"
    )
    assert patterns[0]["count"] == 2
    assert patterns[0]["completed_count"] == 2
    assert patterns[0]["failed_count"] == 0
    assert patterns[0]["top_workflow"] == "CustomerCreateWorkflow"
    assert patterns[0]["top_task_family"] == "customers_products"
    assert patterns[0]["top_operation"] == "create"

    failed_patterns = prompt_pattern_counts(_sample_events(), top=5, outcome="failed")
    assert failed_patterns == [
        {
            "pattern": "pay invoice <num> for customer <value>",
            "count": 1,
            "completed_count": 0,
            "failed_count": 1,
            "latest_received_at": "2026-03-20T11:40:05+00:00",
            "top_workflow": "InvoicePaymentWorkflow",
            "top_task_family": "invoicing",
            "top_operation": "pay",
            "example_prompt": "Pay invoice #77 for customer Beta AS on 2026-03-22 at 08:45",
            "example_trace_id": "trace-invoice-1",
        }
    ]
