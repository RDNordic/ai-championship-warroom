# CLAUDE.md

Purpose: minimal startup context.

## Read Order
1. `SESSION_STATE.json` (single-source current state)
2. `CLAUDE.md` (rules)
3. `SESSION_HANDOFF.md` only if details are needed
4. `RUNBOOK.md` only when running commands

## Core Rules
- One behavior change per trial in one file (`run_hard.py` or `run_expert.py`).
- Hard/Expert gate is a lightweight 3-run batch, not single-run:
  - Run 3 games on the same difficulty.
  - Validate each replay with `validator.py`.
  - Discard runs with `TIMEOUT ROUNDS > 5`.
  - Compare median score of remaining clean runs against the current clean baseline median.
- If clean median improves baseline: keep change and update baseline in state/handoff.
- If clean median does not improve baseline: revert change.
- If fewer than 2 clean runs are available: run one extra; if still inconclusive, revert by default.
- Historical best (`Expert 71`) is a milestone, not the day-to-day trial gate.

## Focus
- Primary: Expert traffic coordination
- Secondary: Hard opening throughput

## Diagnostics
- After each 3-run batch, compute rounds where all 10 bots issued `wait`.
- Use wait-cluster location to choose next trial focus:
  - mostly late rounds -> endgame policy,
  - mid rounds -> congestion/deadlock handling,
  - early rounds -> assignment/opening throughput.

## Guardrails
- Do not touch websocket/token/logging plumbing
- Do not commit `.env` or `__pycache__`
