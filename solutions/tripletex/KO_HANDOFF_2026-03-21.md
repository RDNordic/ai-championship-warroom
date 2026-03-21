# KO Handoff — 2026-03-21

## Purpose

This note is the GitHub-visible handoff for KO.

- Raw Tripletex runtime logs are **not committed** to GitHub.
- The `solutions/tripletex/logs/` directory is gitignored and exists only on the current machine.
- Use this file to understand what exists locally, what is currently proven, and where to look next across T1/T2/T3.

---

## Current Repo State

- Branch: `main`
- Current pushed fix commit: `dee2328`
- Commit message: `tripletex: prefer order-invoice-payment fallback plan`

What that fix does:

- It changes the Tripletex planner fallback behavior so that when the primary planner reduces an `order -> invoice -> payment` prompt to plain `register_payment`, the richer keyword plan is preferred instead.
- This directly targets the live Stormberg-style failure where order creation and invoice conversion were lost.

---

## Tripletex (T1) — Current Status

### Runtime

- Active public endpoint at time of writing:
  - `https://own-mentor-focal-reactions.trycloudflare.com/solve`
- Active local port:
  - `8003`
- Current public state file path:
  - `solutions/tripletex/logs/public-endpoint-state-8003.json`

### Important: Logs Are Local Only

These are **not in GitHub** and must be shared out-of-band if KO needs the raw files:

- `solutions/tripletex/logs/solve-events.jsonl`
- `solutions/tripletex/logs/public-uvicorn-8003.log`
- `solutions/tripletex/logs/public-supervisor-8003.stdout.log`
- `solutions/tripletex/logs/public-cloudflared-8003.log`
- `solutions/tripletex/logs/public-endpoint-state-8003.json`

### What Is Proven Locally Right Now

Local gate on current code:

```powershell
cd solutions/tripletex
.\.venv\Scripts\python.exe -m pytest -q tests\test_planner.py tests\test_workflows.py tests\test_api_call_planner.py --basetemp "C:\Users\John Brown\.codex\memories\tripletex-pytest-run"
.\.venv\Scripts\python.exe scripts\replay_prompt_fixtures.py --keyword-only
```

Current result on the latest fix:

- `67 passed`
- replay fixtures pass for:
  - invoice create/send
  - invoice payment
  - travel expense creation
  - voucher reversal lookup extraction
  - supplier registration
  - supplier invoice containment
  - project lifecycle fail-closed
  - month-end fail-closed
  - employee PDF onboarding fail-closed

### Most Important Recent Tripletex Findings

1. Stale worker issue was real.
   - Earlier submissions were hitting old runtime behavior.
   - The public worker has since been restarted onto current local code.

2. One failed submission was only a malformed endpoint path.
   - The request hit `/solve%20` instead of `/solve`.
   - That failure never reached the solver.

3. A fresh post-restart project-lifecycle prompt now fail-closes as intended.
   - Trace: `567eaaff-773b-4850-9e66-50742ee2475e`
   - Result: `StubWorkflow`
   - Meaning: the fail-closed containment for that unsupported family is now live.

4. The key remaining targeted fix was order -> invoice -> payment routing.
   - Older live misroute trace: `702235e7-9398-4473-9da3-7936ab79814c`
   - Previous bad behavior:
     - routed to `InvoicePaymentWorkflow`
     - only did `GET /customer` then `GET /invoice`
     - failed because no invoice existed yet
   - Current pushed fix `dee2328` is specifically aimed at that planner/fallback miss.

### Best Files For KO To Read In GitHub

- `solutions/tripletex/SESSION_HANDOFF.md`
- `solutions/tripletex/src/tripletex_agent/planner.py`
- `solutions/tripletex/src/tripletex_agent/workflows/live.py`
- `solutions/tripletex/tests/test_planner.py`
- `solutions/tripletex/tests/test_workflows.py`
- `solutions/tripletex/SUBMISSION_CHECKLIST.md`

### If KO Needs The Raw Local Logs

They must be copied directly from the machine, not fetched from GitHub.

Minimum useful bundle:

- `solutions/tripletex/logs/solve-events.jsonl`
- `solutions/tripletex/logs/public-uvicorn-8003.log`
- `solutions/tripletex/logs/public-endpoint-state-8003.json`

---

## Astar Island (T2) — Where KO Should Look

Owner:

- AD / Andrew

Best GitHub entry points:

- `solutions/astar-island/README.md`
- `solutions/astar-island/next-steps.md`

Short orientation:

- Predict a `40x40x6` probability tensor for each of 5 seeds.
- The hidden parameters are shared across all 5 seeds within a round.
- Query budget is `50` per round total, so query efficiency matters more than brute force.
- Cardinal rule: never submit `0.0` probability for any class in any cell.

Immediate useful questions for KO if he wants to help:

- Is the current round active?
- Are all 5 seeds being covered before optimization?
- Are priors and observation weighting being updated only from repeated analysis, not guesswork?

---

## NorgesGruppen Data (T3) — Where KO Should Look

Owner:

- Chris

Best GitHub entry points:

- `solutions/norgesgruppen-data/README.md`
- `solutions/norgesgruppen-data/DATASET.md`

Short orientation:

- Train an object detection model for grocery shelf images.
- Output is an uploaded `submission.zip`, not a hosted endpoint.
- Score is `0.7 * detection_mAP@0.5 + 0.3 * classification_mAP@0.5`.
- Hard cap: `3 submissions/day`.
- Local COCO eval is mandatory before every upload.

Immediate useful questions for KO if he wants to help:

- Is the local eval harness producing detection and classification mAP separately?
- Are training/runtime versions pinned to the sandbox versions?
- Is `submission.zip` validated with `run.py` at the zip root before upload?

---

## Suggested KO Read Order

1. `solutions/tripletex/SESSION_HANDOFF.md`
2. `solutions/tripletex/KO_HANDOFF_2026-03-21.md`
3. `solutions/astar-island/README.md`
4. `solutions/norgesgruppen-data/README.md`

---

## What Is Assumed

- Current pushed `main` reflects the desired Tripletex fix state.
- The current public endpoint in the local state file is still the live one in use.
- KO may need the raw local Tripletex logs separately if he wants trace-level detail.

## Next Highest-Priority Task

For Tripletex:

- Run one fresh submission against the current endpoint and inspect the newest trace immediately to verify whether the `order -> invoice -> payment` routing fix is now live-proven.
