# Tripletex Implementation Plan

**Status:** Evidence-updated working plan
**Last updated:** 2026-03-20
**Owner:** KO

## Purpose

Keep a current, evidence-backed plan for the Tripletex challenge.

This document started as a baseline architecture plan. It is now also the place where we merge live solver evidence, hidden-task observations, and concrete implementation priorities so the next coding session is guided by real scorer behavior instead of assumptions.

## Source Baseline

Primary sources used:
- Official challenge docs on `app.ainm.no`
- Tripletex OpenAPI spec (`openapi.json`, version `2.74.00`)
- Repository challenge brief in `solutions/tripletex/README.md`
- Submission gate in `solutions/tripletex/SUBMISSION_CHECKLIST.md`
- Live solver traces in `solutions/tripletex/logs/solve-events.jsonl`

Secondary sources used with caution:
- Local scratch notes in `tripletex_task.md`
- Local external report in `comprehensive_report.md`

Rule for this project:
- When external notes conflict with the official docs, the official docs and spec win.
- When design intent conflicts with live trace evidence, the live trace evidence wins for prioritization.

## Current Evidence Snapshot

Current live log sample on 2026-03-20:
- `2` traced `/solve` requests
- `1` internal probe
- `1` real competition prompt

Evidence limits:
- The sample is small and not yet representative across all 30 task types.
- It is already large enough to identify one critical semantic gap: the agent can correctly interpret an invoice-create prompt but still miss a scorer-relevant action nuance such as "send".

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
- Hidden competition prompts are now observable from solver-side logs, which means future planning can be grounded in real prompt phrasing instead of only synthetic tests.

## Log-Derived Prompt Taxonomy

### Internal Probes

1. Customer create probe
   - Trace: `4d8fdcf5-fe90-4ed9-8d75-4366bbea189c`
   - Prompt: `Add customer named Codex Logging Probe 20260320-F and email logging-probe-20260320-f@acme.test language English`
   - Why this is internal:
     - sandbox base URL `https://kkpqfuj-amager.tripletex.dev/v2`
     - synthetic `Codex Logging Probe` name
     - known local validation pattern

### Real Competition Prompt

1. French invoice-create-and-send task
   - Trace: `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
   - Prompt: `Créez et envoyez une facture au client Lumière SARL (nº org. 827689114) de 8750 NOK hors TVA. La facture concerne Maintenance.`
   - Why this is competition traffic:
     - ephemeral challenge proxy base URL `https://tx-proxy-jwanbnu3pq-lz.a.run.app/v2`
     - request metadata matches public competition flow
     - not shaped like an internal validation prompt

## Prompt-By-Prompt Assessment

### Prompt 1: Internal Customer Create Probe

Raw prompt:
- `Add customer named Codex Logging Probe 20260320-F and email logging-probe-20260320-f@acme.test language English`

Planned TaskPlan/workflow:
- `task_family=customers_products`
- `operation=create`
- `workflow=CustomerCreateWorkflow`
- extracted fields: `name`, `email`, `language=EN`

Actual API sequence:
- `POST /customer`

Semantic assessment:
- Strong solve.
- The plan and execution match the human request closely.
- No obvious missing fields, no extra reads, and no speculative side effects.

Likely scoring impact:
- High confidence for correctness and efficiency on this prompt shape.

### Prompt 2: Competition French Invoice Create-And-Send Task

Raw prompt:
- `Créez et envoyez une facture au client Lumière SARL (nº org. 827689114) de 8750 NOK hors TVA. La facture concerne Maintenance.`

Planned TaskPlan/workflow:
- `task_family=invoicing`
- `operation=create`
- `workflow=InvoiceCreateWorkflow`
- extracted fields:
  - `customerLookup.customerName = "Lumière SARL"`
  - `customerLookup.organizationNumber = "827689114"`
  - line description `Maintenance`
  - line unit price excluding VAT `8750.0`
  - quantity `1.0`

Actual API sequence:
- `GET /customer`
- `GET /ledger/account`
- `PUT /ledger/account/{id}`
- `POST /invoice` with `sendToCustomer=false`

Semantic assessment:
- Partial solve.
- Positive:
  - multilingual prompt understanding succeeded
  - customer resolution succeeded
  - amount and VAT-excluding phrasing were preserved correctly in the invoice line
  - no 4xx errors occurred
- Negative:
  - the prompt explicitly asked to "create and send" the invoice
  - execution created the invoice but explicitly disabled sending with `sendToCustomer=false`
  - the workflow introduced unrelated bank-account configuration side effects not requested by the prompt
  - the postcondition only proves invoice creation, not sending/delivery

Likely scoring impact:
- Likely partial credit at best if the hidden check included "sent to customer" semantics.
- Efficiency bonus is also weakened by the extra `GET /ledger/account` and `PUT /ledger/account/{id}`.

## Findings Ordered By Severity

### P0: Invoice send intent is not represented end-to-end

Evidence:
- Competition prompt says `Créez et envoyez une facture...` in [solve-events.jsonl:5](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/logs/solve-events.jsonl#L5)
- planner produced plain invoice create with no send flag in [solve-events.jsonl:6](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/logs/solve-events.jsonl#L6)
- workflow hardcodes `sendToCustomer=False` in [live.py:168](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/workflows/live.py#L168)
- keyword invoice intent maps `send invoice` into generic create only in [planner.py:248](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/planner.py#L248)

Implication:
- The agent can understand a prompt well enough to create the right entity while still failing a scorer check on action semantics.

### P0: Multilingual action semantics are weaker than multilingual extraction

Evidence:
- planner system prompt claims support for French, German, Portuguese, Spanish, Nynorsk, Bokmal, and English in [planner.py:845](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/planner.py#L845)
- keyword fallback rules are still heavily English/Norwegian-centric in [planner.py:189](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/planner.py#L189)
- the French competition prompt only succeeded because the OpenAI-backed extraction carried the semantics far enough

Implication:
- Current multilingual coverage is real but fragile.
- The fallback layer does not yet stabilize high-value action semantics across all declared languages.

### P1: Invoice create performs unrequested bank-account mutation

Evidence:
- competition trace includes `GET /ledger/account` then `PUT /ledger/account/{id}` in [solve-events.jsonl:8](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/logs/solve-events.jsonl#L8) and [solve-events.jsonl:9](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/logs/solve-events.jsonl#L9)
- workflow mutates the invoice bank account when empty in [live.py:804](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/workflows/live.py#L804)

Implication:
- This may be acceptable as a sandbox bootstrap tactic, but it is risky and inefficient for hidden competition tasks.
- It increases API count and adds a side effect unrelated to the user prompt.

### P1: Postconditions prove creation, not requested business outcome

Evidence:
- current invoice completion check only expects created invoice fields and IDs in [solve-events.jsonl:6](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/logs/solve-events.jsonl#L6)

Implication:
- The solver can say `completed` even when a scorer-relevant nuance like "send", "approve", or "deliver" was not executed.

### P2: Prompt-pattern analysis currently over-collapses important fields

Evidence:
- the normalization rules at [log_analysis.py:21](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/log_analysis.py#L21) replace long spans after markers like `named`
- this turned the internal probe into a pattern that lost email and language details

Implication:
- The current log-analysis helper is already useful for clustering, but not yet good enough for planner-improvement work on nuanced prompt variants.

## Core Strategy

Build a constrained LLM planner with deterministic workflow handlers, and use live logs to continuously tighten the gap between what the user asked and what the workflow actually did.

Why:
- A free-form agent that invents raw API calls is too likely to incur 4xx penalties.
- The task distribution is broad, but the execution patterns are repetitive enough to encode safely in code.
- Correctness and efficiency both improve when search, validation, and write logic are explicit.
- Live prompt traces now give us a feedback loop for hidden task phrasing and semantic misses.

## Updated Target Architecture

```text
POST /solve
  -> request validation
  -> attachment normalization
  -> structured task extraction
  -> semantic intent flags (send, approve, deliver, reverse, etc.)
  -> deterministic workflow selection
  -> Tripletex API execution
  -> targeted verification of requested outcome
  -> durable trace logging
  -> {"status": "completed"}
```

Main components:
- `app.py` FastAPI entrypoint
- request/response models
- Tripletex API client with auth, retries, and helper methods
- structured `TaskPlan` schema for LLM output
- workflow handlers per task family
- attachment extraction layer
- logging and trace analysis suitable for debugging submission failures and mining prompt variants

## LLM Role

The model should not decide arbitrary endpoint paths.

The model should do:
- multilingual understanding
- attachment interpretation
- entity extraction
- field extraction
- task-family classification
- semantic action extraction such as send/pay/credit/reverse
- reference resolution hints
- confidence signaling

The model should not do:
- free-form API sequencing
- trial-and-error discovery in production
- unbounded tool use

## Task Model Adjustments Needed

The internal `TaskPlan` already captures:
- `task_family`
- `operation`
- `entities_to_create`
- `entities_to_find`
- `fields_to_set`
- `links_between_entities`
- `attachment_facts`
- `completion_checks`
- `confidence`

The next revision should explicitly carry workflow-relevant action flags and delivery intent, for example:
- invoice `sendToCustomer`
- invoice delivery channel or send preference when stated
- approval or delivery transitions for multi-step workflows
- stronger completion checks tied to the requested action, not only entity creation

## Workflow Families

### Employees

Cover:
- create employee
- update employee
- create employment when employment-specific fields are required
- apply entitlement template when the task is about roles/access

Relevant endpoints:
- `/employee`
- `/employee/{id}`
- `/employee/employment`
- `/employee/entitlement`
- `/employee/entitlement/:grantEntitlementsByTemplate`

### Customers And Products

Cover:
- create customer
- update customer
- create product
- update product if needed by task variants

Relevant endpoints:
- `/customer`
- `/customer/{id}`
- `/product`
- `/product/{id}`

### Invoicing

Cover:
- create invoice
- create and send invoice
- register payment
- create credit note

Default approach:
- prefer the shortest reliable path after sandbox validation
- keep direct `POST /invoice` for invoice creation when it is semantically sufficient
- treat "create invoice" and "create and send invoice" as different execution shapes even if both start with invoice creation
- remove or isolate automatic bank-account mutation unless it is strictly required for a known environment bootstrap
- keep an order-first fallback available if direct invoice creation proves fragile

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
- create travel expense report
- delete travel expense report
- potentially complete delivery/approval transitions if required by the verifier

Important design note:
- treat travel expenses as parent plus child resources, not as a single flat payload

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
- create project linked to customer
- update project if variants require edits

Relevant endpoints:
- `/project`
- `/project/{id}`

### Departments And Modules

Cover:
- create department
- enable relevant accounting/sales modules if the task requires it

Relevant endpoints:
- `/department`
- `/department/{id}`
- `/company/salesmodules`

Open verification task:
- confirm which module names are actually required by challenge variants and whether module activation has preconditions

### Corrections

Cover:
- delete records where deletion is supported
- reverse vouchers where reversal is required

Relevant endpoints:
- `/travelExpense/{id}` delete
- `/department/{id}` delete
- `/project/{id}` delete
- `/customer/{id}` delete
- `/product/{id}` delete
- `/ledger/voucher/{id}/:reverse`

## Search And Resolution Rules

To preserve efficiency:
- search only when a task depends on an existing entity
- use exact API-supported search params from the spec
- request only required fields
- reuse IDs returned from create calls instead of re-fetching
- do not mutate unrelated system configuration during business-task execution unless that is the smallest safe path and is explicitly justified by validation evidence

Examples:
- customer lookup should use `customerName` or another supported query param, not an invented `name` param
- invoice payment should use the dedicated payment endpoint rather than a generic update flow

## Attachment Strategy

Support:
- PDF files
- image files

Approach:
- extract the minimum structured facts needed for the task
- feed extracted facts into the same `TaskPlan` pipeline
- avoid large attachment-to-prompt dumps when only a few fields are needed

Priority rule:
- API-only prompt handling still comes first
- PDF and CSV extraction remain lower priority until the prompt-to-API path is stable for supported live workflows

## Validation And Error Strategy

Principles:
- validate locally before the first write
- avoid speculative writes
- treat 4xx responses as serious regressions
- treat semantic mismatches without 4xx responses as equally serious if they can fail scorer checks

Implementation rules:
- normalize dates, amounts, booleans, and enum-like values before calling Tripletex
- map common validation failures into deterministic corrections where safe
- use at most one targeted recovery path for known validation issues
- fail fast rather than thrash if the task plan is low-confidence and ambiguous
- log enough context to compare the human prompt, extracted plan, API sequence, and result

## Verification Strategy

Every workflow should define a minimal postcondition check tied to the requested outcome.

Examples:
- after create: confirm returned entity shape includes the intended fields or IDs
- after create-and-send invoice: confirm the invoice was created and sent, not only created
- after payment: verify invoice payment-related fields when practical
- after reversal: verify the reverse call succeeded and returned a voucher payload

## Merged P0 / P1 / P2 Plan

### P0: Close the semantic gap between prompt intent and workflow execution

Goal:
- Ensure action words in the human prompt survive extraction and materially change execution.

Immediate work:
- add invoice send intent to planner schema and plan payloads
- add multilingual extraction for send/deliver semantics across `nb`, `nn`, `en`, `es`, `pt`, `de`, `fr`
- make `InvoiceCreateWorkflow` honor send intent instead of always using `sendToCustomer=false`
- add completion checks that distinguish "invoice created" from "invoice created and sent"

Expected impact:
- Higher correctness on hidden invoicing tasks
- Fewer silent partial solves that still return HTTP `200`

Tests:
- planner tests for `create invoice` vs `create and send invoice`
- workflow tests that assert request params/body differ when send intent is present
- bilingual and multilingual prompt fixtures for each supported send phrase family

Validation commands:
- `./.venv/bin/pytest -q tests/test_planner.py tests/test_workflows.py`
- `./.venv/bin/python scripts/run_prompt.py --execute "<multilingual invoice send prompt>"`
- public `/solve` replay followed by log inspection and sandbox verification

### P1: Reduce unnecessary side effects and API cost

Goal:
- Preserve efficiency bonus and reduce risk from unrelated writes.

Immediate work:
- re-evaluate whether invoice creation really requires bank-account bootstrap during normal task execution
- move bank-account bootstrap to an explicit environment-prep path if possible
- add regression tests for minimal invoice-create API sequences

Expected impact:
- Fewer extra calls
- Lower risk of hidden-account drift
- Better efficiency bonus potential on perfect solves

Tests:
- workflow tests asserting no ledger-account mutation on already-usable environments
- live sandbox checks comparing API sequence before and after change

Validation commands:
- `./.venv/bin/pytest -q tests/test_workflows.py`
- `./.venv/bin/python scripts/inspect_solve_logs.py trace <trace_id>`

### P2: Improve log analysis so prompt mining is useful for planner tuning

Goal:
- Turn logs into a reliable map of common prompt shapes and misses.

Immediate work:
- refine normalization so fields like email, language, org number, VAT wording, and send intent remain visible as structured signal
- distinguish internal probes from competition prompts in summaries
- add pattern reports grouped by workflow, outcome, and semantic flags

Expected impact:
- Faster identification of real hidden-task clusters
- Better prioritization of prompt-coverage work

Tests:
- unit tests for normalization and prompt clustering
- CLI checks against the real JSONL log

Validation commands:
- `./.venv/bin/pytest -q tests/test_log_analysis.py`
- `./.venv/bin/python scripts/inspect_solve_logs.py recent --limit 20`
- `./.venv/bin/python scripts/inspect_solve_logs.py patterns --top 20`
- `./.venv/bin/python scripts/inspect_solve_logs.py patterns --outcome failed --top 20`

## Specific Code-Change Recommendations

Planner schema and extraction:
- extend invoice extraction and/or entity payload fields to carry `sendToCustomer`
- add multilingual "send invoice" phrasing to the deterministic planner layer, not only the LLM prompt
- add extraction coverage for French phrases like `envoyez`, German send equivalents, Spanish `enviar`, Portuguese `enviar`, and Nynorsk variants
- keep explicit separation between entity type, operation, and secondary action flags

Workflow execution:
- update `InvoiceCreateWorkflow` to branch on send intent
- stop hardcoding `sendToCustomer=False` for every invoice-create path
- review whether any follow-up verification API call is needed to prove sent status without bloating efficiency

Logging and trace analysis:
- enrich trace summaries with a competition-vs-probe label
- preserve prompt cues such as email, language, org number, VAT wording, and send intent in normalized prompt patterns
- add reports that compare requested action words against executed workflow flags

Regression coverage:
- add tests built directly from logged competition prompts
- treat each hidden prompt pattern as a future regression fixture once understood

## Checklist-Driven Validation Rule

Before every public competition submission:
1. Verify sandbox read-only access.
2. Validate raw API behavior for the workflow in question.
3. Validate the workflow via local runner.
4. Validate the full `/solve` path against the public endpoint with sandbox credentials.
5. Verify exact resulting fields in Tripletex.
6. Inspect logs to confirm semantic alignment, not only HTTP success.
7. Submit only after the exact scenario has passed all earlier gates.

## Immediate Next Session Focus

1. Implement invoice send intent end-to-end.
2. Remove or isolate invoice bank-account mutation from normal invoice-create runs.
3. Add multilingual send-intent planner tests derived from the logged French prompt.
4. Improve prompt normalization and trace labeling so future logs immediately show prompt families and failure clusters.
5. Re-run the checklist with fresh sandbox validations and another public `/solve` replay before the next competition submit.
