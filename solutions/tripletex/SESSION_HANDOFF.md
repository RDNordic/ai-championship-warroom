# SESSION_HANDOFF.md

## Checkpoint

Tripletex has moved well beyond scaffold status. The solver now has real live workflows for customer, product, department, project, and invoice creation, plus a structured planner stack with OpenAI-first extraction and keyword fallback.

The most important architectural change in this session is that invoicing is now viable in a fresh sandbox because we discovered and handled an account-level prerequisite: Tripletex cannot create invoices until an invoice bank account number is configured on the existing ledger bank account.

## Session Archive

- Previous handoff preserved at `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`

## Latest Work

- Added environment/config support and local smoke tooling:
  - `src/tripletex_agent/config.py`
  - `scripts/smoke_read_only.py`
  - `.env.example`
- Replaced the scaffold planner with:
  - `OpenAIPlanner`
  - `KeywordTaskPlanner`
  - `FallbackPlanner`
- Extended planner extraction for:
  - customer
  - product
  - employee
  - department
  - project
  - invoice create
- Added real workflows in `src/tripletex_agent/workflows/live.py` for:
  - customer create
  - product create
  - employee create
  - department create
  - project create
  - invoice create
- Wired live workflows into:
  - `service.py`
  - `scripts/run_prompt.py`
  - workflow exports
- Added better local diagnostics:
  - `scripts/run_prompt.py` now prints Tripletex error payloads instead of only stack traces
- Added focused tests for config, planner behavior, and live workflow payloads

## Validation

- Focused test slice passes:
  - `./.venv/bin/pytest -q tests/test_app.py tests/test_config.py tests/test_models.py tests/test_planner.py tests/test_workflows.py`
  - Result: `17 passed`
- Live sandbox validations completed successfully for:
  - customer create
  - department create
  - project create
  - product create
- Manual live invoice probe succeeded after configuring the invoice bank account:
  - direct `POST /invoice` with embedded order and order line returned a real invoice
- Read-only auth smoke test succeeded against the sandbox with `Basic 0:<session_token>`

## Important Sandbox Findings

- Fresh sandbox bank ledger accounts existed, but the invoice account had an empty `bankAccountNumber`
- The existing invoice ledger account was:
  - account number `1920`
  - id `431985679`
- Setting `bankAccountNumber=12345678903` on `/ledger/account/431985679` unlocked invoice creation
- Minimum working invoice shape discovered in the sandbox:
  - top-level `invoiceDate`
  - top-level `invoiceDueDate`
  - top-level `customer`
  - embedded `orders[0].customer`
  - embedded `orders[0].orderDate`
  - embedded `orders[0].deliveryDate`
  - embedded `orders[0].orderLines[0]`

## Notable Created Sandbox Records

- Customer: `108177116` (`Codex Test Kunde 20260320`)
- Department: `869327`
- Product: `84382330` (`Codex Test Produkt 20260320`)
- Project: `401951260` (`Codex Test Prosjekt 20260320`)
- Manual invoice probe: `2147520855`

## Known Issues / Risks

- Invoice create is implemented and unit-tested, but the end-to-end `scripts/run_prompt.py --execute ...` invoice run was interrupted by the user before result capture, so the workflow itself still deserves one final live confirmation through the normal runner path.
- Invoice payment and credit note workflows are still not implemented.
- Travel expense workflows are still not implemented.
- Correction workflows are still not implemented.
- Employee create exists, but it has not yet been live-validated in this sandbox during this session.
- OpenAI planning sometimes falls back because of connection issues; keyword fallback remains important.
- `solutions/CloudRun.md` is user-created/unrelated and should not be touched unless requested.

## Next Steps

1. Re-run one end-to-end invoice creation through `scripts/run_prompt.py --execute ...` to confirm the implemented workflow matches the manual probe.
2. Implement invoice payment:
   - invoice lookup
   - payment type lookup
   - `PUT /invoice/{id}/:payment`
3. Implement credit note creation:
   - invoice lookup
   - `PUT /invoice/{id}/:createCreditNote`
4. Live-validate employee creation.
5. Update README status to reflect that customer/product/project/invoice create are now implemented.
6. Prepare deployment path for the public `/solve` endpoint after the next workflow slice is stable.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md and solutions/tripletex/SESSION_HANDOFF.md. Resume from the live-workflow checkpoint: confirm invoice creation through scripts/run_prompt.py, then implement and validate invoice payment and credit note flows. Preserve session history by archiving old handoffs in solutions/tripletex/session_archive/ before replacing SESSION_HANDOFF.md.
```
