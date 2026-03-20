# Tripletex — Next Steps (Coverage Expansion Branch)

**Branch:** `feature/tripletex-coverage-expansion`
**Date:** 2026-03-20
**Context:** Andrew picking up from KO's foundation. KO may still be running the live endpoint on `main`.

---

## Session Setup (Do This First)

1. Read `solutions/tripletex/README.md` for the full challenge spec
2. Read `solutions/tripletex/SESSION_HANDOFF.md` for KO's latest state
3. Read `solutions/tripletex/PLAN.md` for the architecture and priority findings
4. Stay scoped to `solutions/tripletex/` only

### Local Dev Setup

```bash
cd solutions/tripletex
python -m venv .venv
source .venv/bin/activate        # or .venv/Scripts/activate on Windows
pip install -e ".[dev]"
```

Create `solutions/tripletex/.env` (gitignored):
```
TRIPLETEX_BASE_URL=https://kkpqfuj-amager.tripletex.dev/v2
TRIPLETEX_SESSION_TOKEN=<from app.ainm.no team Tripletex sandbox card>
OPENAI_API_KEY=<your key>
```

Verify: `python scripts/smoke_read_only.py`

---

## Current State

**Score: 2/30 tasks solved** (first submission baseline)

### Working Workflows (8)
| Workflow | Class | Status |
|---|---|---|
| Customer create | `CustomerCreateWorkflow` | Proven live |
| Product create | `ProductCreateWorkflow` | Live |
| Employee create | `EmployeeCreateWorkflow` | Live |
| Department create | `DepartmentCreateWorkflow` | Live |
| Project create | `ProjectCreateWorkflow` | Proven multilingual |
| Invoice create+send | `InvoiceCreateWorkflow` | Proven, send semantics fixed |
| Invoice payment | `InvoicePaymentWorkflow` | Live |
| Invoice credit note | `InvoiceCreditNoteWorkflow` | Live |

### Not Implemented (routes to StubWorkflow)
- Travel expenses (create, delete)
- Employee update (roles, contact info)
- Customer update
- Entity deletions / corrections
- Voucher reversal
- Module activation (e.g. department accounting)
- PDF/CSV attachment extraction

---

## Priority Work Order

### Phase 1 — Quick Coverage Wins (Tier 1/2, highest ROI)

**1. Travel expense create**
- Already classifies correctly to `travel_expenses` family
- Parent+child pattern: `POST /travelExpense` then child resources like `POST /travelExpense/cost` or `/travelExpense/mileageAllowance`
- Check `PLAN.md` "Travel Expenses" section for endpoint list
- Relevant endpoints: `/travelExpense`, `/travelExpense/cost`, `/travelExpense/mileageAllowance`, `/travelExpense/perDiemCompensation`, `/travelExpense/accommodationAllowance`
- May need `/travelExpense/:deliver` for completion

**2. Travel expense delete**
- `GET /travelExpense` -> `DELETE /travelExpense/{id}`
- Simple lookup + delete pattern

**3. Employee update**
- `GET /employee` -> `PUT /employee/{id}`
- Roles/entitlements via `/employee/entitlement/:grantEntitlementsByTemplate`
- Scoring example: "Administrator role assigned" is worth 5/10 points

**4. Customer update**
- `GET /customer` -> `PUT /customer/{id}`

### Phase 2 — Corrections & Reversals

**5. Voucher reversal** — `GET /ledger/voucher` -> `PUT /ledger/voucher/{id}/:reverse`
**6. Entity deletion** (department, project, product, customer) — GET -> DELETE pattern

### Phase 3 — Tier 3 Prep (Saturday)
- Module activation via `/company/salesmodules`
- PDF/image attachment extraction for data-from-file tasks
- Complex multi-step scenarios (bank reconciliation, year-end closing)

---

## Architecture Rules (Inherit from KO)

- **Add new `BaseWorkflow` subclasses** — one per task type, register in `service.py`'s `build_default_service()`
- **Don't touch the planner heavily** — extend `TaskPlan`/`Operation` enums only where needed
- **Don't rewrite existing working workflows** — invoice, customer, project etc. are proven
- **Zero 4xx tolerance** — validate locally before API calls
- **One workflow per commit** — test, measure, commit
- **Use `scripts/run_prompt.py --execute "..."` to test** against sandbox before any submission

## Key Files

- Workflow implementations: `src/tripletex_agent/workflows/live.py`
- Workflow registry: `src/tripletex_agent/workflows/registry.py` + `service.py:build_default_service()`
- Task plan schema: `src/tripletex_agent/task_plan.py` (enums, entity types)
- Planner (LLM extraction): `src/tripletex_agent/planner.py`
- API client: `src/tripletex_agent/client.py`
- Tests: `tests/`

## Scoring Reminder

- Correctness x Tier multiplier (x1/x2/x3) = base score
- Perfect correctness unlocks efficiency bonus (can 2x the tier score)
- Max per task: 6.0 (Tier 3, perfect, best efficiency)
- 4xx errors and unnecessary GETs kill efficiency bonus
- Best score per task is kept forever — bad runs don't hurt
- Breadth > depth: covering 20/30 tasks beats perfecting 10
