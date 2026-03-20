# SESSION_HANDOFF.md

## Checkpoint

Tripletex still preserves the validated invoice create-and-send semantics, and this session tightened the next live weakness from the public traces:
- amount/VAT phrasing is now pruned away from invoice `comment` / `invoiceComment` when it only duplicates the extracted invoice amount
- French description-line prompts are explicitly protected from drifting into `productLookup`
- the public `/solve` path was revalidated after restarting the local `uvicorn` worker, so the new replay reflects current code instead of stale in-memory behavior

This session started from the earlier successful replay trace `251c548b-91a7-4c52-8e1b-7f70040c2ca2` and the old competition miss `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`.

The new public replay trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a` is the current source-of-truth checkpoint:
- `action_semantics.send_to_customer=true`
- no `productLookup` drift
- no amount/VAT phrase stored as invoice comment
- `POST /invoice` still uses `sendToCustomer=true`

Repository scope for the next session stays inside `solutions/tripletex/` unless the owner explicitly asks for broader work.

## Handoff Contract

- Current objective:
  - Keep the live invoice send path stable while continuing to harden invoice extraction against planner drift, using public `/solve` traces as the main source of truth.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after:
    - invoice comment pruning for redundant amount/VAT phrases
    - stronger invoice extraction instructions for free-text description lines vs product references
    - trace-specific regression tests for the stale-worker product hallucination and the successful replay comment drift
  - Public endpoint:
    - `https://app-per-formerly-basement.trycloudflare.com/solve`
  - Local service note:
    - the `uvicorn` worker on `127.0.0.1:8011` was restarted during this session before the public replay so the tunnel served current code
  - Live trace log path:
    - `solutions/tripletex/logs/solve-events.jsonl`
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/SESSION_HANDOFF.md`
    - `solutions/tripletex/README.md`
- What is proven:
  - Invoice send semantics remain intact end to end:
    - create-and-send prompts still produce `action_semantics.send_to_customer=true`
    - completion checks still include `sent_to_customer`
    - `InvoiceCreateWorkflow` still posts with `sendToCustomer=true`
  - The fallback merge now removes redundant amount/VAT phrases from invoice comments when the line amount already captures that information.
  - The planner guidance now explicitly treats phrases like `La facture concerne ...` as free-text line descriptions unless the prompt explicitly names a product.
  - Trace-specific regressions were added for:
    - stale public worker failures:
      - `445ed1db-6210-4378-a246-0bfc4714062a`
      - `0bb865cf-7884-4494-b2cc-8877d343e700`
    - successful but noisy replay:
      - `251c548b-91a7-4c52-8e1b-7f70040c2ca2`
  - Direct raw API validation succeeded against the sandbox:
    - `GET /customer`
    - `GET /ledger/account`
    - `POST /invoice?sendToCustomer=true`
    - created invoice id `2147525885`
    - created invoice comment was empty
  - Local runner validation succeeded:
    - prompt: `Créez et envoyez une facture au client Codex Logging Probe 20260320-F de 8815 NOK hors TVA. La facture concerne Local runner drift validation 20260320 C.`
    - created invoice id `2147525829`
    - planned line used `description`
    - no `productLookup`
    - created invoice comment was empty
  - Public `/solve` replay succeeded after the worker restart:
    - trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
    - HTTP `200`
    - body `{"status":"completed"}`
    - created invoice id `2147525923`
    - log shows `GET /customer`, `GET /ledger/account`, `POST /invoice`
    - no `GET /product`
    - created invoice comment was empty
- What is assumed:
  - The new comment-pruning heuristic is conservative enough not to remove legitimate explicit comments, but that still needs more live validation on explicit comment prompts.
  - The sandbox invoice-account configuration remains representative enough for hidden send tasks to keep the send path valuable.
  - The public tunnel only needs a manual worker restart after code changes; no deeper deployment issue was observed.
- Next highest-priority task:
  - Add and live-validate explicit invoice-comment prompt variants so we confirm the new guard only removes redundant amount/VAT noise and does not over-prune legitimate comments.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-conversational-prompt-layer-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-log-observability-and-plan-refresh-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-send-semantics-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-drift-hardening-checkpoint.md`

## Latest Work

- Added planner-side pruning for redundant invoice comments:
  - drops `comment` / `invoiceComment` when the value is just an amount/VAT phrase already represented by the extracted line amount
- Strengthened invoice extraction guidance for the OpenAI planner:
  - description-line phrasing should stay in `line.description`
  - amount/VAT wording should not be used as a comment unless explicitly requested
- Added regression coverage for the live trace family:
  - French competition-style create-and-send prompts still carry send intent
  - stale-worker `productLookup` hallucination is removed during fallback merge
  - successful replay amount/VAT comment drift is removed during fallback merge
- Revalidated the running public worker after restarting `uvicorn`

## Validation

- Focused code quality and regression suite:
  - `./.venv/bin/ruff check src/tripletex_agent/task_plan.py src/tripletex_agent/planner.py src/tripletex_agent/workflows/live.py src/tripletex_agent/log_analysis.py tests/test_planner.py tests/test_workflows.py tests/test_log_analysis.py`
    - Result: passed
  - `./.venv/bin/pytest -q tests/test_planner.py tests/test_workflows.py tests/test_log_analysis.py`
    - Result: `44 passed`
- Sandbox read-only gate:
  - `python scripts/smoke_read_only.py`
    - Result: passed
- Raw API validation:
  - direct `GET /customer`
  - direct `GET /ledger/account`
  - direct `POST /invoice?sendToCustomer=true`
    - Result: passed
    - Created invoice id `2147525885`
    - Created invoice comment: empty
- Local runner validation:
  - `./.venv/bin/python scripts/run_prompt.py --execute "Créez et envoyez une facture au client Codex Logging Probe 20260320-F de 8815 NOK hors TVA. La facture concerne Local runner drift validation 20260320 C."`
    - Result: passed
    - Created invoice id `2147525829`
    - Planned line description preserved
    - Created invoice comment: empty
- Public `/solve` replay:
  - restarted local `uvicorn` on `127.0.0.1:8011` before replay
  - replay prompt: `Créez et envoyez une facture au client Codex Logging Probe 20260320-F de 8825 NOK hors TVA. La facture concerne Public solve drift validation 20260320 C.`
  - trace id: `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
  - Result: HTTP `200`, body `{"status":"completed"}`
  - Created invoice id `2147525923`
- Trace review:
  - old competition miss:
    - `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
  - stale public worker failures:
    - `445ed1db-6210-4378-a246-0bfc4714062a`
    - `0bb865cf-7884-4494-b2cc-8877d343e700`
  - earlier successful replay with comment drift:
    - `251c548b-91a7-4c52-8e1b-7f70040c2ca2`
  - current successful replay with send semantics intact and empty comment:
    - `6c15b5a1-53d8-4b68-9cfe-384285fa632a`

## Important Findings

- The original competition semantic miss remains closed:
  - old competition trace `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
    - created invoice only
    - `sendToCustomer=false`
  - current public replay trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
    - explicit send semantics
    - `sendToCustomer=true`
- The public replay that previously fixed send semantics (`251c548b-91a7-4c52-8e1b-7f70040c2ca2`) still exposed a noisy planner artifact:
  - `comment: "8795 NOK hors TVA"`
  - that exact drift is now covered by regression tests and absent from the new replay
- The new live replay is the first public trace that simultaneously proves:
  - send semantics carried end to end
  - no `productLookup` hallucination
  - no amount/VAT phrase in invoice comments
- Trusting public replays still depends on deployment hygiene:
  - after code changes, restart the local `uvicorn` worker before trusting the next tunnel trace

## Known Issues / Risks

- Explicit invoice-comment prompts still need fresh live validation after the new pruning guard.
- The public tunnel can still serve stale code if the local `uvicorn` worker is not restarted after edits.
- Travel expenses are still unimplemented.
- Correction workflows are still unimplemented.
- Module-activation workflows are still unimplemented.
- PDF and CSV extraction are still deferred.

## Next Steps

1. Add explicit comment prompt variants across English and French-style invoice prompts and live-validate that legitimate comments still survive.
2. Keep using public `/solve` replay plus trace review after each invoice-planner change so the logs remain the source of truth.
3. Once explicit-comment coverage is proven, continue widening invoice prompt coverage before moving attention back to lower-priority PDF/CSV work.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, solutions/tripletex/SESSION_HANDOFF.md, solutions/tripletex/README.md, and solutions/tripletex/logs/solve-events.jsonl. Stay scoped to solutions/tripletex/.

Start with the new successful public replay trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a`, compare it against the earlier noisy success `251c548b-91a7-4c52-8e1b-7f70040c2ca2`, and keep the old competition miss `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e` as the original baseline.

Current top priority:
- preserve the validated invoice create-and-send semantics
- confirm legitimate explicit invoice comments still survive the new pruning guard
- keep public `/solve` trace review as the main source of truth

Work checklist:
1. Read the merged roadmap in `solutions/tripletex/PLAN.md`.
2. Confirm the public worker is serving current code before trusting a replay.
3. Add explicit invoice-comment regressions and keep description-line prompts out of `productLookup`.
4. Validate again via `solutions/tripletex/SUBMISSION_CHECKLIST.md`:
   - sandbox raw API behavior
   - local runner
   - public `/solve` replay
   - trace review in `solutions/tripletex/logs/solve-events.jsonl`
5. If you update `SESSION_HANDOFF.md` again, archive the current handoff first in `solutions/tripletex/session_archive/`.

Keep PDF and CSV handling lower priority unless new live trace evidence points there directly.
```
