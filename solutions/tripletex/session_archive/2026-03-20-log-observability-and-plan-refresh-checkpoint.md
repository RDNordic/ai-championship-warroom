# SESSION_HANDOFF.md

## Checkpoint

Tripletex now has a materially stronger conversational prompt-to-API layer for the currently supported API-only slice, plus fresh live validation through both direct sandbox workflows and a real public `/solve` replay.

This session focused on making supported workflows safer under broader English/Norwegian phrasing instead of expanding attachments or new task families. The biggest change is that supported plans are now stabilized after LLM extraction: invalid or suspicious fields are sanitized, and the deterministic keyword planner is merged back in to clean up supported create/payment/credit-note prompts before execution.

Repository scope for the next session stays inside `solutions/tripletex/` unless the owner explicitly asks for something broader.

## Handoff Contract

- Current objective:
  - Keep expanding and validating the prompt-to-API layer across supported API-only workflows so conversational prompt variants map to the correct deterministic Tripletex workflow with fewer mis-parsed fields and fewer silent stub hits.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after planner cleanup, fallback-plan merging, sandbox validation of conversational prompts, and a successful public `/solve` replay against `https://app-per-formerly-basement.trycloudflare.com/solve`.
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/docs.md`
- What is proven:
  - Focused tests and lint pass after the planner changes.
  - Sandbox read-only access still works.
  - A conversational customer-create prompt succeeded in the sandbox.
  - A conversational invoice-create prompt with a free-text line description succeeded in the sandbox.
  - A Norwegian conversational invoice-payment prompt succeeded in the sandbox.
  - A real public `POST /solve` request returned HTTP `200` with `{"status":"completed"}` and the created customer was verified afterward in the sandbox by email lookup.
- What is assumed:
  - The main remaining ceiling is still prompt/task coverage and unsupported workflow families, not the core `/solve` contract.
  - The OpenAI planner may remain somewhat nondeterministic, but the new cleanup/merge layer should make supported workflows safer.
  - PDF and CSV handling can still stay lower priority until the API-only prompt layer covers more of the scorer’s obvious prompt variants.
- Next highest-priority task:
  - Build a prompt-coverage matrix for the supported API-only workflows and keep live-validating each variant family through sandbox runner plus public `/solve` replay before the next competition submission.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-conversational-prompt-layer-checkpoint.md`

## Latest Work

- Expanded keyword intent detection for supported employee, customer, product, department, project, invoice, payment, and credit-note prompt variants.
- Broadened deterministic field extraction for:
  - customer name/email/language
  - employee name/number/mobile
  - department number
  - project number/start date/project-manager details
  - invoice customer lookup, invoice comment, free-text line description, quantity, unit price
  - invoice payment phrasing such as `Betal faktura #6 ... via Betalt til bank`
- Added a cleanup/merge layer in the planner path:
  - sanitize invalid `organizationNumber` values from LLM extraction
  - merge supported-plan fields from the deterministic fallback planner even when the OpenAI planner succeeds
  - replace suspicious/truncated name fields with cleaner deterministic values
  - drop hallucinated invoice-line `productLookup` values when the prompt is clearly a free-text description line
- Added focused planner tests for the broader prompt variants and for the new fallback-merge behavior.

## Validation

- Focused tests:
  - `./.venv/bin/pytest -q tests/test_app.py tests/test_models.py tests/test_planner.py tests/test_workflows.py`
  - Result: `30 passed`
- Changed-file lint:
  - `./.venv/bin/ruff check src/tripletex_agent/planner.py tests/test_planner.py`
  - Result: `All checks passed!`
- Live sandbox runner validations:
  - `./.venv/bin/python scripts/smoke_read_only.py`
    - Result: read-only sandbox access succeeded
  - `./.venv/bin/python scripts/run_prompt.py --execute "Add customer named Codex Conversational Kunde 20260320-B and email conversational-20260320-b@acme.test organization number 123 456 789 language English"`
    - Result: customer id `108240985`
  - `./.venv/bin/python scripts/run_prompt.py --execute "Issue invoice for customer Codex Conversational Kunde 20260320-B line description Conversational validation qty 2 unit price 1500 invoice comment Phase 1"`
    - Result: invoice id `2147523008`, invoice number `6`, amount `3000.0`
  - `./.venv/bin/python scripts/run_prompt.py --execute "Betal faktura #6 betalingsdato 2026-03-20 betalt beløp 3000 via Betalt til bank"`
    - Result: invoice `6` paid successfully, amount outstanding `0.0`
- Public `/solve` validation:
  - Real public replay against `https://app-per-formerly-basement.trycloudflare.com/solve`
    - Prompt: `Add customer named Codex Solve Replay Kunde 20260320-C and email solve-replay-20260320-c@acme.test language English`
    - Result: HTTP `200`, body `{"status":"completed"}`
  - Manual sandbox verification after public replay:
    - Email lookup for `solve-replay-20260320-c@acme.test`
    - Result: customer id `108241089`, name `Codex Solve Replay Kunde 20260320-C`, language `EN`
- Local `/solve` log replay:
  - Tried to hit a local `uvicorn` instance on `127.0.0.1:8012`
  - Result: sandbox loopback restriction (`[Errno 1] Operation not permitted`) blocked the local HTTP call, so this did not provide additional evidence about app behavior

## Important Findings

- The OpenAI planner can still return a supported task with slightly wrong structured fields; relying on it alone is too brittle for efficiency-sensitive scoring.
- Merging deterministic extraction back into supported LLM plans fixed a real live failure:
  - before cleanup, a conversational invoice prompt was parsed as:
    - `customerName = "Codex Conversational Kunde"`
    - `organizationNumber = "20260320-B"`
  - after cleanup, the same prompt was stabilized to:
    - `customerName = "Codex Conversational Kunde 20260320-B"`
    - no invalid organization number
- Free-text invoice line prompts can trigger hallucinated product lookups unless explicitly cleaned. The new merge logic now drops that conflicting `productLookup` when the deterministic parser says the line is descriptive text.
- Earlier live Tripletex findings still matter:
  - `GET /invoice` requires `invoiceDateFrom` and `invoiceDateTo`
  - invoice payment and credit-note endpoints use query params, not JSON bodies
  - employee creation still requires valid `userType` plus `department.id`
  - unsupported tasks can still return HTTP `200` if they hit `StubWorkflow`

## Notable Sandbox Records

- Customer from conversational runner validation: `108240985` (`Codex Conversational Kunde 20260320-B`)
- Invoice from conversational description-line validation: `2147523008` (invoice number `6`)
- Customer from public `/solve` replay: `108241089` (`Codex Solve Replay Kunde 20260320-C`)
- Department used for employee creation baseline: `854238`
- Paid validation invoice from earlier session: `2147521961` (invoice number `3`)
- Credited source invoice from earlier session: `2147521996` (invoice number `4`)
- Credit note from earlier session: `2147522003` (invoice number `5`)

## Known Issues / Risks

- Travel expenses are still unimplemented.
- Correction workflows are still unimplemented.
- Module-activation workflows are still unimplemented.
- PDF and CSV extraction are still deferred.
- Planner coverage is improved but still not broad enough across all competition prompt variants or all supported languages.
- Unsupported tasks can still score zero behind an HTTP `200` if they fall through to `StubWorkflow`.
- The competition baseline is still the earlier `2 / 30` result; no new public competition submission was made after these prompt-layer changes.
- Public endpoint logs were not inspected from this workspace during this session; the public replay only proved response shape plus downstream sandbox effect.

## Next Steps

1. Use `solutions/tripletex/SUBMISSION_CHECKLIST.md` as the required gate before every new competition submission.
2. Build a prompt-coverage matrix for the supported workflows and validate at least:
   - fresh create scenario
   - existing-entity lookup scenario
   - English phrasing
   - Norwegian phrasing
3. Extend the same prompt cleanup approach to remaining supported API-only workflows, especially:
   - project create variants
   - employee create variants
   - customer/product variants with more labeled fields
   - invoice credit-note variants
4. Keep reducing `StubWorkflow` exposure before investing in attachments again.
5. Only resume PDF/CSV work after the API-only prompt baseline stops failing obvious conversational variants.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, and solutions/tripletex/SESSION_HANDOFF.md. Stay scoped to solutions/tripletex/. Continue strengthening the conversational prompt-to-API layer for the supported API-only workflows, using the checklist as the gate. Prefer live sandbox validation plus a public /solve replay for each prompt family you improve. Keep PDF and CSV handling lower priority unless a concrete task requires them. Preserve session history by archiving the current handoff in solutions/tripletex/session_archive/ before replacing SESSION_HANDOFF.md again.
```
