# SESSION_HANDOFF.md

Date: 2026-03-02 (UTC)

## Current Objective
Increase Hard above benchmark 99 with one-change experiments and strict keep/revert gate.

## Current Top Scores
- Easy: 137 (KO log reference, external)
- Medium: 118
- Hard: 99
- Expert: 71
- Total best: 425

## What Changed This Session
### Hard (`run_hard.py`)
- Implemented Option A: surplus bot preview pipeline.
- Behavior: when active needs are already covered by carried + assigned capacity, surplus bots are assigned preview items with full priority.
- Kept drop-off queue and delivery allocation logic unchanged.
- Validation run result with this code:
  - `logs/game_20260302_142137.jsonl` -> score 99 (matches benchmark).

### Simulator Analysis (Hard + Expert)
Analyzed replays with `solutions/grocerybot-simulator` tooling and custom metrics.

Key findings:
1. Hard best runs are clean on low-level execution:
   - blocked moves near 0%
   - failed pickups near 0%
2. Hard bottleneck is mainly coordination/throughput in opening phase:
   - repeated early waits from stacked spawn positions while active work is still feasible.
3. Hard late cutoff (`round > 285`) has limited upside in best runs.
4. Expert has larger late-cutoff penalty and larger early stack-wait issue.

## Current Code State
### Hard (Active)
`run_hard.py` includes Option A surplus preview pipeline (`preview_priority_bots` path).

### Medium (Frozen)
`run_medium.py` unchanged at 118-capable state.

### Easy / Expert
No new code changes in this handoff step.

## Hard Rule: Commit/Revert Gate
For each Hard experiment:
1. Make one focused change only.
2. Run one Hard game with fresh token.
3. Compare to benchmark 99.
4. If score `> 99`: keep and commit.
5. If score `<= 99`: revert the change; do not commit.

## Recommended Next Task
1. Apply one low-risk Hard startup anti-stack fan-out change.
2. Run Hard once.
3. Use strict gate above.
4. If kept, run 2 additional confirmations.

## Exact Artifact References
- Hard bot: `solutions/grocerybot-trial-vs-code/run_hard.py`
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

From repo root:
- Replay validator:
  - `solutions\grocerybot-trial-vs-code\.venv\Scripts\python.exe solutions\grocerybot-simulator\validator.py <replay.jsonl>`

## Handoff Contract
- Current objective:
  - Push Hard above 99 using strict one-change gating.
- Exact artifact:
  - Working file: `solutions/grocerybot-trial-vs-code/run_hard.py`
- What is proven:
  - Current Hard code can reproduce 99.
  - Simulator confirms main issue is throughput/coordination, not basic action validity.
- What is assumed:
  - Startup anti-stack behavior can recover early wasted rounds and lift score above 99.
- Next highest-priority task:
  - Implement startup anti-stack fan-out and run one gated Hard validation.
