# Tripletex Implementation Plan

**Status:** Draft baseline
**Last updated:** 2026-03-20
**Owner:** KO

## Purpose

Capture the working plan for the Tripletex challenge before implementation starts, so later changes can be compared against an explicit baseline.

## Source Baseline

Primary sources used:
- Official challenge docs on `app.ainm.no`
- Tripletex OpenAPI spec (`openapi.json`, version `2.74.00`)
- Repository challenge brief in `solutions/tripletex/README.md`

Secondary sources used with caution:
- Local scratch notes in `tripletex_task.md`
- Local external report in `comprehensive_report.md`

Rule for this project:
- When the external report conflicts with the official docs or OpenAPI spec, the official docs and spec win.

## Confirmed Facts

- The competition calls a public HTTPS `POST /solve` endpoint.
- The request body contains `prompt`, optional `files`, and `tripletex_credentials.base_url/session_token`.
- Tripletex API auth is Basic auth with username `0` and password `session_token`.
- The scoring system rewards correctness first, then efficiency.
- Efficiency is hurt by 4xx responses and unnecessary API calls.
- The API surface is broad; the challenge only needs a subset centered on employees, customers, products, invoicing, travel expenses, projects, departments, and corrections.
- Some workflows are multi-step and require using IDs from earlier calls.
- The OpenAPI spec exposes important non-obvious endpoints such as:
  - `/invoice/{id}/:payment`
  - `/invoice/{id}/:createCreditNote`
  - `/ledger/voucher/{id}/:reverse`
  - `/company/salesmodules`
  - `/employee/entitlement/:grantEntitlementsByTemplate`
  - Travel-expense child endpoints such as `/travelExpense/mileageAllowance` and `/travelExpense/cost`

## Core Strategy

Build a constrained LLM planner with deterministic workflow handlers.

Why:
- A free-form agent that invents raw API calls is too likely to incur 4xx penalties.
- The task distribution is broad, but the execution patterns are repetitive enough to encode safely in code.
- Correctness and efficiency both improve when search, validation, and write logic are explicit.

## Target Architecture

```text
POST /solve
  -> request validation
  -> attachment normalization
  -> structured task extraction
  -> deterministic workflow selection
  -> Tripletex API execution
  -> targeted verification
  -> {"status": "completed"}
```

Main components:
- `app.py` or equivalent FastAPI entrypoint
- Request/response models
- Tripletex API client with auth, retries, and small helper methods
- Structured `TaskPlan` schema for LLM output
- Workflow handlers per task family
- Attachment extraction layer
- Logging and trace output suitable for debugging submission failures

## LLM Role

The model should not decide arbitrary endpoint paths.

The model should do:
- Multilingual understanding
- Attachment interpretation
- Entity extraction
- Field extraction
- Task-family classification
- Reference resolution hints
- Confidence signaling

The model should not do:
- Free-form API sequencing
- Trial-and-error discovery in production
- Unbounded tool use

## Planned Task Model

The internal `TaskPlan` should capture:
- `task_family`
- `operation`
- `entities_to_create`
- `entities_to_find`
- `fields_to_set`
- `links_between_entities`
- `attachment_facts`
- `completion_checks`
- `confidence`

This keeps the LLM output stable while allowing the code to choose the safest workflow.

## Workflow Families

### Employees

Cover:
- Create employee
- Update employee
- Create employment when employment-specific fields are required
- Apply entitlement template when the task is about roles/access

Relevant endpoints:
- `/employee`
- `/employee/{id}`
- `/employee/employment`
- `/employee/entitlement`
- `/employee/entitlement/:grantEntitlementsByTemplate`

### Customers And Products

Cover:
- Create customer
- Update customer
- Create product
- Update product if needed by task variants

Relevant endpoints:
- `/customer`
- `/customer/{id}`
- `/product`
- `/product/{id}`

### Invoicing

Cover:
- Create invoice
- Register payment
- Create credit note

Default approach:
- Prefer the shortest reliable path after sandbox validation.
- Evaluate whether `POST /invoice` with embedded related objects is reliable enough to beat order-first creation.
- Keep an order-first fallback available if direct invoice creation proves fragile.

Relevant endpoints:
- `/invoice`
- `/invoice/{id}`
- `/invoice/{id}/:payment`
- `/invoice/{id}/:createCreditNote`
- `/order`
- `/order/orderline`
- `/order/orderline/list`

### Travel Expenses

Cover:
- Create travel expense report
- Delete travel expense report
- Potentially complete delivery/approval transitions if required by the verifier

Important design note:
- Treat travel expenses as parent plus child resources, not as a single flat payload.

Relevant endpoints:
- `/travelExpense`
- `/travelExpense/{id}`
- `/travelExpense/:deliver`
- `/travelExpense/:approve`
- `/travelExpense/mileageAllowance`
- `/travelExpense/perDiemCompensation`
- `/travelExpense/cost`
- `/travelExpense/accommodationAllowance`

### Projects

Cover:
- Create project linked to customer
- Update project if variants require edits

Relevant endpoints:
- `/project`
- `/project/{id}`

### Departments And Modules

Cover:
- Create department
- Enable relevant accounting/sales modules if the task requires it

Relevant endpoints:
- `/department`
- `/department/{id}`
- `/company/salesmodules`

Open verification task:
- Confirm which module names are actually required by challenge variants and whether module activation has preconditions.

### Corrections

Cover:
- Delete records where deletion is supported
- Reverse vouchers where reversal is required

Relevant endpoints:
- `/travelExpense/{id}` delete
- `/department/{id}` delete
- `/project/{id}` delete
- `/customer/{id}` delete
- `/product/{id}` delete
- `/ledger/voucher/{id}/:reverse`

## Search And Resolution Rules

To preserve efficiency:
- Search only when a task depends on an existing entity.
- Use exact API-supported search params from the spec.
- Request only required fields.
- Reuse IDs returned from create calls instead of re-fetching.

Examples:
- Customer lookup should use `customerName` or another supported query param, not an invented `name` param.
- Invoice payment should use the dedicated payment endpoint rather than a generic update flow.

## Attachment Strategy

Support:
- PDF files
- Image files

Approach:
- Extract the minimum structured facts needed for the task.
- Feed extracted facts into the same `TaskPlan` pipeline.
- Avoid large attachment-to-prompt dumps when only a few fields are needed.

## Validation And Error Strategy

Principles:
- Validate locally before the first write.
- Avoid speculative writes.
- Treat 4xx responses as serious regressions.

Implementation rules:
- Normalize dates, amounts, booleans, and enum-like values before calling Tripletex.
- Map common validation failures into deterministic corrections where safe.
- Use at most one targeted recovery path for known validation issues.
- Fail fast rather than thrash if the task plan is low-confidence and ambiguous.

## Verification Strategy

Every workflow should define a minimal postcondition check.

Examples:
- After create: confirm returned entity shape includes the intended fields or IDs.
- After payment: verify invoice payment-related fields when practical.
- After reversal: verify the reverse call succeeded and returned a voucher payload.

Keep verification lean:
- One targeted verification read is acceptable for risky workflows.
- Avoid redundant GETs on simple successful creates.

## Delivery Milestones

### Milestone 1

Scaffold the submission service:
- FastAPI app
- Request/response models
- Tripletex client
- Logging
- Health/basic local run

### Milestone 2

Implement baseline high-frequency workflows:
- Customer creation
- Product creation
- Employee creation/update
- Project creation

### Milestone 3

Implement invoicing flows:
- Invoice creation
- Payment registration
- Credit note creation

### Milestone 4

Implement travel expense flows:
- Parent travel expense creation
- Child item creation
- Delete flow

### Milestone 5

Implement corrections and department/module flows:
- Delete/reverse handlers
- Department creation
- Module activation
- Entitlement template handling

### Milestone 6

Hardening and competition readiness:
- Regression tests
- Sandbox validation scripts
- Submission logging
- Efficiency-focused tuning

## Open Questions

- Which exact task variants require module activation, and which module names are accepted in practice?
- Which entitlement templates are needed for role-related employee tasks?
- Is direct `POST /invoice` creation more reliable than order-first creation in the real sandbox?
- Which travel-expense state transitions are required by the evaluator beyond object creation?
- What level of attachment OCR/vision is actually necessary for the challenge dataset?

## Immediate Next Step

Create the implementation skeleton inside `solutions/tripletex/`:
- service entrypoint
- typed request models
- Tripletex client
- `TaskPlan` schema
- first workflow handlers
