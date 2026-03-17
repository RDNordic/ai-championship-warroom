# SESSION_HANDOFF.md

Date: 2026-03-09 (UTC)

## Current Objective
Maintain the kept Expert improvement while continuing Nightmare point collection.

## Top Scores (Historical)
- Easy: 137 (KO reference, external)
- Medium: 118
- Hard: 99
- Expert: 93
- Nightmare: **193**
- Total best: 647

## Benchmark Context
- Leaderboard reference (provided): Hard 243, Expert 219, combined 462.
- Nightmare: no external benchmark known. Our best is 193.

## Expert Status (Updated 2026-03-09 UTC)
- Clean baseline to beat for current kept Expert logic: `70` clean median on seed `7004`.
- Best recorded workspace score: `93`.
- Active baseline snapshot: `run_expert_baseline_93_20260309.py`.
- Active live file: `run_expert.py`.
- Current kept change: tighter preview activation for bots carrying non-useful inventory.

### Kept Expert Trial
- Trial: tighten preview activation so bots with non-useful inventory only keep building preview when active need is already fully in flight.
- run_ids: `20260309_205554`, `20260309_205750`, `20260309_205937`
- clean/noisy counts: `3 clean`, `0 noisy`
- clean scores: `82, 70, 3`
- clean median: `70`
- decision: `keep`

### Reverted Expert Trials (2026-03-09)
- remove random nudge fallback
- force non-useful bots near drop-off to yield earlier when delivery queue exists
- allow preview buildup when active remaining need is `<= 1`
- remove delivery detours for useful carriers
- early-stall perimeter clear for non-useful carriers

### Latest Reverted Expert Trial: Early-Stall Perimeter Clear
- Goal: when active-order progress stalls during rounds `35-140`, route bots carrying only non-useful inventory toward the perimeter instead of continuing preview-related staging near the work area.
- Result: reverted after live 3-run gate.
- run_ids tested: `20260309_213144`, `20260309_213601`, `20260309_213803`
- clean/noisy counts: `2 clean`, `1 noisy`
- clean scores: `60, 4`
- clean median: `32`
- noisy run: `20260309_213144` score `22`, `TIMEOUT ROUNDS = 7`
- keep/revert decision: `revert`

### Replay-Derived Expert Thresholds
- Healthy by round `100`: at least `2` orders and roughly `score >= 20`.
- Strong by round `100`: `3` orders and `score >= 28`.
- Danger signal: no new active-order progress for `>= 90` rounds after the first stall.
- Collapse signal: `0` orders by round `100` or longest active-order starvation `>= 200`.
- Earliest divergence window: roughly rounds `35-60`.

### Most Useful Fresh Replay Contrast
- Clean stronger run: `20260309_213601`
  - final `60`, orders `6`, round `100` score `20`, orders `2`, longest starvation `92`
- Clean collapse run: `20260309_213803`
  - final `4`, orders `0`, round `100` score `3`, orders `0`, longest starvation `176`
- Read: the new perimeter-clear behavior sometimes helps bots recover after the opening, but it is too unstable to keep.

## Hard Status
- Historical best: 99.
- Current file: `run_hard.py`.
- Includes Option A surplus preview pipeline.
- Known anti-pattern: do not re-sort worker processing order when using `reserved_next`.

## Nightmare Status
- Current file: `run_nightmare.py`.
- Baseline snapshot: `run_nightmare_baseline_193.py`.
- Proven: 7 active workers is the right operating point for the current 20-bot grid.

## Current Code State
- **Nightmare** (`run_nightmare.py`): 7-worker config with stale_pivot.
- **Hard** (`run_hard.py`): includes Option A surplus preview pipeline.
- **Medium** (`run_medium.py`): frozen at 118-capable logic.
- **Expert** (`run_expert.py`): reverted to the kept preview-tightening state after the failed early-stall perimeter-clear trial.

## Exact Artifact References
- Expert bot: `solutions/grocerybot-trial-vs-code/run_expert.py`
- Expert baseline snapshot: `solutions/grocerybot-trial-vs-code/run_expert_baseline_93_20260309.py`
- Replay analyzer: `solutions/grocerybot-trial-vs-code/analyze_expert_replay.py`
- Run history: `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Handoff: `solutions/grocerybot-trial-vs-code/SESSION_HANDOFF.md`
- Next steps: `next-steps.md`

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:
```powershell
# Expert live run
& ".venv\Scripts\python.exe" run_expert.py

# Validate replay
& ".venv\Scripts\python.exe" "..\grocerybot-simulator\validator.py" "logs\game_YYYYMMDD_HHMMSS.jsonl"

# Analyze replay tempo
& ".venv\Scripts\python.exe" analyze_expert_replay.py "logs\game_YYYYMMDD_HHMMSS.jsonl"
```

## Token Setup
1. Go to `app.ainm.no/challenge`.
2. Select difficulty, click **Play**.
3. Update `.env` with one fresh token per live run.

## Handoff Contract
- **Current objective:** Preserve the kept Expert logic and use replay evidence to find a safer post-round-35 collapse intervention.
- **Exact artifact reference:** `solutions/grocerybot-trial-vs-code/run_expert.py`
- **What is proven:**
  - The current kept Expert logic can still produce clean `60-82` class runs on seed `7004`.
  - The early-stall perimeter-clear trial is too unstable to keep; it produced both a clean `60` and a clean `4`.
  - Expert play tokens currently behave as single-use tokens in practice.
- **What is assumed:**
  - The next useful change should be narrower than global perimeter clearing.
  - The first actionable collapse point is still around rounds `35-60`, after the opening burst but before full deadlock.
- **Next highest-priority task:**
  1. Compare clean `60` replay `20260309_213601` against clean `4` replay `20260309_213803` at rounds `35-60` and target one local decision rule.
  2. Keep drop-off queueing and useful-delivery priority intact.
  3. Test temporary bottleneck roles or safe-basin staging only for bots carrying non-useful inventory with `len(inventory) >= 3`, rather than rerouting all non-useful carriers.
  4. Continue one-token-per-run Expert testing and always record run_ids, clean/noisy counts, clean scores, clean median, and keep/revert.
