# Task Coverage

The competition has 30 task types across 3 tiers. We do not have the full list.
This document tracks what we know, from what source, and our implementation status.

**Update this file after every submission batch.**

---

## Coverage confidence levels

- ✅ **Observed** — received in a real competition submission log
- 📄 **Named in docs** — explicitly mentioned in hackathon documentation as an example
- 🔍 **Inferred** — strongly implied by the API surface and task structure
- ❓ **Unknown** — guessed or not yet encountered

## Status levels

- 🟢 **Working** — confirmed correct in sandbox, no known gaps
- 🟡 **Partial** — implemented but known correctness gaps
- 🔴 **Stub** — returns completed without executing
- ⬜ **Not started** — no implementation

---

## Tier 1 — foundational tasks (×1 multiplier)

| # | Task | Evidence | Status | Notes |
|---|---|---|---|---|
| 1 | Create customer | ✅ Observed (trace 4d8fdcf5) | 🟢 Working | Language field confirmed |
| 2 | Create employee | 📄 Named in docs | 🟡 Partial | Entitlement/role assignment needs verification |
| 3 | Create invoice | ✅ Observed (multiple traces) | 🟡 Partial | send intent gap fixed in context block; bank mutation still present |
| 4 | Create product | 🔍 Inferred | ⬜ Not started | Likely straightforward POST |
| 5 | Create department | 🔍 Inferred | ⬜ Not started | May need module enable |
| 6 | Update customer | 🔍 Inferred | ⬜ Not started | GET → PUT pattern |
| 7 | Update employee | 🔍 Inferred | ⬜ Not started | Role/entitlement changes likely |
| 8 | Create project | ✅ Observed (trace b5da5c8c) | 🟢 Working | Customer + manager lookup confirmed |

*Remaining Tier 1 slots (up to ~10 total): unknown.*

---

## Tier 2 — multi-step workflows (×2 multiplier)

| # | Task | Evidence | Status | Notes |
|---|---|---|---|---|
| T2-1 | Create and send invoice | ✅ Observed (traces 251c548b, 6c15b5a1) | 🟡 Partial | sendToCustomer now in context block; needs workflow fix |
| T2-2 | Invoice with payment | 📄 Named in docs | ⬜ Not started | paymentTypeId resolution needed |
| T2-3 | Credit note | 📄 Named in docs | ⬜ Not started | createCreditNote endpoint known |
| T2-4 | Project billing | 📄 Named in docs | ⬜ Not started | Unknown exact flow |
| T2-5 | Travel expense create | ✅ Observed (trace c903bd9c) | 🔴 Stub | **Active scoring gap. Priority.** |
| T2-6 | Supplier invoice | 🔍 Inferred | ⬜ Not started | Approval workflow needed |
| T2-7 | Employee with role | 🔍 Inferred | 🟡 Partial | Entitlement template call may be missing |
| T2-8 | Delete/reverse entity | 📄 Named in docs | ⬜ Not started | Dependency order matters |

*Remaining Tier 2 slots (up to ~10 total): unknown.*

---

## Tier 3 — complex scenarios (×3 multiplier, opens Saturday)

| # | Task | Evidence | Status | Notes |
|---|---|---|---|---|
| T3-1 | Bank reconciliation from CSV | 📄 Named in docs | ⬜ Not started | File attachment + reconciliation API |
| T3-2 | Ledger error correction | 📄 Named in docs | ⬜ Not started | Voucher reversal likely |
| T3-3 | Year-end closing | 📄 Named in docs | ⬜ Not started | High risk, unknown requirements |
| T3-4–10 | Unknown | ❓ | ⬜ Not started | — |

**Recommendation:** Only attempt T3-1 (bank reconciliation) if Tier 1/2 are solid.
T3-3 (year-end) is likely a trap — skip until explicit examples are observed.

---

## Priority implementation order

Based on scoring impact (correctness × tier multiplier × likelihood of being assigned):

1. **Fix invoice send intent** — Tier 1/2, already being assigned, known gap
2. **Fix bank account mutation on invoice** — affects efficiency bonus on all invoices
3. **Implement travel expense workflow** — Tier 2, already assigned, scoring 0
4. **Verify employee entitlement assignment** — Tier 1/2, likely high-point check
5. **Implement invoice payment** — Tier 2, named in docs, likely common
6. **Implement credit note** — Tier 2, named in docs
7. **Implement product create** — Tier 1, likely assigned eventually
8. **Investigate bank reconciliation** — Tier 3, highest ceiling

---

## Observed prompt patterns

Updated from `logs/solve-events.jsonl`. Add new entries after each submission batch.

| Trace | Language | Task | Outcome | Key learning |
|---|---|---|---|---|
| 4d8fdcf5 | EN | Customer create | UNKNOWN (201 returned) | Language=EN extraction works |
| c3ba0a55 | FR | Invoice create (no send) | UNKNOWN (201 returned) | Bank mutation present; orgNumber lookup works |
| 445ed1db | FR | Invoice create-and-send | FAILED | productLookup vs description ambiguity |
| 0bb865cf | FR | Invoice create-and-send | FAILED | Same as above, second attempt |
| 251c548b | FR | Invoice create-and-send | UNKNOWN (201 returned) | Fixed to use description; sendToCustomer=true |
| c903bd9c | ES | Travel expense create | UNKNOWN (no calls) | StubWorkflow — 0 points |
| 6c15b5a1 | FR | Invoice create-and-send | UNKNOWN (201 returned) | sendToCustomer=true working |
| b5da5c8c | DE | Project create | UNKNOWN (201 returned) | Customer + manager lookup working |

---

## What we still don't know

- Exact task list for all 30 types
- Point breakdown for Tier 2 and Tier 3 tasks (only Tier 1 example given in docs)
- Which specific entitlement template names the scorer expects for employee roles
- Which paymentTypeId values exist in competition sandbox
- Whether travel expense scorer checks delivery/approval status or just creation
- Full Tier 3 task requirements
- Whether any tasks require enabling company modules (`/company/salesmodules`)
