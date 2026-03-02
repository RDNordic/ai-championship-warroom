# SESSION_HANDOFF.md

Date: 2026-03-02 (UTC)

## Current Objective
Stabilize Hard from the fresh-window baseline and then push Hard beyond the current best of 99.

## Current Best Scores (from `logs/run_history.csv`)
- Easy: 110 (`20260301_211903`)
- Medium: 118 (`20260302_110356`)
- Hard: 99 (`20260301_223438`)
- Expert: 71 (`20260301_224548`)
- Current total best: 398

## What Changed This Session
### Repository
- Removed duplicate workspace `solutions/grocerybot-trial-cursor` and committed cleanup.
  - Commit: `ba525b0`

### Medium (`run_medium.py`)
- Accepted and committed:
  1. Late-game conversion guard for preview pivot + earlier detour cutoff.
     - Commit: `d704c3d`
  2. Drop-off ring fallback staging when adjacency is blocked.
     - Commit: `6b24f2c`
- Rejected and reverted (not committed):
  - lock-first + adjacent-pick variant (regressed to 104/104/12)
  - deadlock reservation-relax variant (regressed to 94/21/3)

## Proven Findings
- Medium currently reaches 118 reliably on this map/seed profile.
- Verified 118 replays include:
  - `logs/game_20260302_105543.jsonl`
  - `logs/game_20260302_105659.jsonl`
  - `logs/game_20260302_110356.jsonl`
  - `logs/game_20260302_110514.jsonl`
  - `logs/game_20260302_110631.jsonl`
- Aggressive path/reservation and pickup-target churn changes can cause severe collapse runs.

## Current Code State
### Medium (Frozen)
`run_medium.py` should remain at `HEAD` with commits `d704c3d` + `6b24f2c` in place.

### Hard (Active)
`run_hard.py` is now the tuning target for the next session window.

## Fresh Hard Baseline (This Window)
- `20260302_112639`: 20 (`logs/game_20260302_112639.jsonl`)
- `20260302_112818`: 91 (`logs/game_20260302_112818.jsonl`)
- `20260302_112945`: 20 (`logs/game_20260302_112945.jsonl`)
- Baseline summary: min=20, median=20, max=91

## Recommended Next Task (Highest Priority)
1. Set fresh token: `GROCERY_BOT_TOKEN_HARD`.
2. Apply one low-risk stability change to `run_hard.py` (single change only).
3. Re-run 3 Hard games:
   - `& ".venv\Scripts\python.exe" run_hard.py`
4. Keep/revert based on min/median improvement vs baseline (20/20/91).

## Exact Artifact References
- Hard bot code:
  - `solutions/grocerybot-trial-vs-code/run_hard.py`
- Medium frozen bot code:
  - `solutions/grocerybot-trial-vs-code/run_medium.py`
- Runbook:
  - `solutions/grocerybot-trial-vs-code/RUNBOOK.md`
- Run history:
  - `solutions/grocerybot-trial-vs-code/logs/run_history.csv`
- Hard key replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_20260301_223438.jsonl` (99)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260301_225157.jsonl` (98)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_112639.jsonl` (20)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_112818.jsonl` (91)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_112945.jsonl` (20)
- Medium key replays:
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_110356.jsonl` (118)
  - `solutions/grocerybot-trial-vs-code/logs/game_20260302_110631.jsonl` (118)

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:
- Hard baseline:
  - `& ".venv\Scripts\python.exe" run_hard.py`
- Medium verification (frozen reference):
  - `& ".venv\Scripts\python.exe" run_medium.py`

## Token Setup
- Hard: `GROCERY_BOT_TOKEN_HARD=<fresh_token>`
- Medium (only if re-validating): `GROCERY_BOT_TOKEN_MEDIUM=<fresh_token>`

## Handoff Contract
- Current objective:
  - Start Hard optimization from a clean baseline window.
- Exact artifact reference:
  - Working file: `solutions/grocerybot-trial-vs-code/run_hard.py`
  - Frozen reference: `solutions/grocerybot-trial-vs-code/run_medium.py`
- What is proven:
  - Current Medium build is 118-capable and already committed.
- What is assumed:
  - Hard can recover floor and exceed 99 with controlled one-change tests and 3-run gating.
- Next highest-priority task:
  - Apply one low-risk Hard stability patch, then run a 3-game gate against baseline 20/20/91.
