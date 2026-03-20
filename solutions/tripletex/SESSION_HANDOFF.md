# SESSION_HANDOFF.md

## Checkpoint

Endpoint was **LIVE at 0/7**. This session added 9 new workflows and fixed 2 broken ones.
Score should improve significantly on next submission.

## What Was Done This Session

### New workflows added (9)
| Workflow | Pattern | Status |
|---|---|---|
| CustomerDeleteWorkflow | GET /customer → DELETE /customer/{id} | Coded, untested live |
| CustomerUpdateWorkflow | GET /customer → PUT /customer/{id} | Coded, untested live |
| ProductDeleteWorkflow | GET /product → DELETE /product/{id} | Coded, untested live |
| EmployeeUpdateWorkflow | GET /employee → PUT /employee/{id} | Coded, untested live |
| DepartmentDeleteWorkflow | GET /department → DELETE /department/{id} | Coded, untested live |
| ProjectDeleteWorkflow | GET /project → DELETE /project/{id} | Coded, untested live |
| TravelExpenseDeleteWorkflow | GET /travelExpense → DELETE /travelExpense/{id} | Coded, untested live |
| VoucherReverseWorkflow | GET /ledger/voucher → PUT /ledger/voucher/{id}/:reverse | Coded, untested live |

### Fixes
- **CustomerCreate**: removed `isCustomer: True` from POST body (was likely causing proxy rejection as read-only field); added `_normalize_language()` to map EN/ENG/ENGLISH → EN, NO/NB/NN → NO
- **DepartmentCreate**: now supports multi-entity prompts ("Create depts: X, Y, Z") via `names: list[str]` in planner schema + loop in workflow
- **Planner**: DELETE/REVERSE handling added to `_plan_from_extraction`; expanded keyword rules for all new operations (EN + NO); LLM system prompt updated with all new supported operations

### Commits
- `9a48b99` tripletex: add delete+update workflows — 7 new task types
- `9b5d07d` tripletex: fix CustomerCreate + DepartmentCreate multi-entity
- `9494c2c` tripletex: add VoucherReverseWorkflow + expand REVERSE planner coverage

## Current Workflow Coverage (18 workflows)

### Creates (9)
- CustomerCreate ✓ (fixed — `isCustomer` removed)
- ProductCreate ✓
- EmployeeCreate ✓ (requires default dept)
- DepartmentCreate ✓ (now multi-entity capable)
- ProjectCreate ✓ (confirmed live)
- InvoiceCreate+Send ✓ (send semantics implemented)
- InvoicePayment ✓
- InvoiceCreditNote ✓
- TravelExpenseCreate ✓ (sandbox validated)

### Updates (2)
- CustomerUpdate (new)
- EmployeeUpdate (new)

### Deletes (5)
- CustomerDelete (new)
- ProductDelete (new)
- DepartmentDelete (new)
- ProjectDelete (new)
- TravelExpenseDelete (new)

### Corrections (1)
- VoucherReverse (new)

### Still Missing (StubWorkflow → 0 pts)
- EmployeeDelete
- Module activation (company/salesmodules)
- PDF/image attachment extraction
- Complex voucher/ledger tasks (Tier 3)

## Handoff Contract

- Branch: `feature/tripletex-coverage-expansion` at commit `9494c2c`
- `.venv` set up and working (Python 3.14.2)
- `.env` file EXISTS with valid credentials
- Server command: `.venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000`
- Tunnel command: `npx cloudflared tunnel --url http://localhost:8000`
- **Tunnel URL is ephemeral** — must re-register at `https://app.ainm.no/submit/tripletex` each restart

## Priority Work Order (Next Session)

### IMMEDIATE
1. **Start endpoint** — uvicorn + cloudflared + register URL
2. **Submit** — the new workflows are live, get a baseline score
3. **Check logs** — `python scripts/inspect_solve_logs.py recent --limit 20`

### If CustomerCreate still fails
- Check the actual error from logs
- Try: `python scripts/run_prompt.py --execute "Create customer Test AS with org 123456789"`
- The `isCustomer` fix should help; if still failing check the actual API error detail

### High-value additions
4. **EmployeeDelete** — simple GET + DELETE /employee/{id}, 15-min job
5. **ProductUpdate** — GET + PUT /product/{id}, 30-min job
6. **Travel expense deliver/approve** — PUT /travelExpense/{id}/:deliver after create
7. **Improve voucher lookup** — currently requires voucherNumber; try adding description/date search

### Planner improvements
- The LLM planner system prompt now covers all current operations
- Watch for prompts that route to StubWorkflow — add keywords for those patterns
- Multi-employee create (same pattern as multi-department) — low priority

## Validation

- `.venv/Scripts/pytest -q`: 65 passed
- All new workflows coded but NOT yet tested against proxy
- CustomerCreate fix: isCustomer removed — should fix proxy rejection
- Test before trusting any new workflow in live submission

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
- `solutions/tripletex/session_archive/2026-03-20-api-call-plan-dry-run-checkpoint.md`

## Restart Prompt

```text
Branch: feature/tripletex-coverage-expansion at commit 9494c2c
Scope: solutions/tripletex/ only.

Read solutions/tripletex/SESSION_HANDOFF.md first.

STEP 1 — GET ENDPOINT LIVE:
  cd solutions/tripletex
  .venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000
  npx cloudflared tunnel --url http://localhost:8000
  Register tunnel URL + /solve at https://app.ainm.no/submit/tripletex

STEP 2 — SUBMIT:
  Hit submit on the platform and wait for results.
  Check: python scripts/inspect_solve_logs.py recent --limit 20

STEP 3 — DEBUG IF NEEDED:
  CustomerCreate fix shipped (isCustomer removed). If still failing:
    python scripts/run_prompt.py --execute "Create customer Test AS"
  DepartmentCreate multi-entity fix shipped. Test:
    python scripts/run_prompt.py "Opprett tre avdelingar: Logistikk, Kundeservice, HR"

STEP 4 — NEXT WORKFLOWS (by ROI):
  - EmployeeDelete: GET /employee → DELETE /employee/{id}
  - ProductUpdate: GET /product → PUT /product/{id}
  - Travel expense deliver: add deliver=true support to planner extraction
```
