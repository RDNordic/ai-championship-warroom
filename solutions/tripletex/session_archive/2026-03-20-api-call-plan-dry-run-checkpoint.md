# SESSION_HANDOFF.md

## Checkpoint

Tripletex still has the validated invoice create-and-send path from the public replay, and this session added a safe phase-1 prototype for unsupported tasks:
- invoice create-and-send semantics remain anchored by public trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
- multilingual project creation remains validated by public trace `b5da5c8c-8bb0-4e3d-bf6c-8588c1f7d457`
- multilingual travel expenses are still a real gap, shown by stub trace `c903bd9c-b11a-4d63-92f0-4e115baec310`
- a new feature-flagged dry-run `ApiCallPlan` path now records structured candidate Tripletex call plans for stubbed tasks without changing the live executor

The main source of truth for online behavior remains public `/solve` trace review in `solutions/tripletex/logs/solve-events.jsonl`.

## Handoff Contract

- Current objective:
  - Keep the validated invoice and project paths stable while using live traces to design safe coverage expansion for unsupported tasks, starting with travel expenses through the new dry-run `ApiCallPlan` path.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after:
    - invoice comment pruning for redundant amount/VAT phrases
    - stronger invoice extraction guidance for free-text description lines vs product references
    - phase-1 dry-run `ApiCallPlan` prototype for stubbed task families
    - trace/log tooling that can now surface a generated `api_call_plan`
  - Public endpoint:
    - `https://app-per-formerly-basement.trycloudflare.com/solve`
  - Live trace log path:
    - `solutions/tripletex/logs/solve-events.jsonl`
  - Current live trace anchors:
    - invoice success: `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
    - project success: `b5da5c8c-8bb0-4e3d-bf6c-8588c1f7d457`
    - travel-expense stub: `c903bd9c-b11a-4d63-92f0-4e115baec310`
  - Feature flag state:
    - `ENABLE_API_CALL_PLAN=false`
    - `API_CALL_PLAN_MODEL=gpt-5-mini`
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/SESSION_HANDOFF.md`
    - `solutions/tripletex/README.md`
- What is proven:
  - The online solver behavior for supported tasks is still anchored by live public traces:
    - invoice trace `6c15b5a1-53d8-4b68-9cfe-384285fa632a` still proves `send_to_customer=true`, no `GET /product`, and empty invoice comments
    - project trace `b5da5c8c-8bb0-4e3d-bf6c-8588c1f7d457` still proves multilingual project extraction and execution
  - The live gap is still real:
    - travel-expense trace `c903bd9c-b11a-4d63-92f0-4e115baec310` planned `travel_expenses` but routed to `StubWorkflow` with no Tripletex API calls
  - The fallback merge now removes redundant amount/VAT phrases from invoice comments when the extracted line amount already captures that information.
  - The planner guidance now explicitly treats phrases like `La facture concerne ...` as free-text line descriptions unless the prompt explicitly names a product.
  - The new dry-run `ApiCallPlan` path is feature-flagged and scoped safely:
    - it only activates when the chosen workflow is `StubWorkflow`
    - it records an `api_call_plan` event instead of executing new API calls
    - live workflows skip it entirely
  - Config defaults keep the prototype offline by default:
    - `ENABLE_API_CALL_PLAN=false`
    - `API_CALL_PLAN_MODEL=gpt-5-mini`
  - Log tooling now surfaces generated dry-run plans:
    - `SolveEventLogger` records `api_call_plan`
    - `log_analysis.py` includes `api_call_plan` in trace summaries
    - `scripts/inspect_solve_logs.py` prints the plan in text and JSON modes
  - Focused validation for the new prototype succeeded:
    - `./.venv/bin/ruff check src/tripletex_agent/config.py src/tripletex_agent/service.py src/tripletex_agent/solve_logging.py src/tripletex_agent/log_analysis.py src/tripletex_agent/api_call_plan.py src/tripletex_agent/api_call_planner.py scripts/inspect_solve_logs.py tests/test_config.py tests/test_service.py tests/test_api_call_planner.py tests/test_log_analysis.py`
      - Result: passed
    - `./.venv/bin/pytest -q tests/test_config.py tests/test_api_call_planner.py tests/test_log_analysis.py`
      - Result: `10 passed`
    - direct local service check for the stub path:
      - Result: `{"status":"completed"}`
      - logged events: `received`, `planned`, `api_call_plan`, `completed`
- What is assumed:
  - The dry-run `gpt-5-mini` plans will be good enough to guide executor design once we start replaying real stub prompts locally with the feature flag on.
  - The current curated endpoint catalog in `api_call_planner.py` is enough for the first travel-expense iteration, but it will likely need refinement after reviewing real generated plans.
  - Online behavior remains unchanged while `ENABLE_API_CALL_PLAN` stays off.
- Next highest-priority task:
  - Turn on `ENABLE_API_CALL_PLAN=true` locally only, replay the live travel-expense stub prompt `c903bd9c-b11a-4d63-92f0-4e115baec310`, inspect the generated `api_call_plan`, and refine the schema/prompt before attempting any executor work or online enablement.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-conversational-prompt-layer-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-log-observability-and-plan-refresh-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-send-semantics-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-drift-hardening-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-api-call-plan-dry-run-checkpoint.md`

## Latest Work

- Preserved the invoice drift-hardening work already in the tree:
  - redundant amount/VAT phrasing is pruned out of invoice comments
  - French description-line prompts stay in `line.description`
  - trace-shaped invoice regressions were added around the stale-worker misses and successful replay
- Added phase-1 dry-run `ApiCallPlan` support:
  - new structured Pydantic schema for dry-run API call plans
  - new OpenAI-backed planner that requests a strict structured plan from `gpt-5-mini`
  - feature-flagged service hook that records a dry-run plan only for stubbed tasks
  - new solve-log event type and trace-summary support for reviewing the generated plan
- Added focused tests for:
  - config defaults
  - OpenAI dry-run planner output shaping
  - service logging behavior for stub vs live workflows
  - log-analysis handling of `api_call_plan`

## Validation

- Live trace review still anchors current online behavior:
  - invoice success: `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
  - project success: `b5da5c8c-8bb0-4e3d-bf6c-8588c1f7d457`
  - travel-expense stub: `c903bd9c-b11a-4d63-92f0-4e115baec310`
- Focused code quality checks for the new dry-run path:
  - `./.venv/bin/ruff check src/tripletex_agent/config.py src/tripletex_agent/service.py src/tripletex_agent/solve_logging.py src/tripletex_agent/log_analysis.py src/tripletex_agent/api_call_plan.py src/tripletex_agent/api_call_planner.py scripts/inspect_solve_logs.py tests/test_config.py tests/test_service.py tests/test_api_call_planner.py tests/test_log_analysis.py`
    - Result: passed
- Focused tests:
  - `./.venv/bin/pytest -q tests/test_config.py tests/test_api_call_planner.py tests/test_log_analysis.py`
    - Result: `10 passed`
  - `timeout 20 ./.venv/bin/pytest -q tests/test_service.py -k api_call_plan -vv`
    - Result: both new stub/live service tests passed before the local pytest process lingered in the sandbox
- Direct stub-path service verification:
  - local scripted call to `SolverService.solve(...)` with a stubbed travel-expense plan
  - Result: `{"status":"completed"}`
  - Event sequence: `received`, `planned`, `api_call_plan`, `completed`
  - Confirmed the logged `api_call_plan` carried the structured dry-run steps

## Important Findings

- Translation is not the main problem in the live traffic:
  - French invoice prompts solve
  - German project prompts solve
  - the Spanish travel-expense prompt was understood well enough to classify as `travel_expenses`
- The main blocker is task-family coverage, not multilingual prompt understanding.
- The new dry-run `ApiCallPlan` path gives us a way to inspect model-proposed Tripletex calls for unsupported tasks without risking online execution quality.
- The online solver should remain behaviorally unchanged until the dry-run feature flag is explicitly enabled.

## Known Issues / Risks

- The `ApiCallPlan` prototype does not execute anything yet.
- The dry-run path has only been validated locally; it has not been exercised through the public endpoint because the feature flag remains off.
- Travel expenses are still unimplemented in the live executor.
- The public tunnel can still serve stale code if the local `uvicorn` worker is not restarted after edits.
- Correction workflows are still unimplemented.
- Module-activation workflows are still unimplemented.
- PDF and CSV extraction are still deferred.

## Next Steps

1. Enable `ENABLE_API_CALL_PLAN=true` locally only and replay the live travel-expense stub prompt `c903bd9c-b11a-4d63-92f0-4e115baec310`.
2. Inspect the generated `api_call_plan` in `solve-events.jsonl` and refine the schema or curated endpoint catalog before any executor work.
3. Keep public `/solve` replay and trace review as the source of truth for supported live paths, especially invoice send semantics.
4. After the dry-run plans look sane, decide whether to build a deterministic executor for one narrow travel-expense create shape.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, solutions/tripletex/SESSION_HANDOFF.md, solutions/tripletex/README.md, and solutions/tripletex/logs/solve-events.jsonl. Stay scoped to solutions/tripletex/.

Start with the current live trace anchors:
- invoice success: `6c15b5a1-53d8-4b68-9cfe-384285fa632a`
- project success: `b5da5c8c-8bb0-4e3d-bf6c-8588c1f7d457`
- travel-expense stub: `c903bd9c-b11a-4d63-92f0-4e115baec310`

Current top priority:
- preserve the validated invoice create-and-send semantics
- keep public `/solve` trace review as the main source of truth for live behavior
- use the dry-run `ApiCallPlan` path to study unsupported travel-expense prompts before building any executor

Work checklist:
1. Read the merged roadmap in `solutions/tripletex/PLAN.md`.
2. Confirm the public worker is serving current code before trusting a replay.
3. Turn on `ENABLE_API_CALL_PLAN=true` locally only and replay the travel-expense stub trace prompt to generate `api_call_plan` events.
4. Review the generated dry-run steps in `solutions/tripletex/logs/solve-events.jsonl` and `scripts/inspect_solve_logs.py`.
5. If the dry-run plan looks sane, scope one narrow deterministic executor candidate for travel expenses.
6. If you update `SESSION_HANDOFF.md` again, archive the current handoff first in `solutions/tripletex/session_archive/`.

Keep PDF and CSV handling lower priority unless new live trace evidence points there directly.
```
