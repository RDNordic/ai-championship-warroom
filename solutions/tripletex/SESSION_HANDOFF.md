# SESSION_HANDOFF.md

## Checkpoint

Tripletex now has durable solver-side trace logging for both incoming hidden prompts and outgoing Tripletex API calls, plus the first real competition prompt captured from a live submission. The project now has enough evidence to move from generic prompt hardening to log-driven prompt-to-workflow remediation.

This session did two things that materially change the next steps:
- added durable JSONL trace logging and inspection tooling for `/solve`
- merged the live trace evidence back into `PLAN.md`, which now prioritizes semantic alignment between human intent and workflow execution

Repository scope for the next session stays inside `solutions/tripletex/` unless the owner explicitly asks for something broader.

## Handoff Contract

- Current objective:
  - Close the semantic gap between what hidden user prompts ask for and what the deterministic workflow actually executes, starting with invoice create-vs-create-and-send behavior.
- Exact artifact reference:
  - Working tree in `solutions/tripletex/` on `2026-03-20` after:
    - prompt-layer cleanup and fallback-plan merging
    - durable `/solve` event logging
    - per-Tripletex API call logging
    - prompt-pattern inspection tooling
    - log-driven update of `solutions/tripletex/PLAN.md`
  - Public endpoint validated in this session:
    - `https://app-per-formerly-basement.trycloudflare.com/solve`
  - Live trace log path:
    - `solutions/tripletex/logs/solve-events.jsonl`
  - Key docs for the next session:
    - `solutions/tripletex/PLAN.md`
    - `solutions/tripletex/SUBMISSION_CHECKLIST.md`
    - `solutions/tripletex/SESSION_HANDOFF.md`
    - `solutions/tripletex/README.md`
- What is proven:
  - Incoming `/solve` prompts are durably logged with `trace_id`, prompt text, request metadata, selected workflow, and outcome.
  - Outgoing Tripletex API calls are durably logged with method, path, params, body, status, and response payload.
  - The public solver is healthy and the public endpoint remained reachable after the logging changes.
  - The helper script can inspect recent traces, one trace in detail, and normalized prompt patterns.
  - At least one real competition prompt was captured from a live submission and analyzed.
  - The real competition prompt was partially solved: the agent created the correct invoice but did not honor the prompt’s “create and send” semantics.
- What is assumed:
  - The logged French invoice prompt is representative of a broader class of multilingual action-semantics failures, not a one-off oddity.
  - Eliminating unrelated side effects during invoice creation should improve efficiency and reduce hidden-task risk.
  - PDF and CSV handling can remain lower priority until the API-only conversational layer stops missing scorer-relevant semantics.
- Next highest-priority task:
  - Implement invoice send intent end-to-end in the planner and workflow, validate it in sandbox and through public `/solve`, and use the trace log to confirm the semantic mismatch is closed.

## Session Archive

- `solutions/tripletex/session_archive/2026-03-20-scaffold-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-invoice-create-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-validated-invoicing-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-pre-first-solve-submission-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-conversational-prompt-layer-checkpoint.md`
- `solutions/tripletex/session_archive/2026-03-20-log-observability-and-plan-refresh-checkpoint.md`

## Latest Work

- Added durable solve-event logging:
  - `received`
  - `planned`
  - `tripletex_call`
  - `completed`
  - `failed`
- Added request-scoped tracing:
  - `trace_id`
  - safe request metadata
  - prompt and attachment metadata
- Added per-Tripletex API call tracing with status, duration, params, JSON body, and response payload.
- Added log inspection tooling:
  - `python scripts/inspect_solve_logs.py recent`
  - `python scripts/inspect_solve_logs.py trace <trace_id>`
  - `python scripts/inspect_solve_logs.py patterns`
- Added prompt-pattern analysis helpers and tests.
- Updated `PLAN.md` with:
  - prompt taxonomy from the live log
  - prompt-by-prompt semantic assessment
  - severity-ordered findings
  - merged `P0 / P1 / P2` roadmap
- Archived the previous handoff before replacing this one.

## Validation

- Logging and analysis checks:
  - `./.venv/bin/ruff check src/tripletex_agent/log_analysis.py scripts/inspect_solve_logs.py tests/test_log_analysis.py`
    - Result: passed
  - `./.venv/bin/pytest -q tests/test_log_analysis.py`
    - Result: `4 passed`
  - `./.venv/bin/pytest -q tests/test_client.py tests/test_app.py tests/test_models.py`
    - Result: `7 passed`
- CLI smoke against the real log:
  - `./.venv/bin/python scripts/inspect_solve_logs.py recent --limit 3`
  - `./.venv/bin/python scripts/inspect_solve_logs.py patterns --top 5`
  - Result: recent traces and normalized prompt patterns printed correctly from `solve-events.jsonl`
- Live service health:
  - `curl -sS http://127.0.0.1:8011/health`
  - Result: `{"status":"ok"}`
- Earlier focused validation still stands for the supported API-only slice:
  - customer create
  - invoice create
  - invoice payment
  - public `/solve` replay

## Important Findings

- A hidden competition prompt is now captured in the log:
  - `Créez et envoyez une facture au client Lumière SARL (nº org. 827689114) de 8750 NOK hors TVA. La facture concerne Maintenance.`
- That prompt revealed the current highest-priority semantic mismatch:
  - the planner/workflow selected invoice create correctly
  - customer resolution, org number, amount, and description were all handled correctly
  - execution still posted `/invoice` with `sendToCustomer=false`
  - this means the agent likely earned partial credit at best if the scorer checked “sent” semantics
- The current multilingual story is asymmetric:
  - OpenAI-backed extraction can understand more than the deterministic fallback can stabilize
  - high-value action semantics such as “send invoice” are not yet carried through as explicit workflow flags
- Invoice creation currently performs an unrelated bank-account mutation when needed:
  - `GET /ledger/account`
  - `PUT /ledger/account/{id}`
  - this may help bootstrap a sandbox, but it is a poor default for hidden-task efficiency and safety
- The log-analysis helper is useful but still too lossy for some prompts:
  - current normalization can collapse away fields like email, language, and other planner-relevant slots

## Notable Traces

- Internal probe trace:
  - `4d8fdcf5-fe90-4ed9-8d75-4366bbea189c`
  - Customer create probe
  - strong semantic match and efficient execution
- Competition trace:
  - `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e`
  - French invoice create-and-send prompt
  - partial semantic solve due to missing send behavior

## Known Issues / Risks

- Travel expenses are still unimplemented.
- Correction workflows are still unimplemented.
- Module-activation workflows are still unimplemented.
- PDF and CSV extraction are still deferred.
- The supported API-only slice can still return HTTP `200` while missing scorer-relevant semantics.
- Unsupported tasks can still score zero behind HTTP `200` if they fall through to `StubWorkflow`.
- The current real hidden-prompt sample is still small, so prioritization should stay evidence-driven and be updated with each new trace.
- `tests/test_service.py` has shown sandbox runner flakiness around process exit, so use it carefully as a confidence signal and lean on live trace evidence too.

## Next Steps

1. Implement invoice send intent end-to-end in planner schema, extraction, and workflow execution.
2. Add multilingual send/deliver phrase coverage across `nb`, `nn`, `en`, `es`, `pt`, `de`, and `fr`.
3. Reduce or isolate invoice bank-account mutation so hidden invoice tasks do not pay an unnecessary efficiency and side-effect cost.
4. Improve log-analysis normalization so “typical prompts” preserve fields like email, language, org number, VAT wording, and send intent.
5. Re-run the submission checklist on the improved invoice-send path:
   - raw API validation
   - sandbox runner validation
   - public `/solve` replay
   - trace review
6. Only after the API-only semantic gaps are closed, resume broader prompt coverage or attachment work.

## Restart Prompt

```text
Read solutions/tripletex/PLAN.md, solutions/tripletex/SUBMISSION_CHECKLIST.md, solutions/tripletex/SESSION_HANDOFF.md, solutions/tripletex/README.md, and solutions/tripletex/logs/solve-events.jsonl. Stay scoped to solutions/tripletex/.

Use the current live trace evidence as the primary guide. Start with the logged competition trace `c3ba0a55-7baa-4a0b-831c-c0e23870ef7e` and confirm exactly where the prompt intent diverges from execution.

Current top priority:
- implement invoice create-vs-create-and-send semantics end to end
- carry send intent explicitly through planner schema, extraction, and workflow execution
- add multilingual action-semantic coverage across nb, nn, en, es, pt, de, fr
- reduce or isolate invoice bank-account mutation during normal invoice creation
- improve log-analysis heuristics so typical prompt clusters preserve email, language, org number, VAT wording, and send intent

Work checklist:
1. Read the current findings and merged roadmap in `solutions/tripletex/PLAN.md`.
2. Update the planner/task model so invoice send intent is explicit and testable.
3. Update `InvoiceCreateWorkflow` so execution changes when send intent is present.
4. Add regression tests directly from the logged French competition prompt and equivalent multilingual prompt variants.
5. Validate via `solutions/tripletex/SUBMISSION_CHECKLIST.md`:
   - sandbox raw API behavior
   - local runner
   - public `/solve` replay
   - trace review in `solutions/tripletex/logs/solve-events.jsonl`
6. If you update `SESSION_HANDOFF.md` again, archive the current handoff first in `solutions/tripletex/session_archive/`.

Keep PDF and CSV handling lower priority unless the trace evidence shows a direct need.
```
