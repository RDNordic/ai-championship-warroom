# Scoring

## How scoring works

### Step 1 — Correctness (0.0–1.0)

After your agent returns `{"status": "completed"}`, the scorer queries the Tripletex
API and checks specific fields field-by-field. Each check has a point value. Your
correctness score = points_earned / max_points.

Example (create employee, max 10 pts):
- Employee found: 2 pts
- Correct first name: 1 pt
- Correct last name: 1 pt
- Correct email: 1 pt
- Administrator role assigned: 5 pts

**Implication**: Some fields are worth much more than others. Missing the role
assignment on an employee task loses 5/10 = 50% of the correctness score. The high-
value checks are almost always the *action semantics* — role, send, approve, deliver —
not the basic entity fields. Never sacrifice action semantics to save API calls.

### Step 2 — Tier multiplier

| Tier | Multiplier | Example tasks |
|---|---|---|
| 1 | ×1 | Create employee, create customer, create invoice |
| 2 | ×2 | Invoice with payment, credit notes, project billing |
| 3 | ×3 | Bank reconciliation, ledger corrections, year-end |

Base score = correctness × tier multiplier.
A perfect Tier 3 task = 1.0 × 3 = 3.0 base score.

### Step 3 — Efficiency bonus (only on perfect correctness)

Only applies when correctness = 1.0. Can up to double the tier score.

Two factors:
- **Call efficiency**: your call count vs. the minimum known solution. Fewer = better.
- **Error cleanliness**: 4xx responses reduce the bonus. Zero errors = maximum bonus.

| Scenario (Tier 2) | Score |
|---|---|
| Failed all checks | 0.0 |
| 80% checks passed | 1.6 |
| Perfect, many errors/extra calls | ~2.1 |
| Perfect, efficient, few errors | ~2.6 |
| Perfect, best-in-class, zero errors | 4.0 |

Benchmarks are recalculated periodically as teams find more efficient solutions.

### Best score per task

Your score per task is your all-time best. Bad runs never lower your score.
This means: submit confidently once a workflow is correct, then optimise.

## Strategic implications

### Priority order for implementation

1. **Correctness on Tier 1 tasks first.** These are the foundation. A perfect Tier 1
   with efficiency bonus beats a partial Tier 2 every time.
2. **Action semantics are the highest-value correctness gap.** "Send", "approve",
   "deliver" — these are the checks worth the most points and the most commonly missed.
3. **Efficiency bonus is only reachable at perfect correctness.** Don't optimise
   call counts until the workflow is correct. Sequence: correct → efficient.
4. **Tier 3 has the highest ceiling but highest risk.** A partially-correct Tier 3
   (e.g. 0.6 correctness) scores 1.8 — worse than a perfect Tier 1 (1.0) with
   efficiency bonus (~2.0). Only attempt Tier 3 workflows you can complete correctly.

### What kills the efficiency bonus

- Any 4xx response (400, 404, 422)
- Unnecessary GET calls (fetching entities whose IDs you already have)
- Spurious writes (bank account mutation on invoice create)
- Multiple attempts at the same call (trial-and-error)

### What the scorer actually checks

We don't know the exact check list for every task type, but from the docs and logs:

**Confirmed scorer checks:**
- Entity exists (found by query after submission)
- Specific field values (name, email, amount, date)
- Action outcomes (invoice sent, employee has role, expense approved)

**Inferred high-value checks (based on scoring structure):**
- Role/entitlement assignment on employee tasks
- `sendToCustomer` outcome on invoice tasks
- Approval status on supplier invoice tasks
- Delivery status on travel expense tasks
- Correct amounts (VAT-inclusive vs exclusive matters)

### Rate limits

| Limit | Verified teams |
|---|---|
| Concurrent submissions | 3 |
| Per task per day | 10 |

10 submissions per task per day is enough to iterate, but not enough to trial-and-error.
Every submission must be a deliberate improvement over the last.

## Task distribution

Each submission receives one task, weighted toward tasks you've attempted less.
Over many submissions you'll encounter all 30 task types.

56 variants per task type (7 languages × 8 data sets). You will rarely see the same
prompt twice. Your implementation must be parametric — never hardcode entity names,
amounts, or dates that appeared in test runs.

## Submission checklist (fast version)

Before any competition submission:
1. Run the relevant workflow against the sandbox with a similar prompt
2. Verify the exact postcondition in the sandbox (not just HTTP 200)
3. Confirm no spurious API calls in the trace
4. Submit
