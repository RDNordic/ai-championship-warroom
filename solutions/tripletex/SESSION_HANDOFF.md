# SESSION_HANDOFF.md

## Checkpoint (2026-03-22)

- Branch: `tripletex/complex-multi-step-project`
- Local HEAD: `8278f5f` (`tripletex: harden solve path and plan validation`)
- Working tree: additional local, uncommitted fixes in `api_validator.py`, `llm_executor.py`, and `tests/test_llm_executor.py`
- Service: `captains-tripletex`
- Cloud Run URL: `https://captains-tripletex-339414168231.europe-north1.run.app`
- Submission page: `https://app.ainm.no/submit/tripletex`
- Last documented leaderboard snapshot in repo history: `~53.2` on `2026-03-22 ~08:00 CET`
- Latest observed score set this session: `0/8, 8/8, 2/8` from `run_20260322_111308.log`

## Current Objective

Deploy and verify the current local patch that targets the latest deployed blockers:
- plan validation rejects valid `/$var` endpoint paths too early
- invoice line VAT ids are still drifting into input/invalid VAT codes on `POST /invoice`

The recent voucher/accounting hardening should be kept; the current bottleneck moved further upstream into planning/normalization.

## Active Architecture

The live `/solve` path is:

```text
POST /solve
  -> app.py
  -> service.py
  -> LLMApiExecutor in llm_executor.py
  -> TripletexClient
```

Important:
- `service.py` currently builds the solver around `LLMApiExecutor`.
- `ANTHROPIC_API_KEY` is required for the default app/service boot path.
- The older deterministic workflows under `src/tripletex_agent/workflows/` are still in the repo, but they are not the active competition path right now.
- If the goal is "more handling" for the deployed solver, patch `llm_executor.py` and its validators/prompts first, not `workflows/live.py`, unless you intentionally rewire `service.py`.

## Deployment Loop

1. From `solutions\tripletex\`, run `.\scripts\deploy-ko.ps1`
2. Verify the new Cloud Run revision still has `ANTHROPIC_API_KEY`
3. Submit on `https://app.ainm.no/submit/tripletex`
4. Run `.\scripts\post-score.ps1`
5. Inspect the newest file in `solutions/tripletex/logs/`
6. Compare only log entries after the latest `DELETE /logs` boundary

## Artifact Reference

Primary files for the next session:
- `solutions/tripletex/src/tripletex_agent/llm_executor.py`
- `solutions/tripletex/src/tripletex_agent/api_validator.py`
- `solutions/tripletex/src/tripletex_agent/schema_validator.py`
- `solutions/tripletex/src/tripletex_agent/service.py`
- `solutions/tripletex/src/tripletex_agent/app.py`
- `solutions/tripletex/tests/test_llm_executor.py`
- `solutions/tripletex/tests/test_service.py`

Key recent log artifacts already referenced by the repo:
- `solutions/tripletex/logs/run_20260322_092146.log`
- `solutions/tripletex/logs/run_20260322_101830.log`
- `solutions/tripletex/logs/run_20260322_111308.log`

## What Is Proven

- The deploy-submit-log loop works end to end.
- The service preserves the competition response contract and returns HTTP `200` with `{"status":"completed"}`.
- Runtime hardening from `8278f5f` is in place:
  - invalid/non-object plans are rejected before execution
  - missing correction prompt files no longer crash the request path
  - executor/service/app failure handling logs internal failures more truthfully
- Executor-side recovery is in place for unresolved variables and some ID derivation paths.
- Supplier-invoice account rerouting exists for some generic prompts.
- Additional local fixes now exist in the working tree:
  - strict blocking of unbalanced `POST /ledger/voucher`
  - deterministic rebuild of 25% supplier vouchers with explicit input VAT posting
  - project timesheet activity repair toward project/chargeable activities
  - variable-id path normalization in the API validator
  - deterministic invoice VAT normalization for sales invoices
- The targeted regression suite passes from the actual Tripletex venv:
  - command: `& '.\.venv\Scripts\python.exe' -m pytest tests\test_llm_executor.py`
  - result: `40 passed`
- The latest deployed run in `run_20260322_111308.log` suggests the voucher hardening did not regress:
  - payroll/manual voucher flow completed cleanly and is the strongest candidate for the observed `8/8`
  - no fresh evidence in that log shows the old "schema warned but still sent bad voucher" failure mode

## What Is Not Proven

- The current local `api_validator.py` + invoice-VAT patch has not yet been verified in a fresh deployment/log after it was written.
- Full `pytest` is not currently a clean green gate from a cold shell. It fails during `tests/test_app.py` collection if `ANTHROPIC_API_KEY` is not set because `app.py` builds the default service at import time.
- The older workflow files are not proof of deployed capability because the live path does not route through them.
- The old `~53.2` leaderboard snapshot should be treated as historical context, not a guaranteed current score.

## Last Strong Evidence From Logs

The freshest concrete evidence is now in `run_20260322_111308.log`:

1. Fixed-price milestone prompt likely drove the `0/8`
   - the plan failed before execution
   - validator rejected `PUT /project/$project_id` as "not in catalog"
   - the invoice step in that same plan was also missing `deliveryDate`

2. Payroll/manual voucher flow likely drove the `8/8`
   - the request completed with a balanced `POST /ledger/voucher`
   - this is evidence that the recent voucher/accounting hardening did not introduce a regression on that path

3. Mixed-VAT invoice prompt likely drove the `2/8`
   - first `POST /invoice` failed `422 Ugyldig mva-kode`
   - the deployed solver was still looking up `/ledger/vatType` and drifting into wrong invoice VAT ids
   - a corrected retry succeeded, which means the deployed path is recoverable but still semantically brittle

## Current Assessment

The current highest-value remaining losses are no longer the original supplier-voucher/project-activity failures.

The dominant issues after the latest deployed run are:
- path normalization during plan validation for valid `/$var` endpoints
- invoice VAT normalization on sales invoices

Runtime crashes are not the main bottleneck, and the voucher-balance issue should stay fixed.

## Next Highest-Priority Task

Deploy the current local working-tree patch, then validate the next log specifically for these two cases:

1. Variable-id path normalization
   - confirm prompts using `/project/$project_id` and `/invoice/$invoice_id/:payment` now pass plan validation

2. Sales invoice VAT normalization
   - confirm `POST /invoice` no longer emits input/invalid VAT ids like `1` or `33`
   - the intended steady-state sales mappings are:
     - `25% -> 3`
     - `15% -> 31`
     - `12% -> 32`
     - `0% -> 6`

If that fresh deployment still shows partials:
- next patch should move from normalization to a more deterministic fixed-price/milestone invoice builder or order/invoice flow guard

## Secondary Backlog

After the deploy/verify cycle above, the next likely wins are still:
- tighten exact-account fallback after empty `number=` lookups such as `6030` and `1219`
- stronger routing of clear supplier-invoice prompts toward `/supplierInvoice`
- better fixed-price / milestone invoice handling
- travel expense reliability beyond the current partial recipe coverage

## Known Limitations

- `/solve` can still return `200 {"status":"completed"}` for semantically bad runs, so logs remain mandatory.
- The current local fixes are not yet captured in a commit; `HEAD` still points at `8278f5f`.
- Supplier-invoice rerouting is still heuristic and keyword-limited.
- Account fallback logic can still overfit to the first broad-search hit after an exact miss.
- Project invoicing is still not fully deterministic; the recent local patch normalizes VAT ids, but it does not yet introduce a dedicated fixed-price/milestone builder.
- Log files can contain multiple runs; always isolate the fresh run using the latest `DELETE /logs` line.
- `README.md`, `PLAN.md`, and `PLAN_CHRIS_TAKEOVER.md` contain useful context but are not perfectly aligned with the active unified-executor path.

## Repro / Validation Commands

From `solutions\tripletex\`:

- Targeted tests:
  - `& '.\.venv\Scripts\python.exe' -m pytest tests\test_llm_executor.py`
- Deploy:
  - `.\scripts\deploy-ko.ps1`
- Post-deploy score snapshot:
  - `.\scripts\post-score.ps1`
- Full test sweep if env is configured:
  - `$env:ANTHROPIC_API_KEY='...'; & '.\.venv\Scripts\python.exe' -m pytest`
- Local smoke:
  - `& '.\.venv\Scripts\python.exe' scripts\smoke_read_only.py`

## Handoff Contract

Current objective:
- deploy and verify the current local patch for variable-id path normalization and sales-invoice VAT normalization on the unified executor path

Exact artifact reference:
- branch `tripletex/complex-multi-step-project`
- local HEAD `8278f5f`
- working tree includes uncommitted edits in:
  - `src/tripletex_agent/api_validator.py`
  - `src/tripletex_agent/llm_executor.py`
  - `tests/test_llm_executor.py`
- service `captains-tripletex`

What is proven:
- deploy/submit/log loop works
- runtime hardening is deployed
- latest deployed payroll/manual voucher path is healthy
- local targeted executor regression suite passes (`40 passed`)

What is assumed:
- the latest `0/8` is dominated by pre-execution plan rejection on variable-path endpoints
- the latest `2/8` is dominated by brittle invoice VAT mapping rather than a voucher-accounting regression

Next highest-priority task:
- deploy the current working-tree patch and inspect the next fresh log for:
  - successful plan validation on `/project/$project_id`-style paths
  - correct invoice VAT ids on `POST /invoice`
