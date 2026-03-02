# SESSION_HANDOFF.md

Date: 2026-03-02 (UTC)

## Current Objective
Raise Medium score floor (reduce collapse runs) while preserving the stable 116 cluster.

## Current Best Scores (from run_history.csv)
- Easy: 110 (run `20260301_211903`)
- Medium: 116 (latest repeat: `20260301_235029`)
- Hard: 71
- Expert: 60
- Current total best: 357

## What Changed This Session
### Medium (`run_medium.py`)
Applied small, low-risk behavior changes:
1. Anti-stall nudge now triggers earlier (`wait_streak >= 2` instead of `>= 3`).
2. Early low-score recovery nudge: if `round < 80` and `score < 20`, try nudge before wait.
3. Inventory usefulness now also checks `_has_useful_inventory(inventory, needed)` when unmet demand remains.
4. Replaced hard late cutoff with distance-aware late-game staging:
   - In late game, if `dist_to_drop + 2 > rounds_left`, non-useful bots stage near drop-off instead of blind wait.
5. `_select_target_item` now uses a shallow-cycle cost:
   - `cost = (dist_bot * 2) + dist_drop`.
6. `_is_near_delivery_path` detour thresholds are now round-dependent:
   - early: `+8 / <=12`
   - mid: `+6 / <=10`
   - late: `+3 / <=6`

## Proven Findings
- Code compiles after changes (`py_compile` pass).
- Previous rollback baseline remained capable of repeated 116 scores on seed 7002.
- Main remaining risk is variance floor (historical low outliers), not peak score.

## Current Code State (Medium)
`run_medium.py` includes:
- `random.seed(42)`
- `self._walls` caching
- single queue deliverer (`ranked[:1]`)
- round-banded detour gating
- distance-aware late-game staging rule
- early anti-stall nudging and lower wait threshold
- drop-off-aware item scoring in `_select_target_item`

## Recommended Next Task (Highest Priority)
1. Run a controlled Medium batch with fresh tokens (10-15 runs minimum).
2. Compare median and min score to previous baseline.
3. If floor worsens, rollback in this order:
   - target-cost bias
   - late-game distance gate
   - early low-score nudge.

## Exact Artifact References
- Medium bot code:
  - `solutions/grocerybot-trial-vs-code/run_medium.py`
- Runbook:
  - `solutions/grocerybot-trial-vs-code/RUNBOOK.md`
- Run history:
  - `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Key medium replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_20260301_235029.jsonl` (116)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260301_234839.jsonl` (106)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260301_222205.jsonl` (historical low, 11)

## Repro Command
From `solutions/grocerybot-trial-vs-code`:
`& ".venv\Scripts\python.exe" run_medium.py`

## Token Setup
Set `.env` key:
`GROCERY_BOT_TOKEN_MEDIUM=<fresh_token>`

## Handoff Contract
- Current objective:
  - Reduce bad-run frequency while preserving the 116 cluster.
- Exact artifact reference:
  - Working file: `solutions/grocerybot-trial-vs-code/run_medium.py`
  - Baseline high replay: `logs/game_20260301_235029.jsonl`
  - Baseline low replay: `logs/game_20260301_222205.jsonl`
- What is proven:
  - New heuristics are integrated and compile successfully.
- What is assumed:
  - Changes improve score floor; this is not yet validated by a post-change run batch.
- Next highest-priority task:
  - Execute 10-15 Medium runs and compare min/median vs baseline.