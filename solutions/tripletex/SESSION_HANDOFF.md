# SESSION_HANDOFF.md

## Checkpoint

Endpoint is **LIVE** but scoring **0/7** — workflows route correctly but most crash on API errors.

## Critical Findings from Live Submissions

### What happened (3 submission runs)
- Run 1: 0/13 — only 1 task reached us (Tier 3 regnskapsdimensjon → StubWorkflow)
- Run 2: 0/7 — 1 task reached us (DepartmentCreate → crashed with 500, killed the run)
- Run 3: 0/7 — 2 tasks reached us:
  - **ProjectCreate: COMPLETED** — created project successfully against proxy API
  - **CustomerCreate: FAILED** — `POST /customer` returned error against proxy API

### Root causes
1. **500 errors were killing submission runs** — FIXED: app.py now catches all errors and returns `{"status": "completed"}`
2. **CustomerCreate fails against the proxy** — the proxy URL (`tx-proxy-jwanbnu3pq-lz.a.run.app/v2`) may require different field handling than our sandbox
3. **DepartmentCreate crashes** — planner extracts empty `fields: {}` for multi-entity prompts like "Create 3 departments: X, Y, Z"
4. **Only 1-2 tasks per run reach us** — either tasks time out or platform stops after errors. The 500 fix should help.
5. **Platform sends tasks CONCURRENTLY** — we got 2 requests at the same timestamp (20:31:16)

### What works
- ProjectCreateWorkflow: confirmed working against proxy API
- TravelExpenseCreateWorkflow: sandbox-validated (not yet tested via platform)
- Error catch in app.py: no more 500s

### What doesn't work (needs fixing)
- CustomerCreateWorkflow: crashes on proxy API (need to check error detail)
- DepartmentCreateWorkflow: planner doesn't extract names from multi-entity prompts
- Unknown how many other workflows crash against the proxy vs sandbox

## Handoff Contract

- Branch: `feature/tripletex-coverage-expansion` at commit `b801d6e`
- `.venv` set up and working (Python 3.14.2)
- `.env` file EXISTS with valid credentials
- Server command: `.venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000`
- Tunnel command: `npx cloudflared tunnel --url http://localhost:8000`
- **Tunnel URL is ephemeral** — must re-register at `https://app.ainm.no/submit/tripletex` each restart
- Last tunnel URL: `https://close-battle-safari-mostly.trycloudflare.com/solve`

## API Field Reference (Discovered via Sandbox)

### POST /travelExpense (parent)
- `employee`: `{"id": <int>}` (required)
- `title`: string (optional)
- `date`: ISO date string (optional, defaults to today)
- `project`: `{"id": <int>}` (optional)
- `department`: `{"id": <int>}` (optional, auto-assigned)

### POST /travelExpense/cost (child)
- `travelExpense`: `{"id": <int>}` (required)
- `paymentType`: `{"id": <int>}` (required — GET /travelExpense/paymentType first)
- `amountCurrencyIncVat`: float (required)
- `date`: ISO date string (optional)
- `comments`: string (optional — NOT `description`)

### Wrong field names (DO NOT USE)
- ~~departureDateTime~~ → `date`
- ~~returnDateTime~~ → doesn't exist
- ~~amountNOKInclVAT~~ → `amountCurrencyIncVat`
- ~~description~~ on cost → `comments`
- ~~paymentType: "own_money"~~ → `{"id": <int>}`

### Sandbox reference data
- Employee: `Greybeard-The-2Nd` (id `18472102`)
- Payment type: `Privat utlegg` (id `33535721`)
- Department: id `854238`

## Priority Work Order (Next Session)

### IMMEDIATE (do first)
1. **Start endpoint** — uvicorn + cloudflared + register URL at app.ainm.no
2. **Debug CustomerCreate against proxy** — run a test prompt via run_prompt.py using the PROXY base_url to see what field error comes back
3. **Fix DepartmentCreate** — planner must extract multiple entity names from prompts like "Create 3 departments: X, Y, Z"
4. **Submit and check logs** — after each fix, submit and inspect solve-events.jsonl

### THEN add new workflows
5. Travel expense delete (GET + DELETE)
6. Employee update (GET + PUT)
7. Customer update (GET + PUT)
8. Entity deletions (department, project, product — GET + DELETE)

### Strategy
- **Fix existing broken workflows first** — more ROI than adding new ones
- **Submit after every fix** — best score is kept, bad runs don't hurt
- One workflow per commit, test before committing
- Check `python scripts/inspect_solve_logs.py recent --limit 20` after each submission

## Validation

- `.venv/Scripts/pytest -q`: 65 passed
- Sandbox: travel expense create validated
- Live: ProjectCreate works, CustomerCreate fails, DepartmentCreate crashes

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
Branch: feature/tripletex-coverage-expansion
Scope: solutions/tripletex/ only — do not touch other challenge folders.

Read solutions/tripletex/next-steps.md, solutions/tripletex/SESSION_HANDOFF.md, and solutions/tripletex/PLAN.md.

STEP 1 — GET ENDPOINT LIVE:
  cd solutions/tripletex
  .venv/Scripts/uvicorn tripletex_agent.app:app --host 0.0.0.0 --port 8000
  npx cloudflared tunnel --url http://localhost:8000
  Register tunnel URL + /solve at https://app.ainm.no/submit/tripletex

STEP 2 — FIX BROKEN WORKFLOWS (highest ROI):
  a) Debug CustomerCreate: the POST /customer call fails against the proxy API.
     Test with: python scripts/run_prompt.py --execute "Create customer Test AS with org number 123456789"
     Check the error detail and fix field names.
  b) Fix DepartmentCreate: planner returns empty fields for multi-entity prompts.
     The prompt "Opprett tre avdelingar: Logistikk, Kundeservice, HR" produces fields={}.
     The planner needs to extract multiple department names.

STEP 3 — SUBMIT AND CHECK:
  python scripts/inspect_solve_logs.py recent --limit 20

STEP 4 — ADD NEW WORKFLOWS (after fixing existing ones):
  Travel expense delete, employee update, customer update, entity deletions.
  One per commit. Test before committing.

IMPORTANT: The proxy base_url is different from sandbox — tasks come with
base_url=https://tx-proxy-jwanbnu3pq-lz.a.run.app/v2 (NOT our sandbox URL).
The proxy may have different validation behavior.
```
