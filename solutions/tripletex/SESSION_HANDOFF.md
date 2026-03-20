# SESSION_HANDOFF.md

## Current State

**Score: 5.0 — Rank #221 — 11/30 tasks solved**
**Branch: `feature/tripletex-multiline-invoice`** (not yet merged to main)
**Last commit: `379338d`**

---

## What's Running

- Server: `.venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000`
- Tunnel: `npx cloudflared tunnel --url http://localhost:8000`
- Last tunnel URL: `https://silence-reggae-cause-gained.trycloudflare.com/solve` (**ephemeral — will change**)
- Register URL at: `https://app.ainm.no/submit/tripletex`

---

## Workflows (20 total)

### Working / Confirmed
| Workflow | Status |
|---|---|
| CustomerCreate | Fixed (isCustomer removed) |
| CustomerUpdate | Coded |
| CustomerDelete | Coded |
| ProductCreate | Live |
| ProductDelete | Coded |
| EmployeeCreate | Live |
| EmployeeUpdate | Coded |
| DepartmentCreate | Fixed (multi-entity names[]) |
| DepartmentDelete | Coded |
| ProjectCreate | Confirmed live |
| ProjectDelete | Coded |
| InvoiceCreate+Send | Live, multi-line + VAT added this session |
| InvoicePayment | Live |
| InvoiceCreditNote | Live |
| TravelExpenseCreate | Sandbox validated |
| TravelExpenseDelete | Coded |
| VoucherReverse | Fixed (customer→invoice→voucher path) |

---

## Tasks Seen From Platform (Real Competition Prompts)

| Prompt type | Our handling | Notes |
|---|---|---|
| CustomerCreate (DE/ES/FR) | ✓ Working | 8/8 checks passed |
| ProjectCreate (FR, basic) | ✓ Runs | Partial — misses fixed price/milestone |
| DepartmentCreate (3 depts, Nynorsk) | ✓ Fixed | names[] loop |
| Invoice multi-line + VAT (NO) | ✓ NEW — untested live | lines[] + vatPercent added |
| Payment reversal (ES) | ✓ Fixed | customer→invoice→voucher path |
| Order→invoice→payment (Nynorsk) | ✗ StubWorkflow | Complex 3-step, not implemented |
| Time tracking + project invoice (FR) | ✗ StubWorkflow | Tier 3, out of scope |
| Accounting dimension + voucher (NO) | ✗ StubWorkflow | Tier 3, out of scope |

---

## Highest ROI Next Work

### 1. Order→Invoice workflow (Tier 2, seen in logs)
Prompt: *"Opprett ein ordre for Strandvik AS med produkta X og Y. Konverter ordren til faktura og registrer full betaling."*
= POST /order + orderLines → PUT /order/{id}/:invoice → PUT /invoice/{id}/:payment
This is a 3-step workflow but all parts exist. High ROI.

### 2. Merge feature branch to main
`git checkout main && git merge feature/tripletex-multiline-invoice`
So Chris can pull latest.

### 3. Submit and check logs after each fix
Check: `.venv/Scripts/python scripts/inspect_solve_logs.py recent --limit 10`

---

## How to Start the Server (Windows PowerShell)

**Kill any existing process on port 8000 first:**
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Terminal 1 — server:**
```powershell
cd "c:\Users\John Brown\ai-championship-warroom\solutions\tripletex"
.venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — tunnel:**
```powershell
npx cloudflared tunnel --url http://localhost:8000
```
Copy the trycloudflare.com URL, add `/solve`, register at `https://app.ainm.no/submit/tripletex`.

---

## Key Files
- Workflows: `src/tripletex_agent/workflows/live.py`
- Planner: `src/tripletex_agent/planner.py`
- Service registry: `src/tripletex_agent/service.py`
- Logs: `logs/solve-events.jsonl`
- Tests: `.venv/Scripts/pytest -q` (65 pass)

---

## Restart Prompt for Next Session

```
Branch: feature/tripletex-multiline-invoice (or merge to main first)
Score: 5.0, rank #221, 11/30 tasks solved
Last commit: 379338d

Read solutions/tripletex/SESSION_HANDOFF.md first.

STEP 1 — merge to main if not done:
  git checkout main
  git merge feature/tripletex-multiline-invoice
  git checkout -b feature/tripletex-order-invoice

STEP 2 — kill port 8000 and start server:
  netstat -ano | findstr :8000  → taskkill /PID <X> /F
  cd solutions/tripletex
  .venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000

STEP 3 — tunnel:
  npx cloudflared tunnel --url http://localhost:8000
  Register new URL + /solve at app.ainm.no/submit/tripletex

STEP 4 — submit and check logs:
  .venv/Scripts/python scripts/inspect_solve_logs.py recent --limit 10

STEP 5 — implement Order→Invoice workflow (highest ROI unsolved task):
  POST /order with orderLines
  PUT /order/{id}/:invoice → creates invoice
  PUT /invoice/{id}/:payment → registers payment
  Keywords: "ordre", "order", "konverter", "convert to invoice"
```
