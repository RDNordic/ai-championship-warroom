# SESSION_HANDOFF.md

## Checkpoint

Tripletex now has live end-to-end coverage for the full baseline invoicing slice:

- invoice create
- invoice payment
- invoice credit note

This checkpoint confirmed invoice creation through the normal `scripts/run_prompt.py --execute ...` path and added deterministic payment and credit note workflows that are validated in the sandbox.

## Handoff Contract

- Current objective:
  - Stabilize the Tripletex baseline after the invoicing slice.
- Exact artifact reference:
  - Working tree on `2026-03-20` after live sandbox validation and focused tests.
  - Archived prior handoff: `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- What is proven:
  - `scripts/run_prompt.py` successfully created invoice `#3`, paid invoice `#3`, created invoice `#4`, and created credit note `#5` for invoice `#4`.
  - Focused tests pass for planner and live workflows, including the numeric invoice-id fallback case.
- What is assumed:
  - The challenge prompts will mostly reference invoice numbers, not internal Tripletex invoice IDs.
  - Defaulting invoice payments to the bank payment type is acceptable when the prompt does not specify a payment method.
- Next highest-priority task:
  - Live-validate employee creation, then move to travel expense workflows.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`

## Latest Work

- Confirmed invoice creation through the real local runner:
  - `./.venv/bin/python scripts/run_prompt.py --execute "Opprett en faktura ..."`
- Added new live workflows in `src/tripletex_agent/workflows/live.py` for:
  - invoice payment
  - invoice credit note
- Added invoice helpers for:
  - invoice lookup by invoice number with required date window
  - invoice payment type lookup via `/invoice/paymentType`
  - fallback from mistaken numeric invoice `id` lookups to invoice-number search when `GET /invoice/{id}` returns `404`
- Extended planner extraction for:
  - invoice payment
  - invoice credit note
  - payment date / amount / payment type hints
  - credit note date / comment
- Wired new workflows into:
  - `src/tripletex_agent/service.py`
  - `scripts/run_prompt.py`
  - workflow exports
- Updated README status to reflect the implemented invoicing slice.

## Validation

- Focused tests:
  - `./.venv/bin/pytest -q tests/test_app.py tests/test_config.py tests/test_models.py tests/test_planner.py tests/test_workflows.py`
  - Result: `22 passed`
- Changed-file lint:
  - `./.venv/bin/ruff check scripts/run_prompt.py src/tripletex_agent/planner.py src/tripletex_agent/service.py src/tripletex_agent/workflows/__init__.py src/tripletex_agent/workflows/live.py tests/test_planner.py tests/test_workflows.py`
  - Result: `All checks passed!`
- Live sandbox runner validations:
  - Invoice create:
    - Prompt: `Opprett en faktura for kunde Codex Test Kunde 20260320 med produkt Codex Test Produkt 20260320 antall 1 pris 500`
    - Result: invoice id `2147521961`, invoice number `3`, amount `625.0`
  - Invoice payment:
    - Prompt: `Register payment for invoice 3 payment date 2026-03-20 payment type Betalt til bank amount 625`
    - Result: invoice id `2147521961`, payment type id `33535763`, outstanding amount `0.0`
  - Credit-note validation create:
    - Prompt: `Opprett en faktura for kunde Codex Test Kunde 20260320 med produkt Codex Test Produkt 20260320 antall 1 pris 400`
    - Result: invoice id `2147521996`, invoice number `4`, amount `500.0`
  - Credit note:
    - Prompt: `Create credit note for invoice 4 date 2026-03-20 comment Codex credit validation`
    - Result: credit note id `2147522003`, invoice number `5`, source invoice id `2147521996`

## Important Sandbox Findings

- `GET /invoice` requires both:
  - `invoiceDateFrom`
  - `invoiceDateTo`
- Exact `invoiceNumber` search works when those dates are included.
- `PUT /invoice/{id}/:payment` uses query params, not JSON body:
  - `paymentDate`
  - `paymentTypeId`
  - `paidAmount`
  - optional `paidAmountCurrency`
- `PUT /invoice/{id}/:createCreditNote` also uses query params, not JSON body:
  - required `date`
  - optional `comment`
  - optional `creditNoteEmail`
  - `sendToCustomer` defaults to true in the API, so the workflow explicitly sends `false`
- Sandbox invoice payment types currently available:
  - `33535762` = `Kontant`
  - `33535763` = `Betalt til bank`
- The invoice bank account prerequisite from the prior checkpoint still applies:
  - invoice ledger account `1920` / id `431985679` needed `bankAccountNumber=12345678903`

## Notable Sandbox Records

- Customer: `108177116` (`Codex Test Kunde 20260320`)
- Product: `84382330` (`Codex Test Produkt 20260320`)
- Department: `869327`
- Project: `401951260` (`Codex Test Prosjekt 20260320`)
- Manual invoice probe: `2147520855` (invoice number `1`)
- Runner-confirmed invoice create: `2147521809` (invoice number `2`)
- Paid validation invoice: `2147521961` (invoice number `3`)
- Credited source invoice: `2147521996` (invoice number `4`)
- Credit note: `2147522003` (invoice number `5`)

## Known Issues / Risks

- Employee create exists but is still not live-validated in this sandbox during this session.
- Travel expense workflows are still not implemented.
- Correction workflows are still not implemented.
- OpenAI planning may still classify a bare numeric invoice reference as an internal ID in some prompts; the workflow fallback now covers that case, but more multilingual invoice-action examples would still help.
- Credit note flow currently supports the safe baseline path:
  - lookup existing invoice
  - create full credit note
  - do not send to customer
- `solutions/CloudRun.md` remains untouched.

## Next Steps

1. Live-validate employee creation through `scripts/run_prompt.py`.
2. Implement the first travel expense workflow slice.
3. Implement correction workflows.
4. Expand multilingual planner coverage for invoice payment and credit note phrasing.
5. Prepare deployment for the public `/solve` endpoint once the next live slice is stable.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md and solutions/tripletex/SESSION_HANDOFF.md. Resume from the validated invoicing checkpoint: live-validate employee creation through scripts/run_prompt.py, then implement the first travel expense workflow slice. Preserve session history by archiving the current handoff in solutions/tripletex/session_archive/ before replacing SESSION_HANDOFF.md again.
```
