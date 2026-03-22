# Tripletex Challenge — Takeover Assessment & Plan

## Context

Chris is taking over the Tripletex AI Accounting Agent challenge (previously owned by KO). The competition deadline is March 22, 2026. The agent must handle 30 task types across 7 languages, scored on correctness + efficiency. Current baseline: **2/30 tasks solved**.

This plan covers: (1) what exists, (2) what the docs say vs what the code actually does, (3) what needs to happen next.

---

## Current State Summary

### What's Built (code matches docs)
- FastAPI `/solve` endpoint accepting `SolveRequest` (prompt, files, credentials)
- OpenAI-based planner (`gpt-5-mini`) with keyword fallback for task classification
- **8 live workflows** implemented:
  - CustomerCreate, ProductCreate, EmployeeCreate, DepartmentCreate, ProjectCreate
  - InvoiceCreate (with send semantics), InvoicePayment, InvoiceCreditNote
- Structured `TaskPlan` schema with `TaskFamily` + `Operation` enums
- `TripletexClient` (async httpx, Basic auth, JSONL event logging)
- Invoice send semantics: fully wired (planner extracts `send_to_customer`, workflow honors it)
- Dry-run `ApiCallPlan` prototype for unsupported tasks (feature-flagged OFF)
- JSONL trace logging with inspection scripts
- 45 tests across 9 test files

### What's NOT Built (documented as gaps, confirmed in code)
- **Travel expense workflows** — keyword detection exists, but StubWorkflow
- **Correction/reversal workflows** — no implementation
- **Module-activation workflows** — no implementation
- **Employee UPDATE** — only CREATE exists
- **Customer/Product UPDATE** — only CREATE exists
- **PDF/CSV attachment extraction** — not implemented
- **DELETE operations** — no implementation for any entity type

### LLM: OpenAI Only (NOT Claude)
- All LLM calls use `openai.OpenAI()` with `gpt-5-mini`
- Zero Claude/Anthropic references anywhere in codebase
- README says "LLM: Claude API" but code uses OpenAI — **doc/code mismatch**

---

## Doc vs Code Alignment Check

| Area | Docs Say | Code Does | Match? |
|------|----------|-----------|--------|
| Endpoint contract | POST /solve, 200 + completed | Correct | YES |
| Auth | Basic auth, user=0, pass=token | Correct | YES |
| LLM | README says "Claude API" | Uses OpenAI gpt-5-mini | **NO** |
| Invoice send | PLAN.md says P0 | Fully implemented | YES |
| Travel expenses | Listed as gap | StubWorkflow | YES |
| Corrections | Listed as gap | Not implemented | YES |
| Bank account mutation | PLAN.md P1 concern | Still in code (conditional on send) | YES |
| 8 supported workflows | SUBMISSION_CHECKLIST lists them | All 8 exist in live.py | YES |
| ApiCallPlan dry-run | SESSION_HANDOFF describes | Implemented, flag OFF | YES |
| .env.example | README mentions it | Does NOT exist | **NO** |
| Logs directory | .gitignored, mentioned | Correct | YES |

### Key Mismatches
1. **README line 184**: Says "LLM: Claude API" — code exclusively uses OpenAI
2. **No .env.example file**: README says "Copy `.env.example` to `.env`" but no such file exists

---

## Competition Math: What Matters Most

- 30 task types, scored independently. Best score per task kept forever.
- Tier 1 (×1): employee, customer, product, department — **already covered**
- Tier 2 (×2): invoice+payment, credit notes, project billing — **partially covered**
- Tier 3 (×3): bank reconciliation, error correction, year-end — **NOT covered at all**
- Max score per task: tier × 2 (with perfect efficiency)
- **Tier 3 tasks have 6.0 ceiling vs 1.0-2.0 for Tier 1** — highest leverage

Current 8 workflows cover roughly Tier 1 + some Tier 2. The biggest score gains come from:
1. **Expanding to more task types** (breadth > depth)
2. **Implementing travel expenses** (likely Tier 2, multiple variants)
3. **Implementing corrections/reversals** (likely Tier 2-3)
4. **Tier 3 complex workflows** (opens Saturday — highest ceiling)

---

## Immediate Next Steps (Priority Order)

### Step 1: Create branch `tripletex_continuation`
- Branch from current main

### Step 2: Fix doc/code mismatches
- Fix README LLM reference (OpenAI, not Claude)
- Create `.env.example` with required env vars
- Update SESSION_HANDOFF.md for new ownership

### Step 3: Verify the environment works
- Confirm Python venv setup
- Run existing tests (`pytest`)
- Run linter (`ruff check`)
- Confirm the 8 existing workflows still function

### Step 4: Expand task coverage (biggest score impact)
Priority order for new workflows:
1. **Travel expenses** (create, delete) — most common gap in live traces
2. **Employee update** — extend existing EmployeeCreate
3. **Customer/Product update** — extend existing creates
4. **Corrections** (delete entities, reverse vouchers)
5. **Tier 3 tasks** when they unlock Saturday

### Step 5: Improve efficiency
- Audit unnecessary API calls in existing workflows
- Remove/isolate bank account mutation from non-send invoice paths

---

## Files to Modify

| File | Change |
|------|--------|
| `README.md` | Fix LLM reference |
| `.env.example` | Create with required vars |
| `SESSION_HANDOFF.md` | Update for new owner |
| `src/tripletex_agent/workflows/live.py` | Add travel expense + other workflows |
| `src/tripletex_agent/workflows/registry.py` | Register new workflows |
| `src/tripletex_agent/planner.py` | Extend keyword rules for new task types |
| `tests/` | Add tests for new workflows |

---

## Verification Plan

1. `pytest` — all existing tests pass
2. `ruff check` — no lint errors
3. `python scripts/smoke_read_only.py` — sandbox connectivity
4. `python scripts/run_prompt.py "test prompt"` — planner works
5. `python scripts/run_prompt.py --execute "test prompt"` — workflow executes
6. Local `/solve` endpoint test with sandbox credentials
