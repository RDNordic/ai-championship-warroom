# SESSION_HANDOFF.md

## Checkpoint

Tripletex now carries invoice send intent explicitly from planning to execution, and that behavior has been validated at all the important layers:
- direct raw Tripletex API
- local `run_prompt.py --execute`
- public HTTPS `/solve`
- solver trace review in `logs/solve-events.jsonl`

This session closed the exact semantic gap seen in competition trace `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`: the new public replay trace `251c548b-91a7-4c52-8e1b-7f70040c2ca2` now records `action_semantics.send_to_customer=true` and sends the invoice with `sendToCustomer=true`.

Repository scope for the next session stays inside `solutions/tripletex/` unless the owner explicitly asks for something broader.

## Handoff Contract

- Current objective:
  - Keep the invoice send path stable in production and tighten the remaining invoice extraction rough edges revealed during validation, especially comment drift and product-vs-description confusion on multilingual prompts.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after:
    - explicit `TaskPlan.action_semantics`
    - invoice `sendToCustomer` extraction through planner and fallback
    - `InvoiceCreateWorkflow` branching on send intent
    - bank-account mutation isolated away from normal invoice create
    - multilingual send-intent regression coverage
    - improved log normalization for email, language, org number, VAT wording, and send intent
  - Public endpoint revalidated in this session:
    - `https://app-per-formerly-basement.trycloudflare.com/solve`
  - Local service note:
    - the long-running `uvicorn` worker on `127.0.0.1:8011` had to be restarted once during validation because the tunnel was still serving stale in-memory code
  - Live trace log path:
    - `solutions/tripletex/logs/solve-events.jsonl`
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/SESSION_HANDOFF.md`
    - `solutions/tripletex/README.md`
- What is proven:
  - The planner now emits explicit send semantics:
    - `action_semantics.send_to_customer=true` for create-and-send prompts
    - `completion_checks` now include `sent_to_customer` when applicable
  - The deterministic fallback now recognizes send intent across `nb`, `nn`, `en`, `es`, `pt`, `de`, and `fr`.
  - Normal invoice creation no longer performs ledger-account mutation by default.
  - The send path uses `GET /ledger/account` only when send intent is present.
  - Direct raw API validation succeeded with `POST /invoice?sendToCustomer=true` against the sandbox account.
  - Local runner validation succeeded with a French create-and-send prompt.
  - Public `/solve` replay succeeded after the stale worker restart:
    - HTTP `200`
    - body `{"status":"completed"}`
    - trace `251c548b-91a7-4c52-8e1b-7f70040c2ca2`
  - The new successful public trace shows:
    - `action_semantics.send_to_customer=true`
    - `completion_checks` include `sent_to_customer`
    - `POST /invoice` uses `sendToCustomer=true`
    - no `GET /product` drift on the successful run
- What is assumed:
  - The sandbox invoice-account configuration is representative enough for hidden send tasks to make the new path valuable.
  - The scorer accepts `sendToCustomer=true` on invoice creation as the relevant business action for “create and send”.
  - The public worker only needs occasional manual restart after code changes; no deeper deployment bug was observed.
- Next highest-priority task:
  - Reduce the remaining extraction noise on invoice prompts, especially:
    - avoid amount/VAT phrases leaking into `comment`
    - keep description-line prompts from drifting into `productLookup`
    - preserve the validated send semantics while tightening those fields

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-conversational-prompt-layer-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-log-observability-and-plan-refresh-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-send-semantics-checkpoint.md`

## Latest Work

- Added explicit action semantics to the task model:
  - `TaskPlan.action_semantics.send_to_customer`
- Extended planner extraction:
  - `InvoiceExtraction.sendToCustomer`
  - deterministic send-intent detection across `nb`, `nn`, `en`, `es`, `pt`, `de`, `fr`
  - multilingual invoice-customer / amount / description handling for the traced send-invoice prompt family
- Added action-aware completion checks:
  - `sent_to_customer`
- Updated `InvoiceCreateWorkflow`:
  - normal create keeps `sendToCustomer=false`
  - create-and-send uses `sendToCustomer=true`
  - ledger-account lookup/mutation now only happens on the send path
  - workflow result now records `sendToCustomer`, `invoiceBankAccountId`, and `invoiceBankAccountUpdated`
- Improved log normalization:
  - preserves or canonicalizes email, language, org number, VAT wording, and send intent
- Added regression coverage:
  - logged French competition prompt
  - equivalent multilingual send prompts
  - fallback merge coverage for the traced semantic miss
  - workflow create-vs-create-and-send behavior

## Validation

- Focused code quality and regression suite:
  - `./.venv/bin/ruff check src/tripletex_agent/task_plan.py src/tripletex_agent/planner.py src/tripletex_agent/workflows/live.py src/tripletex_agent/log_analysis.py tests/test_planner.py tests/test_workflows.py tests/test_log_analysis.py`
    - Result: passed
  - `./.venv/bin/pytest -q tests/test_planner.py tests/test_workflows.py tests/test_log_analysis.py`
    - Result: `42 passed`
- Sandbox read-only gate:
  - `python scripts/smoke_read_only.py`
    - Result: passed
- Raw API validation:
  - direct `GET /customer`
  - direct `GET /ledger/account`
  - direct `POST /invoice?sendToCustomer=true`
    - Result: passed
    - Created invoice id `2147525215`
- Local runner validation:
  - `./.venv/bin/python scripts/run_prompt.py --execute "Créez et envoyez une facture au client Codex Logging Probe 20260320-F de 8775 NOK hors TVA. La facture concerne Local runner send validation 20260320 A."`
    - Result: passed
    - Created invoice id `2147525232`
- Public `/solve` replay:
  - first replay failed because the tunnel was still serving a stale `uvicorn` process
  - after restarting the local worker, replay succeeded:
    - prompt: `Créez et envoyez une facture au client Codex Logging Probe 20260320-F de 8795 NOK hors TVA. La facture concerne Public solve send validation 20260320 B.`
    - Result: HTTP `200`, body `{"status":"completed"}`
    - Created invoice id `2147525393`
- Trace review:
  - failed stale-worker traces:
    - `445ed1db-6210-4378-a246-0bfc4714062a`
    - `0bb865cf-7884-4494-b2cc-8877d343e700`
  - successful updated-worker trace:
    - `251c548b-91a7-4c52-8e1b-7f70040c2ca2`

## Important Findings

- The original competition semantic miss is now demonstrably closed in the live solver path:
  - old competition trace `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
    - planned plain create
    - `POST /invoice` with `sendToCustomer=false`
  - new replay trace `251c548b-91a7-4c52-8e1b-7f70040c2ca2`
    - planned `action_semantics.send_to_customer=true`
    - `POST /invoice` with `sendToCustomer=true`
- The public endpoint failure seen during validation was not a new planner/workflow bug.
  - It was a stale-process deployment issue.
  - The logged failed traces still showed the old in-memory planner behavior.
  - Restarting `uvicorn` fixed the public path immediately.
- Raw API validation showed the send path works cleanly when the invoice bank account is already configured.
  - The send workflow still performs a `GET /ledger/account`, but it did not need a mutation on the validated account.
- Log normalization is now much more useful for prompt mining.
  - The successful French send trace normalizes to a pattern that clearly preserves send intent and VAT wording.

## Notable Traces

- Original competition miss:
  - `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
  - create-and-send prompt solved only as create
- Stale public worker failures:
  - `445ed1db-6210-4378-a246-0bfc4714062a`
  - `0bb865cf-7884-4494-b2cc-8877d343e700`
  - both failed because the old worker still hallucinated `productLookup`
- Successful updated public replay:
  - `251c548b-91a7-4c52-8e1b-7f70040c2ca2`
  - create-and-send semantics carried correctly end to end

## Known Issues / Risks

- The public tunnel can serve stale code if the local `uvicorn` worker is not restarted after changes.
- Invoice prompts can still leak amount/VAT phrasing into `comment` depending on planner behavior.
- Some multilingual prompts may still drift between free-text description and `productLookup` in the LLM path.
- Travel expenses are still unimplemented.
- Correction workflows are still unimplemented.
- Module-activation workflows are still unimplemented.
- PDF and CSV extraction are still deferred.

## Next Steps

1. Tighten invoice extraction so description-line prompts do not drift into `productLookup`.
2. Prevent amount/VAT phrasing from being turned into invoice comments unless the prompt actually asks for a comment.
3. Keep using live trace review after each public replay to confirm the tunnel is serving the current code.
4. Once invoice extraction noise is reduced, make another competition submission on the now-validated send path.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, solutions/tripletex/SESSION_HANDOFF.md, solutions/tripletex/README.md, and solutions/tripletex/logs/solve-events.jsonl. Stay scoped to solutions/tripletex/.

Start with the successful public replay trace `251c548b-91a7-4c52-8e1b-7f70040c2ca2` and compare it against the old competition miss `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`.

Current top priority:
- preserve the validated invoice create-and-send semantics
- reduce invoice comment drift from amount/VAT phrases
- reduce product-lookup hallucination on description-line prompts
- keep public `/solve` trace review as the main source of truth

Work checklist:
1. Read the current findings and merged roadmap in `solutions/tripletex/PLAN.md`.
2. Confirm the public worker is serving current code before trusting a replay.
3. Tighten invoice extraction so free-text service descriptions stay descriptions.
4. Add regression tests from the stale-worker failed traces and the successful replay trace.
5. Validate again via `solutions/tripletex/SUBMISSION_CHECKLIST.md`:
   - sandbox raw API behavior
   - local runner
   - public `/solve` replay
   - trace review in `solutions/tripletex/logs/solve-events.jsonl`
6. If you update `SESSION_HANDOFF.md` again, archive the current handoff first in `solutions/tripletex/session_archive/`.

Keep PDF and CSV handling lower priority unless new live trace evidence points there directly.
```
