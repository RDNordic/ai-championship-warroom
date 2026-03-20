# SESSION_HANDOFF.md

## Checkpoint

Tripletex now has a working public `/solve` endpoint, a reusable submission checklist, and a stronger baseline across the supported API-only slice:

- customer create
- product create
- employee create
- department create
- project create linked to an existing customer
- invoice create
- invoice payment
- invoice credit note

The first competition submission was a total failure. After the latest fixes, the baseline improved to `2 / 30` tasks solved. The latest visible task result passed `1 / 4` checks and failed `3 / 4`, which is still far from acceptable but confirms that the service can now reach and satisfy part of the scoring path.

Repository scope for the next session stays inside `solutions/tripletex/` unless the owner explicitly asks for something broader.

## Handoff Contract

- Current objective:
  - Strengthen the conversational prompt-to-API layer so the solver chooses and executes the correct deterministic Tripletex workflow across more prompt variants and task types.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after the first public `/solve` submission, employee-create fix, live endpoint logging, and submission-checklist addition.
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/docs.md`
- What is proven:
  - The public `/solve` endpoint is reachable over HTTPS and accepts the documented competition payload.
  - A public `/solve` request created a customer in the sandbox and later created employee `18562422`.
  - `scripts/run_prompt.py --execute` now live-validates employee creation after adding the required employee fields.
  - Focused tests and lint pass for the current baseline workflows and logging changes.
- What is assumed:
  - The move from `0 / 30` to `2 / 30` is mainly limited by unsupported or weakly interpreted task variants, not by endpoint reachability.
  - PDF and CSV handling can stay lower priority while we improve API-only prompt interpretation and workflow selection.
- Next highest-priority task:
  - Build a stronger prompt-to-API bot for API-only tasks before investing further in attachment handling.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`

## Latest Work

- Added a reusable checklist in `solutions/tripletex/SUBMISSION_CHECKLIST.md` for sandbox validation, local runner checks, and full `/solve` contract replay.
- Confirmed that the public Cloudflare-backed `/solve` endpoint receives real external requests from the competition platform.
- Added request, plan, workflow, and result logging in the service layer so the next failed submission is not a black box.
- Updated the stub workflow to log when unsupported tasks quietly fall back to a no-op path.
- Fixed employee creation by resolving the required default department and sending a valid `userType`.
- Live-validated employee creation both through `scripts/run_prompt.py --execute` and through the public `/solve` endpoint.

## Validation

- Focused tests:
  - `./.venv/bin/pytest -q tests/test_app.py tests/test_config.py tests/test_models.py tests/test_planner.py tests/test_workflows.py`
  - Result: `23 passed`
- Changed-file lint:
  - `./.venv/bin/ruff check src/tripletex_agent/app.py src/tripletex_agent/config.py src/tripletex_agent/service.py src/tripletex_agent/workflows/live.py src/tripletex_agent/workflows/stub.py tests/test_workflows.py`
  - Result: `All checks passed!`
- Live sandbox runner validations:
  - `python scripts/smoke_read_only.py`
    - Result: read-only sandbox access succeeded
  - `./.venv/bin/python scripts/run_prompt.py --execute "Create employee named Codex Employee20260320B, email codex.employee20260320b@acme.test"`
    - Result: employee id `18562413`
- Public `/solve` validations:
  - Customer create via public endpoint
    - Result: customer id `108240330`, `Codex Public Kunde 20260320-public-1`
  - Employee create via public endpoint
    - Result: employee id `18562422`, `Codex PublicEmployee 20260320-public-employee-1`
- Competition signal:
  - First submission: `0 / 30`
  - Latest submission after fixes: `2 / 30`
  - Latest visible task card: `1 / 4` checks passed, `3 / 4` failed

## Important Sandbox Findings

- `GET /invoice` requires both:
  - `invoiceDateFrom`
  - `invoiceDateTo`
- Exact `invoiceNumber` search works when those dates are included.
- `PUT /invoice/{id}/:payment` uses query params, not JSON body.
- `PUT /invoice/{id}/:createCreditNote` uses query params, not JSON body, and should explicitly send `sendToCustomer=false`.
- Employee creation requires more than first name, last name, and email:
  - valid `userType`
  - `department.id`
- The verified minimal employee create path currently works with:
  - `userType=NO_ACCESS`
  - default department id `854238`
- Unsupported tasks currently risk returning HTTP 200 through `StubWorkflow` while scoring zero, so unsupported-plan detection must remain visible in logs.

## Notable Sandbox Records

- Customer: `108240330` (`Codex Public Kunde 20260320-public-1`)
- Employee from local runner: `18562413` (`Codex Employee20260320B`)
- Employee from public `/solve`: `18562422` (`Codex PublicEmployee 20260320-public-employee-1`)
- Department used for employee creation: `854238`
- Paid validation invoice: `2147521961` (invoice number `3`)
- Credited source invoice: `2147521996` (invoice number `4`)
- Credit note: `2147522003` (invoice number `5`)

## Known Issues / Risks

- The current implemented workflow slice is still too narrow for the competition task spread, which likely explains the `2 / 30` ceiling so far.
- Travel expense workflows are still unimplemented.
- Correction workflows are still unimplemented.
- Attachment extraction for PDF and CSV is still deferred.
- Unsupported tasks can still appear “successful” at the HTTP level if they hit `StubWorkflow`.
- Planner coverage is still weaker than needed for broad conversational prompts and multilingual variants.
- `solutions/CloudRun.md` remains untouched.

## Next Steps

1. Use `solutions/tripletex/SUBMISSION_CHECKLIST.md` as the required gate before every new competition submission.
2. Build a stronger prompt-to-API bot for API-only tasks: better task classification, field extraction, entity lookup, and workflow selection from conversational prompts.
3. Expand deterministic workflow coverage across existing API-only areas before touching attachments again.
4. Reduce silent `StubWorkflow` dependence by replacing stubs with real handlers and watching logs for unsupported plans.
5. Implement the first travel expense workflow slice after the API-only bot is materially stronger.
6. Keep PDF and CSV handling lower priority until the prompt-to-API baseline stops failing obvious non-attachment tasks.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, and solutions/tripletex/SESSION_HANDOFF.md. Stay scoped to solutions/tripletex/. Use the checklist to validate API-only scenarios in the sandbox and through a full `/solve` replay. Focus on strengthening the conversational prompt-to-API layer so the solver can choose and execute the correct Tripletex workflows for more prompt variants. Keep PDF and CSV handling lower priority unless a concrete task requires them. Preserve session history by archiving the current handoff in solutions/tripletex/session_archive/ before replacing SESSION_HANDOFF.md again.
```
