# SESSION_HANDOFF.md

Date: 2026-03-01 (UTC)

## Current Objective
Recover Easy performance to >= 110 while preserving the new anti-oscillation fixes, then push toward 137+.

## Current Best Scores (from run_history.csv)
- Easy: 110 (run `20260301_211903`)
- Medium: 99
- Hard: 71
- Expert: 60
- Current total best: 340

## What Changed This Session
`run_easy.py` now includes:
- lock-first target policy in `_locked_or_best_item`
- oscillation detection with temporary target commit
- smart early delivery (2-item early drop rule)
- BFS fallback targeting in `_select_target_item`
- mixed active+preview opportunistic pickup branch
- failed-pick item blocking and shelf-diversity penalties (experimental)

## Latest Easy Run Outcomes
- `20260301_211903`: score 110, items 45, orders 13 (best)
- `20260301_212753`: score 26, items 11, orders 3 (regression)
- `20260301_213409`: score 84, items 34, orders 10
- `20260301_213638`: score 84, items 34, orders 10 (deterministic with current logic)

## Proven Findings
- Oscillation bug at score 8 is fixed.
- New heuristics introduced a late-game regression: repeated failed `pick_up` attempts after round ~240 cause plateau at score 84.
- Replay evidence:
  - `logs/game_20260301_212753.jsonl`
  - `logs/game_20260301_213409.jsonl`
  - `logs/game_20260301_213638.jsonl`

## Recommended Next Task (Highest Priority)
Stabilize Easy by tightening or rolling back the new experimental heuristics while keeping lock-first + oscillation logic:
1. Keep lock-first + oscillation code intact.
2. Reduce/remove mixed preview opportunism when active-order progress stalls.
3. Revisit failed-pick handling to avoid over-constraining target pool.
4. Re-run Easy and target >= 110 before further optimization.

## Exact Artifact References
- Easy bot code:
  - `solutions/grocerybot-trial/run_easy.py`
- Runbook:
  - `solutions/grocerybot-trial/RUNBOOK.md`
- Run history:
  - `solutions/grocerybot-trial/logs/run_history.csv`
- Latest replays:
  - `solutions/grocerybot-trial/logs/game_20260301_211903.jsonl`
  - `solutions/grocerybot-trial/logs/game_20260301_212753.jsonl`
  - `solutions/grocerybot-trial/logs/game_20260301_213409.jsonl`
  - `solutions/grocerybot-trial/logs/game_20260301_213638.jsonl`

## Repro Command
From `solutions/grocerybot-trial`:
`& ".venv\Scripts\python.exe" run_easy.py`

## Token Setup
Set `.env` key:
`GROCERY_BOT_TOKEN_EASY=<fresh_token>`

