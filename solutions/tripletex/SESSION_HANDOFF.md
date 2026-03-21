# SESSION_HANDOFF.md

## Read This First

This is now the single authoritative Tripletex handoff.

- Read this file first in the next chat.
- `solutions/tripletex/next-steps.md` is intentionally only a pointer to this file.
- Do not spend another submission until the public worker has been restarted onto current local code.

## Current State

- Date: `2026-03-21`
- Repo branch: `main`
- Working tree: dirty, with uncommitted Tripletex changes
- Last older confirmed leaderboard snapshot:
  - score `5.0`
  - rank `#221`
  - solved `11/30`
- Latest later user-reported submission outcomes on `2026-03-21` Oslo time:
  - `0/14`
  - `0/8`

## Runtime Status

- Current supervisor state file says the active public endpoint is:
  - `https://concerts-remarks-carol-display.trycloudflare.com/solve`
- Supervisor state file:
  - `solutions/tripletex/logs/public-endpoint-state-8003.json`
- Supervisor log:
  - `solutions/tripletex/logs/public-supervisor-8003.stdout.log`
- Live service log:
  - `solutions/tripletex/logs/public-uvicorn-8003.log`
- Solve trace log:
  - `solutions/tripletex/logs/solve-events.jsonl`

Important:

- the tunnel is not the current blocker
- the current blocker is stale deployed runtime behavior
- the currently running public worker is behind the current local code

## What Is Proven Locally

Current narrow gate:

```powershell
cd solutions/tripletex
.\.venv\Scripts\python.exe -m pytest -q tests\test_planner.py tests\test_workflows.py tests\test_api_call_planner.py --basetemp "C:\Users\John Brown\.codex\memories\tripletex-pytest-run"
.\.venv\Scripts\python.exe scripts\replay_prompt_fixtures.py --keyword-only
```

Results:

- `66 passed`
- replay fixtures pass for:
  - supplier invoice containment
  - voucher reversal lookup extraction
  - project-lifecycle fail-closed
  - month-end fail-closed
  - attachment-led employee onboarding fail-closed

Local planner behavior now intentionally fail-closes these unsupported families:

1. project lifecycle / project delivery compound prompts
2. month-end / period-close prompts
3. attachment-led employee onboarding prompts that depend on PDF offer-letter contents

Practical meaning:

- these families should now route to `unknown` / `StubWorkflow`
- they should not hit live write workflows on the current local code

## What Is Still Live-Proven Good

1. Invoice payment with amount stated excluding VAT
2. Invoice create-and-send
3. Travel expense creation
4. Basic customer creation
5. Basic product creation

These were proven in earlier live traces and are still the stable base.

## Most Important New Live Traces

### 1. Employee Onboarding Via PDF Hit Old Worker Behavior

- `trace_id=c24268f2-b7c5-4fb8-9ce7-db3525b2770a`
- received at `2026-03-21 13:48` Oslo time

Prompt family:

- Portuguese
- attachment-led employee onboarding
- PDF offer letter referenced
- create employee
- assign department
- configure employment percentage
- configure annual salary
- configure standard working hours

Observed live behavior:

- planned to `EmployeeCreateWorkflow`
- extracted only a generic `comments` field about the PDF
- failed before any Tripletex API call with:
  - `Employee creation requires firstName`

Meaning:

- the public worker was still serving old code after the local fail-closed patch existed
- this is direct evidence of stale runtime, not just a planner-quality problem

### 2. Order -> Invoice -> Payment Still Misroutes Live

- `trace_id=702235e7-9398-4473-9da3-7936ab79814c`
- received at `2026-03-21 14:00` Oslo time

Prompt:

```text
Opprett en ordre for kunden Stormberg AS (org.nr 870531559) med produktene Vedlikehold (4665) til 35200 kr og Systemutvikling (7431) til 4400 kr. Konverter ordren til faktura og registrer full betaling.
```

Observed live behavior:

- planned to `InvoicePaymentWorkflow`
- operation became `register_payment`
- order creation and invoice creation steps were lost
- API calls:
  - `GET /customer` -> matched Stormberg AS
  - `GET /invoice` -> no results
- failed with:
  - `No invoice matched lookup {'customerLookup': {'customerName': 'Stormberg AS', 'organizationNumber': '870531559'}}`

Meaning:

- `order -> invoice -> payment` is still not live-proven
- the live worker did not use the intended local route for this family
- this is another sign the public worker is stale

### 3. Older But Still Relevant Live Traces

- `8ce83963-d7d7-4d55-ae1d-ecdd2e5d18e7`
  - French project-lifecycle prompt
  - old live worker degraded into invoice/supplier containment
- `68855094-7ec9-4302-8da7-576c0afa7b6b`
  - German month-end close
  - old live worker degraded into `InvoiceCreateWorkflow`
- `44e888d3-38c8-4b46-94d9-352b2280b179`
  - voucher reversal
  - old live worker lost lookup and failed before Tripletex API call

These are still relevant as regression targets, but the immediate operational issue is stale deployment.

## Current Highest-Priority Problems

1. The live public worker is stale.
2. The latest submissions were spent against code that does not match current local patches.
3. `order -> invoice -> payment` still is not live-proven.
4. Voucher reversal is still only partially validated live.
5. Attachment/PDF tasks are only contained, not solved.

## Current Objective

Do not do more local planner work first.

The next objective is:

1. restart the public worker onto the current local code
2. re-check local and public health
3. submit once
4. inspect `solve-events.jsonl` immediately

## What The Next Submission Must Validate

On the first fresh post-restart traces, verify:

1. employee PDF onboarding now fails closed to `unknown` / `StubWorkflow`
2. project-lifecycle prompts fail closed
3. month-end close prompts fail closed
4. `order -> invoice -> payment` routes to `OrderInvoicePaymentWorkflow`

If `order -> invoice -> payment` still misroutes after restart, then it becomes the next code-fix target.

## Recommended Action Sequence

1. Restart the public worker.
   - Do not assume the current uvicorn process picked up local edits.

2. Re-check health.

```powershell
Invoke-WebRequest http://127.0.0.1:8003/health
Invoke-WebRequest https://concerts-remarks-carol-display.trycloudflare.com/health
```

3. Re-run the narrow local gate if needed.

4. Submit once.

5. Inspect logs immediately.

```powershell
cd solutions/tripletex
.\.venv\Scripts\python.exe scripts\inspect_solve_logs.py recent --limit 20
Get-Content logs\public-uvicorn-8003.log -Tail 120
```

## Key Files

- planner: `solutions/tripletex/src/tripletex_agent/planner.py`
- workflows: `solutions/tripletex/src/tripletex_agent/workflows/live.py`
- service: `solutions/tripletex/src/tripletex_agent/service.py`
- replay harness: `solutions/tripletex/scripts/replay_prompt_fixtures.py`
- replay fixtures: `solutions/tripletex/fixtures/replay_prompt_fixtures.json`
- public endpoint supervisor: `solutions/tripletex/scripts/run_public_endpoint.py`
- solve trace log: `solutions/tripletex/logs/solve-events.jsonl`
- live service log: `solutions/tripletex/logs/public-uvicorn-8003.log`

## What Is Assumed

- the current tunnel URL remains live until the current `cloudflared` process dies
- the current local code is the desired version to deploy
- the stale behavior is from an old worker process, not from missing local edits

## Do Not Spend Time On

- blaming the tunnel by default
- broad new unsupported feature work before restarting the worker
- implementing full PDF extraction right now
- reading both handoff files; this file is enough

## Restart Prompt

```text
Read solutions/tripletex/SESSION_HANDOFF.md first. Do not read next-steps.md for detail; it is only a pointer.

Current state:
- Latest later user-reported runs on 2026-03-21 Oslo time: 0/14, then 0/8
- Current public endpoint in the supervisor state file:
  https://concerts-remarks-carol-display.trycloudflare.com/solve
- Tunnel health is not the blocker
- The blocker is stale public worker behavior relative to local code
- Local narrow gate passes with 66 tests
- Local replay fixtures pass for:
  - project lifecycle fail-closed
  - month-end fail-closed
  - employee PDF onboarding fail-closed

Most important live traces:
- c24268f2-b7c5-4fb8-9ce7-db3525b2770a
  - Portuguese PDF-led employee onboarding
  - live worker routed to EmployeeCreateWorkflow
  - failed with Employee creation requires firstName

- 702235e7-9398-4473-9da3-7936ab79814c
  - Norwegian order -> invoice -> payment
  - live worker routed to InvoicePaymentWorkflow
  - it only did GET /customer then GET /invoice
  - failed with No invoice matched lookup ...

Goal for this chat:
- restart the public worker onto current local code
- re-check health
- submit once
- inspect fresh traces immediately
- confirm whether:
  - employee PDF onboarding now fails closed
  - project/month-end now fail closed
  - order -> invoice -> payment routes to OrderInvoicePaymentWorkflow
```
