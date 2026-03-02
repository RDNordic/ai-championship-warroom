# SESSION_HANDOFF.md

Date: 2026-03-02 (UTC)

## Current Objective
Close Hard+Expert gap against benchmark reference `Hard 243` + `Expert 219` = `462`.

## Current Top Scores
- Easy: 137 (KO log reference, external)
- Medium: 118
- Hard: 99
- Expert: 71
- Total best: 425

## Benchmark Context
- Leaderboard reference (provided): Hard 243, Expert 219, combined 462.
- Current local Hard+Expert: 170.
- Gap to reference on Hard+Expert: 292.

## What Changed This Session
### Hard (`run_hard.py`)
- Implemented Option A: surplus bot preview pipeline.
- Behavior: when active needs are already covered by carried + assigned capacity, surplus bots are assigned preview items with full priority.
- Kept drop-off queue and delivery allocation logic unchanged.
- Validation run result with this code:
  - `logs/game_20260302_142137.jsonl` -> score 99 (matches benchmark).

### Expert (`run_expert.py`) Experiments This Session
Tested one-change experiments and reverted each due to no uplift:
1. Late non-useful cutoff `>285` (reverted).
2. Blocked-move anti-jam streak nudge (reverted).
3. BFS failure random-nudge fallback (reverted).
4. Proximity-aware delivery allocation (reverted).
5. Queue depth scaling to 4 for 7+ bots (reverted after score 54).

### Analysis Findings (Hard + Expert)
1. Hard top runs are execution-clean:
   - blocked moves near 0%
   - pickup failures near 0%
2. Hard main inefficiency: opening spawn-stack waits.
3. Expert main inefficiency: swarm congestion/traffic conflicts at scale (10 bots), plus run-noise risk from timeout-heavy games.
4. Several low Expert runs had high blocked-move rates and validator timeout rounds, so noisy-run filtering is required before keep/revert decisions.

## Current Code State
### Hard (Active)
`run_hard.py` includes Option A surplus preview pipeline (`preview_priority_bots` path).

### Medium (Frozen)
`run_medium.py` unchanged at 118-capable state.

### Expert (Baseline Restored)
`run_expert.py` has been reverted to baseline after all one-change experiments above.

## Hard / Expert Rule: Commit/Revert Gate
For each experiment:
1. Make one focused change only.
2. Run one game on the targeted difficulty with fresh token.
3. Compare to local best for that difficulty (Hard 99, Expert 71).
4. If improved: keep and commit.
5. If not improved: revert and do not commit.
6. If timeout-heavy/noisy run: classify as noisy and rerun before final keep/revert decision.

## Recommended Next Task
1. Prioritize Expert traffic-first single changes (swarm coordination, deconfliction near drop-off/chokepoints).
2. Continue Hard only with opening anti-stack throughput changes.
3. Use strict one-change gate and noisy-run handling.
4. Commit only proven improvements.

## Exact Artifact References
- Hard bot: `solutions/grocerybot-trial-vs-code/run_hard.py`
- Expert bot: `solutions/grocerybot-trial-vs-code/run_expert.py`
- Runbook: `solutions/grocerybot-trial-vs-code/RUNBOOK.md`
- Handoff: `solutions/grocerybot-trial-vs-code/SESSION_HANDOFF.md`
- Resume prompt: `solutions/grocerybot-trial-vs-code/RESUME_PROMPT.txt`
- Run history: `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Hard replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_hard_99_20260301_223438.jsonl` (99)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_142137.jsonl` (99)
- Expert replay reference:
  - `solutions/grocerybot-trial-vs-code/logs/game_expert_71_20260301_224548.jsonl` (71)

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:
- Hard run:
  - `& ".venv\Scripts\python.exe" run_hard.py`
- Expert run:
  - `& ".venv\Scripts\python.exe" run_expert.py`

From repo root:
- Replay validator:
  - `solutions\grocerybot-trial-vs-code\.venv\Scripts\python.exe solutions\grocerybot-simulator\validator.py <replay.jsonl>`

## Handoff Contract
- Current objective:
  - Maximize Hard+Expert points to close gap vs benchmark 462.
- Exact artifact:
  - Working files: `solutions/grocerybot-trial-vs-code/run_hard.py`, `solutions/grocerybot-trial-vs-code/run_expert.py`
- What is proven:
  - Current Hard code can reproduce 99.
  - Hard issues are mainly opening throughput/coordination.
  - Expert failures are mainly swarm traffic/conflict at 10 bots, not pickup legality.
- What is assumed:
  - Traffic-first Expert changes can unlock larger gains than routing-only tweaks.
- Next highest-priority task:
  - Implement one Expert traffic coordination change and run one gated validation with timeout/noise check.
