# SESSION_HANDOFF.md

## Current State

Last known leaderboard snapshot:
- Score: `5.0`
- Rank: `#221`
- Solved: `11/30`

Branch: `feature/tripletex-multiline-invoice`
HEAD commit: `1429bb9`
Working tree: dirty, with local uncommitted Tripletex changes

Uncommitted files:
- `solutions/tripletex/SESSION_HANDOFF.md`
- `solutions/tripletex/scripts/run_prompt.py`
- `solutions/tripletex/src/tripletex_agent/planner.py`
- `solutions/tripletex/src/tripletex_agent/service.py`
- `solutions/tripletex/src/tripletex_agent/workflows/__init__.py`
- `solutions/tripletex/src/tripletex_agent/workflows/live.py`
- `solutions/tripletex/tests/test_planner.py`
- `solutions/tripletex/tests/test_workflows.py`

Unrelated change still present:
- `solutions/astar-island/next-steps.md`

---

## Critical Bug Discovered This Session — Fix Before Anything Else

**The OpenAI model name in config is `gpt-5-mini`. That model does not exist.**

The actual model is `gpt-4o-mini`. This means every LLM planner call is failing silently
and the system has been running entirely on the `KeywordTaskPlanner` fallback — no LLM
extraction at all. This is almost certainly responsible for multiple recent failures.

**Fix in `config.py` or `.env` immediately:**
```python
openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini")
api_call_plan_model=os.getenv("API_CALL_PLAN_MODEL", "gpt-4o-mini")
```

Verify the fix worked by checking that a complex prompt produces a richer plan than
the keyword fallback would generate (e.g. multi-field extraction, not just task_family).

---

## Architecture Review This Session

This session included a full external architecture review against a set of framework
documents built from scratch based on the OpenAPI spec, live logs, and hackathon rules.
The documents are in `docs/` — read them before coding. See "New Framework Documents"
section below for what was added and where.

### What the review found

**Architecture is correct and should not be rewritten.** The planner→workflow separation,
`TaskPlan` schema, `FallbackPlanner`, and workflow implementations are all sound. The code
is better than expected. Do not start from scratch.

**The five real problems, in priority order:**

1. **Wrong model name** — `gpt-5-mini` doesn't exist. All LLM calls are failing. (See above.)
2. **No `temperature=0`** — Both `responses.parse()` calls in `OpenAIPlanner` and
   `OpenAIApiCallPlanner` have no `temperature` parameter. Default is non-zero, causing
   non-determinism. Identical prompts produce different plans. One-line fix each.
3. **Voucher reversal planner doesn't populate lookup** — `VoucherReverseWorkflow` has the
   correct customer→invoice→voucher chain (Path 3 in `_find_single_voucher`), but the
   planner's `_lookup_for_extraction` for `entity_type="voucher"` returns `{}` because
   there is no voucher-specific extraction. Customer name and org number from the prompt
   never reach the workflow. Fix: when `primary_entity_type == "voucher"` and
   `operation == "reverse"`, extract customer name + org number into the lookup dict
   with keys `name` and `organizationNumber`.
4. **Bank account mutation on every send-invoice** — `_ensure_invoice_bank_account_configured`
   fires `GET /ledger/account` on every `sendToCustomer=True` call, and `PUT /ledger/account`
   if no bank number is set. The GET alone costs the efficiency bonus. Test whether invoices
   succeed without this function entirely — if the sandbox already has a configured bank
   account, remove the call.
5. **Department multi-name extraction missing from keyword fallback** — The `names: list[str]`
   field exists in `DepartmentExtraction` and `DepartmentCreateWorkflow` handles it correctly,
   but `_extract_department_payload` only extracts a single `name`. When the LLM path fails
   (which it always has, due to wrong model name), multi-department prompts produce
   `fields: {}` and the workflow throws. Fix the keyword extractor to parse comma/og/and
   separated quoted department names into the `names` list.

---

## What Is Live-Proven (Carry Forward)

These paths were confirmed working on the live public endpoint before this session:

1. **Invoice payment (VAT gross-up)** — Amount stated excluding VAT is correctly grossed
   up against `amountOutstanding` before `PUT /invoice/{id}/:payment`. Confirmed on
   Solmar SL (46700 NOK sin IVA → 58375 gross) and Río Verde SL (22500 → 28125).

2. **Invoice create-and-send** — `sendToCustomer=True` correctly set. Confirmed on
   Fjelltopp AS (Nynorsk prompt).

3. **Travel expense create** — Employee lookup, parent expense, and cost sub-resources
   all working. Confirmed on William Wilson (EN prompt, flight + taxi + per diem).

4. **Customer create** — Stable. Address fields, language, org number all working.

5. **Product create** — Stable. Name, number, price all working.

6. **Project create** — Customer lookup + project manager lookup + POST confirmed.
   German prompt (Windkraft GmbH) confirmed working.

---

## What Is Locally Patched But Not Yet Live-Proven

1. **Supplier registration** — `isSupplier=true`, `isCustomer=false` now set in planner.
   Customer workflow forwards flags. Not yet confirmed on live endpoint after restart.

2. **Supplier invoice containment** — Supplier invoice prompts now tagged `supplierInvoice=true`
   and routed to StubWorkflow rather than misfiring into outgoing invoice path. Not yet
   live-confirmed.

3. **Order → invoice → payment** — `OrderInvoicePaymentWorkflow` is implemented and
   mock-tested. Not yet live-proven.

---

## What Is Still Broken / Stubbed

From log analysis (31 traces reviewed this session):

| Task | Status | Root cause |
|---|---|---|
| Voucher reversal (bounced payment) | BROKEN | Planner lookup empty — see fix #3 above |
| Department create (multi-dept) | BROKEN | Keyword extractor doesn't parse `names` list |
| Supplier invoice (POST) | STUB | Not implemented, only contained |
| Timesheet entry | STUB | StubWorkflow |
| Set project fixed price | STUB | StubWorkflow |
| Accounting dimension + voucher | STUB | Not classified (0.0 conf) |
| Month-end closing | STUB | Misclassified as invoicing, Tier 3 |
| Full project lifecycle | STUB | Not classified (0.0 conf), Tier 3 |
| Employee from PDF | BROKEN | PDF extraction not implemented |

---

## New Framework Documents Added This Session

A full set of architecture/domain docs was created and should be added to the repo.
See "Merging Framework Documents" section below for how to handle conflicts.

Documents created:
- `docs/ARCHITECTURE.md` — System design, planner→workflow separation, retry logic,
  TaskPlan schema, the three prompt-handling layers
- `docs/TRIPLETEX_DOMAIN.md` — Domain context block (inject into LLM system prompt),
  invoice type distinctions, voucher lifecycle, travel expense state machine, Norwegian
  terminology, multilingual action semantics
- `docs/SCORING.md` — Scoring mechanics, tier multipliers, efficiency bonus rules,
  strategic priority order
- `docs/WORKFLOWS.md` — Per-family workflow specs with confidence levels (✅/🔶/❓),
  API sequences, known failure modes, postcondition checks
- `docs/TASK_COVERAGE.md` — Living coverage matrix of all 31 observed task types,
  priority implementation order, confirmed bugs from log analysis
- `docs/TESTING_RIG.md` — Sandbox reset strategy, prompt library design, integration
  test runner, attachment fixture generation

`CLAUDE.md` (repo root for the tripletex folder) was also created — Claude Code reads
this automatically. Contains the must-never-break rules, repo layout, current known gaps,
and pointers to all docs.

---

## Merging Framework Documents

The repo already has `PLAN.md`, `docs.md`, and `session_archive/` checkpoint files.
The new docs don't replace these — they complement and extend them.

**Recommended approach:**

1. Keep `PLAN.md` as the operational log it already is (evidence-updated, date-stamped).
   Do not replace it. Append a section `## 2026-03-21 Architecture Review` that links
   to the new docs and summarises the five critical findings above.

2. Add the new `docs/` files alongside whatever is already there. If `docs/` doesn't
   exist yet, create it. If architecture files already exist there, rename the old ones
   with a `-legacy` suffix or move them to `session_archive/` with a date prefix before
   adding the new ones. Do not silently overwrite — the old files may have context
   not captured in the new ones.

3. Add `CLAUDE.md` at the `solutions/tripletex/` root. Claude Code reads this
   automatically on every session. If a `CLAUDE.md` already exists, merge the contents
   — don't overwrite.

4. Commit everything together as a single commit with message:
   `docs: add architecture framework from 2026-03-21 review session`

---

## Runtime Status

At last handoff:
- Local health `http://127.0.0.1:8000/health`: `200`
- Public endpoint: `https://newspapers-reform-walking-embassy.trycloudflare.com/solve`
- Public health: `200`
- 54 targeted tests passing (`test_planner.py`, `test_workflows.py`)
- Full pytest blocked by Windows temp ACL issue (`.tmp`, `.pytest-tmp` folders)

Latest live failure traces:
- Voucher reversal: `44e888d3` — empty lookup, workflow dies before first API call
- Proxy 403: `77082f85` — transient, same endpoint worked in same window

---

## Immediate Next Steps (Ordered)

**Do these before any competition submission:**

```
1. Fix model name: gpt-5-mini → gpt-4o-mini in config.py or .env
   Verify: run a complex prompt through run_prompt.py and confirm LLM extraction works

2. Add temperature=0 to both responses.parse() calls:
   - planner.py: OpenAIPlanner.plan()
   - api_call_planner.py: OpenAIApiCallPlanner.plan()

3. Fix voucher reversal planner extraction:
   - When primary_entity_type == "voucher" and operation == "reverse"
   - Extract customer name + org number from prompt into lookup dict
   - Keys: "name" and "organizationNumber"
   - The workflow's Path 3 lookup chain already handles these correctly

4. Run narrow test gate:
   .venv/Scripts/pytest -q tests/test_planner.py tests/test_workflows.py

5. Submit once, inspect logs immediately
   - Watch for voucher reversal prompt — should now reach Path 3 lookup
   - Watch for any LLM extraction evidence in planned events (richer than keyword output)
```

**After confirming fixes work on live:**

```
6. Fix bank account mutation:
   - Test POST /invoice?sendToCustomer=true in sandbox WITHOUT _ensure_invoice_bank_account_configured
   - If it works, remove the GET /ledger/account + PUT /ledger/account calls entirely
   - This recovers the efficiency bonus on all send-invoice tasks

7. Fix department multi-name extraction in keyword fallback:
   - _extract_department_payload should parse comma/og/and separated quoted names
   - Populate the "names" list field, not just "name"

8. Implement supplier invoice workflow:
   - POST /incomingInvoice or /supplierInvoice
   - Approval → payment chain
   - Currently only contained as StubWorkflow

9. Implement timesheet entry:
   - POST /timesheet/entry
   - Employee + project + activity + date + hours
   - Currently StubWorkflow

10. Add domain context block to LLM system prompt:
    - The full block is in docs/TRIPLETEX_DOMAIN.md under "System prompt context block"
    - Add it to the _SYSTEM_PROMPT string in planner.py
    - This hardens description vs productLookup, invoice type disambiguation,
      multilingual action semantics, and Norwegian terminology
```

**Consider for Tier 3 (only after Tier 1/2 stable):**
- Accounting dimension + voucher (`/ledger/accountingDimensionName` + `/ledger/voucher`)
- Bank reconciliation from CSV attachment

---

## Key Files

- Planner: `src/tripletex_agent/planner.py`
  - `OpenAIPlanner.plan()` — add `temperature=0`, fix model name
  - `_SYSTEM_PROMPT` — add domain context block from `docs/TRIPLETEX_DOMAIN.md`
  - `_lookup_for_extraction` — fix voucher lookup population
- Workflows: `src/tripletex_agent/workflows/live.py`
  - `_ensure_invoice_bank_account_configured` — remove or gate more tightly
  - `VoucherReverseWorkflow` — already correct, needs planner fix to feed it
- Config: `src/tripletex_agent/config.py` — fix model name default
- `.env` — check `OPENAI_MODEL` value
- New docs: `docs/ARCHITECTURE.md`, `docs/TRIPLETEX_DOMAIN.md`, `docs/SCORING.md`,
  `docs/WORKFLOWS.md`, `docs/TASK_COVERAGE.md`, `docs/TESTING_RIG.md`
- New root context: `CLAUDE.md`
- Logs: `logs/solve-events.jsonl` (31 traces analysed this session)
- Tests: `tests/test_planner.py`, `tests/test_workflows.py`

---

## Restart Prompt for Claude Code

```text
Branch: feature/tripletex-multiline-invoice
HEAD: 1429bb9
Working tree is dirty. Read SESSION_HANDOFF.md and docs/CLAUDE.md first.

CRITICAL: The OpenAI model name in config is "gpt-5-mini" which doesn't exist.
Fix to "gpt-4o-mini" before anything else. This has been silently breaking all
LLM extraction — the system has been running on keyword fallback only.

After fixing the model name, the next three fixes in order:
1. Add temperature=0 to both responses.parse() calls in planner.py and api_call_planner.py
2. Fix voucher reversal planner lookup (see SESSION_HANDOFF.md fix #3)
3. Run pytest -q tests/test_planner.py tests/test_workflows.py

Do not submit to the competition until all three are done and tests pass.

What is live-proven working: invoice payment (VAT gross-up), invoice create-and-send,
travel expense create, customer create, product create, project create.

What is broken: voucher reversal (empty lookup), department create (multi-name),
supplier invoice (only contained), PDF extraction (not implemented).

New architecture docs are in docs/ — these are the ground truth for design decisions.
PLAN.md remains the operational log — append to it, do not replace it.
```