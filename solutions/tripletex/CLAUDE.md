# Tripletex Hackathon — Claude Code Context

## What this project is

A competitive hackathon agent that exposes a `POST /solve` endpoint. The endpoint
receives a natural language prompt (in one of 7 languages), optional file attachments,
and Tripletex API credentials. It must interpret the prompt and execute the correct
sequence of Tripletex API calls to complete the accounting task described.

Scoring is automated and field-by-field. Every unnecessary API call and every 4xx
error directly reduces the score. Correctness comes first, efficiency second.

## Must-never-break rules

1. **All Tripletex API calls must use the `base_url` from the request body**, not any
   hardcoded URL. The competition routes calls through an authenticated proxy.
2. **LLM temperature must be 0** for the planner. Non-determinism has caused identical
   prompts to produce different plans and different outcomes.
3. **No free-form API sequencing by the LLM.** The LLM extracts intent and fields.
   Deterministic workflow handlers decide which endpoints to call and in what order.
4. **No speculative writes.** Never mutate data that the prompt did not ask to change.
   The bank-account bootstrap in the invoice workflow is a known violation of this rule
   — it must be removed.
5. **No 4xx errors accepted as normal.** Every 4xx is a scoring regression. Validate
   locally before writing.
6. **Action semantics must survive extraction.** "Create and send" is not the same as
   "create". "Approve" is not the same as "deliver". The planner must capture these
   distinctions explicitly and the workflow must act on them.

## Repo layout (expected)

```
solutions/tripletex/
  src/tripletex_agent/
    app.py                  # FastAPI entrypoint, POST /solve
    planner.py              # LLM-backed structured extraction → TaskPlan
    workflows/
      live.py               # Workflow dispatch and execution
      invoice.py            # Invoice family workflows
      employee.py           # Employee family workflows
      customer.py           # Customer/product family workflows
      travel_expense.py     # Travel expense workflows (currently stubbed)
      project.py            # Project workflows
      correction.py         # Delete/reverse workflows
    client.py               # Tripletex API client (auth, retries, helpers)
    models.py               # TaskPlan schema and related types
    log_analysis.py         # Trace parsing and prompt mining
  tests/
  scripts/
    run_prompt.py           # Local test runner
    inspect_solve_logs.py   # Log analysis CLI
    reset_sandbox.py        # Sandbox reset harness (to be built)
  logs/
    solve-events.jsonl      # Live submission traces
  docs/                     # All architecture docs (read these first)
```

## Key reference documents — read before coding

- `docs/ARCHITECTURE.md` — system design, planner→workflow separation, retry logic
- `docs/TRIPLETEX_DOMAIN.md` — domain rules, invoice types, voucher lifecycle,
  Norwegian terminology, intent→endpoint mapping
- `docs/SCORING.md` — how the competition scores, what costs points, tier priorities
- `docs/WORKFLOWS.md` — per-family workflow specs and known failure modes
- `docs/TASK_COVERAGE.md` — what tasks we know about, observed vs inferred vs unknown
- `docs/TESTING_RIG.md` — sandbox testing architecture and reset strategy

## Tech stack

- Python, FastAPI, uvicorn
- Anthropic API (`claude-sonnet-4-6`, structured output / tool use)
- `httpx` or `requests` for Tripletex API calls
- Basic Auth: username `0`, password = `session_token` from request

## Current known gaps (as of last update)

- Travel expense workflow is `StubWorkflow` — returns completed without executing
- Invoice workflow unconditionally sets `sendToCustomer=False` regardless of prompt
- Invoice workflow fires `GET /ledger/account` + `PUT /ledger/account/{id}` on every
  run — spurious side effect, costs efficiency bonus
- Planner non-deterministically treats invoice line subjects as `productLookup` vs
  free-text `description` — fixed in domain context block but needs temp=0 enforcement
- No Tier 3 workflow implementations exist yet

## Languages the agent must handle

Norwegian Bokmål (nb), Norwegian Nynorsk (nn), English (en), French (fr),
German (de), Spanish (es), Portuguese (pt)

The LLM handles multilingual understanding natively. Keyword/regex fallback layers
in the planner must not be English/Norwegian-only.
