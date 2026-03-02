# SESSION_HANDOFF.md

Date: 2026-03-01 (UTC)

## Current Objective
Recover and stabilize Medium after the failed 3-item lookahead experiment, then push beyond 116 with controlled single-change tests.

## Current Best Scores (from run_history.csv)
- Easy: 110 (run `20260301_211903`)
- Medium: 116 (run `20260301_221741`)
- Hard: 71
- Expert: 60
- Current total best: 357

## What Changed This Session
### Easy (`run_easy.py`)
- End-game and delivery policy tuning was applied.
- Best recent tuned run: 109 (`20260301_220218`).

### Medium (`run_medium.py`)
Implemented sequence (one change, one run):
1. Added `random.seed(42)`.
2. Added wall caching (`self._walls`) initialized on first `decide()`.
3. Changed drop-off queue leader from `ranked[:2]` to `ranked[:1]`.
4. Changed late-game cutoff from `round_number > 270` to `round_number > 285`.
5. Widened `_is_near_delivery_path` to `via_item <= direct + 8` and Manhattan `<= 12`.
6. Added experimental 3-item BFS lookahead in `_select_target_item`.

Outcome: step 6 caused a major regression (score 11).
Action taken: step-6 lookahead has been rolled back in code (restored nearest-item `_select_target_item`).

## Latest Medium Run Outcomes
- `20260301_221440`: 52 (step 1)
- `20260301_221531`: 52 (step 2)
- `20260301_221623`: 52 (step 3)
- `20260301_221702`: 36 (step 4)
- `20260301_221741`: 116 (step 5, current best)
- `20260301_222205`: 11 (step 6 regression)

## Proven Findings
- Widened delivery detour (step 5) was the highest-leverage gain in this sequence.
- The 3-item BFS lookahead in Medium destabilized item selection and cratered score.
- Rollback of step 6 is complete in `run_medium.py` and compiles (`py_compile` pass).
- A post-rollback verification run was started but user-aborted, so no verified post-rollback score yet.

## Current Code State (Medium)
`run_medium.py` currently includes:
- `random.seed(42)`
- `self._walls` caching
- `ranked[:1]` drop-off queue leader
- late cutoff `round_number > 285`
- widened detour (`direct + 8`, Manhattan `<= 12`)
- no 3-item lookahead helpers (`_sequence_route_cost`, `_distance_*`, `_bfs_distance` removed)

## Recommended Next Task (Highest Priority)
1. Run one fresh Medium game with the rollback build to verify recovery toward the 116 profile.
2. If recovered, test one small change at a time from the step-5 baseline only.
3. If not recovered, revert step 4 (`>285`) first and re-test.

## Exact Artifact References
- Medium bot code:
  - `solutions/grocerybot-trial/run_medium.py`
- Runbook:
  - `solutions/grocerybot-trial/RUNBOOK.md`
- Run history:
  - `solutions/grocerybot-trial/logs/run_history.csv`
- Key medium replays:
  - `solutions/grocerybot-trial/logs/game_20260301_221741.jsonl` (116)
  - `solutions/grocerybot-trial/logs/game_20260301_222205.jsonl` (11)

## Repro Command
From `solutions/grocerybot-trial`:
`& ".venv\Scripts\python.exe" run_medium.py`

## Token Setup
Set `.env` key:
`GROCERY_BOT_TOKEN_MEDIUM=<fresh_token>`

## Handoff Contract
- Current objective:
  - Verify rollback build and stabilize Medium around the 116 trajectory.
- Exact artifact reference:
  - Working file: `solutions/grocerybot-trial/run_medium.py`
  - Best reference replay: `logs/game_20260301_221741.jsonl`
  - Regression replay: `logs/game_20260301_222205.jsonl`
- What is proven:
  - Step 5 worked; step 6 failed; rollback completed in code.
- What is assumed:
  - Post-rollback behavior should return near pre-step-6 levels, but this is not yet re-verified with a completed run.
- Next highest-priority task:
  - Execute one completed Medium run and compare against run `20260301_221741`.
