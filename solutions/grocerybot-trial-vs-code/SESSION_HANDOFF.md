# SESSION_HANDOFF.md

Date: 2026-03-02 (UTC)

## Current Objective
Push Easy above the current best of 119 using one-change incremental experiments.

## Current Best Scores (from `logs/run_history.csv`)
- Easy: 119 (`20260302_125953`)
- Medium: 118 (`20260302_105543`)
- Hard: 99 (`20260301_223438`)
- Expert: 71 (`20260301_224548`)
- Current total best: 407

## What Changed This Session
### Easy (`run_easy.py`)
- Accepted (kept in working tree):
  1. Preserved active-order needed counts separately as `active_needed`.
  2. In solo `useful_inventory` branch, collection logic now uses active-order-only demand (`collect_needed = Counter(active_needed)`) instead of mixed preview demand.
- Tested and rejected (reverted):
  1. Disabling `_pick_if_adjacent(...)` while carrying useful inventory.
  2. Blocking global preview-switch while any active delivery cargo remained.

### Easy Runs in This Window
- `20260302_125953`: 119 (`logs/game_20260302_125953.jsonl`) <- current best
- `20260302_130323`: 93 (`logs/game_20260302_130323.jsonl`) [reverted tweak]
- `20260302_130504`: 95 (`logs/game_20260302_130504.jsonl`) [reverted tweak]

## Proven Findings
- Current Easy best for today/map window is 119 with 14 completed orders.
- The active-order-only collection change in the solo `useful_inventory` branch is compatible with a high run.
- Adjacent-pick suppression and broad preview-switch blocking both caused regressions on this seed.

## Current Code State
### Easy (Active)
`run_easy.py` includes the active-order-only collection patch and excludes the two reverted regressions.

### Medium (Frozen)
`run_medium.py` remains frozen at the 118-capable build (`d704c3d` + `6b24f2c`).

### Hard (Paused)
`run_hard.py` unchanged in this session.

## Recommended Next Task (Highest Priority)
1. Set fresh token: `GROCERY_BOT_TOKEN_EASY`.
2. Apply one new Easy tweak only (single behavior change).
3. Run 2-3 Easy games:
   - `& ".venv\Scripts\python.exe" run_easy.py`
4. Keep/revert based on comparison to baseline 119 and collapse risk.

## Exact Artifact References
- Easy bot code:
  - `solutions/grocerybot-trial-vs-code/run_easy.py`
- Medium frozen bot code:
  - `solutions/grocerybot-trial-vs-code/run_medium.py`
- Runbook:
  - `solutions/grocerybot-trial-vs-code/RUNBOOK.md`
- Session handoff:
  - `solutions/grocerybot-trial-vs-code/SESSION_HANDOFF.md`
- Run history:
  - `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Key Easy replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_125953.jsonl` (119)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_130323.jsonl` (93)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_130504.jsonl` (95)

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:
- Easy validation run:
  - `& ".venv\Scripts\python.exe" run_easy.py`
- Medium frozen reference:
  - `& ".venv\Scripts\python.exe" run_medium.py`

## Token Setup
- Easy: `GROCERY_BOT_TOKEN_EASY=<fresh_token>`
- Medium (only if re-validating): `GROCERY_BOT_TOKEN_MEDIUM=<fresh_token>`

## Handoff Contract
- Current objective:
  - Improve Easy beyond 119 with controlled one-change experiments.
- Exact artifact reference:
  - Working file: `solutions/grocerybot-trial-vs-code/run_easy.py`
  - Frozen reference: `solutions/grocerybot-trial-vs-code/run_medium.py`
- What is proven:
  - Easy has reached 119 in this window and the retained patch is non-regressive at peak.
- What is assumed:
  - Additional targeted routing changes can recover wasted rounds without introducing collapse.
- Next highest-priority task:
  - Implement one new low-risk Easy tweak, then run a short 2-3 run gate against 119.
