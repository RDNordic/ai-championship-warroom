# SESSION_HANDOFF.md

Date: 2026-03-03 (UTC)

## Current Objective
Maximize Hard+Expert points with stable, incremental experiments.

## Top Scores (Historical)
- Easy: 137 (KO reference, external)
- Medium: 118
- Hard: 99
- Expert: 71
- Total best: 425

## Benchmark Context
- Leaderboard reference (provided): Hard 243, Expert 219, combined 462.
- Historical local Hard+Expert: 170.
- Historical gap to reference on Hard+Expert: 292.

## Critical Process Update (Adopted)
- Old gate (single-run vs `Expert 71`) is suspended for day-to-day trialing.
- New default gate is lightweight `3-run clean-median`:
  - 3 runs per trial,
  - discard noisy runs where `TIMEOUT ROUNDS > 5`,
  - compare median of clean runs vs current clean baseline median.

## Current Clean Baseline (Expert)
- Difficulty: Expert
- Map seed: `7004`
- Baseline run_ids: `20260303_232503`, `20260303_232642`, `20260303_232807`
- Baseline clean scores: `3, 3, 12`
- Baseline clean median: `3`
- Observed wait cluster: all 10 bots waiting in rounds `271-299` (29 rounds).

## What Changed This Session
### Process / Evaluation
- Added timeout-aware validation as required gate.
- Added all-bot-wait clustering diagnostic.
- Documented that historical best is milestone, not per-trial gate.

### Expert (`run_expert.py`) Trials
Re-tested and/or attempted several one-change ideas:
1. BFS assignment distance (reverted; no uplift).
2. Scarcity weighting (reverted; no uplift).
3. Zone partition bias (reverted; no uplift).
4. Queue depth `2 -> 3` (reverted; no uplift on clean run).
5. Option A surplus preview pipeline (clean single run `60`, below historical 71; reverted under old gate).
6. Prompt 5 pick-fail cooldown port from Hard: now patched and partially evaluated.

## Prompt 5 Trial Status (In Progress)
- File: `solutions/grocerybot-trial-vs-code/run_expert.py`
- Change: pick-fail cooldown port from Hard (`_update_pick_retry_state`, `_item_pick_blocked`, assignment filter, pick tracking).
- Completed runs in this batch:
  - `20260303_233101` -> score 30, timeouts 1 (clean)
  - `20260303_233230` -> score 12, timeouts 0 (clean)
- Third run missing due token expiry.
- Interim clean median (2 runs): 30.

## Current Code State
- Hard (`run_hard.py`): includes Option A surplus preview pipeline.
- Medium (`run_medium.py`): frozen at 118-capable logic.
- Expert (`run_expert.py`): includes Prompt 5 patch; decision pending final third run.

## Keep/Revert Decision Rule (Now)
For each Hard/Expert trial:
1. One behavior change in one file.
2. Run 3 games on target difficulty.
3. Validate each replay.
4. Exclude runs with `TIMEOUT ROUNDS > 5`.
5. If clean run count <2 after one extra attempt, revert as inconclusive.
6. Compare clean median to current clean baseline median.
7. Keep if improved; otherwise revert.

## Exact Artifact References
- Hard bot: `solutions/grocerybot-trial-vs-code/run_hard.py`
- Expert bot: `solutions/grocerybot-trial-vs-code/run_expert.py`
- Runbook: `solutions/grocerybot-trial-vs-code/RUNBOOK.md`
- Handoff: `solutions/grocerybot-trial-vs-code/SESSION_HANDOFF.md`
- State: `solutions/grocerybot-trial-vs-code/SESSION_STATE.json`
- Resume prompt: `solutions/grocerybot-trial-vs-code/RESUME_PROMPT.txt`
- Run history: `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Latest baseline replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_20260303_232503.jsonl`
  - `solutions/grocerybot-trial-vs-code/logs/game_20260303_232642.jsonl`
  - `solutions/grocerybot-trial-vs-code/logs/game_20260303_232807.jsonl`

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:
- Expert run:
  - `& ".venv\Scripts\python.exe" run_expert.py`

From repo root:
- Replay validator:
  - `solutions\grocerybot-trial-vs-code\.venv\Scripts\python.exe solutions\grocerybot-simulator\validator.py <replay.jsonl>`

## Handoff Contract
- Current objective:
  - improve Expert via clean-median iteration without noisy-run drift.
- Exact artifact:
  - active trial file: `solutions/grocerybot-trial-vs-code/run_expert.py`
- What is proven:
  - noise-aware median gate is now necessary and operational.
  - current clean expert baseline median is 3 on seed 7004.
  - endgame wait clustering exists in rounds 271-299.
- What is assumed:
  - pick-fail cooldown can improve median once full 3-run batch is completed.
- Next highest-priority task:
  - refresh Expert token and complete the third Prompt 5 run, then decide keep/revert by clean median.
