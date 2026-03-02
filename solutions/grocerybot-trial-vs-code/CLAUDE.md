# CLAUDE.md

Purpose: Fast session bootstrap with minimal context usage.

## Start Here (Read In This Order)
1. `CLAUDE.md` (this file)
2. `SESSION_HANDOFF.md` (for latest proven state)
3. `RUNBOOK.md` (only when running games / checking process details)

Do not read large logs or replay files until a concrete experiment is chosen.

## Current Mission
- Primary focus: maximize `Hard + Expert` points.
- Benchmark reference: `Hard 243` + `Expert 219` = `462`.
- Current local best: `Hard 99`, `Expert 71` (combined `170`).

## Working Rules
- One behavior change per experiment.
- Change only one target file: `run_hard.py` or `run_expert.py`.
- Run exactly once with fresh token.
- Compare against local best for that difficulty:
  - Hard gate: improve beyond `99`
  - Expert gate: improve beyond `71`
- If not improved: revert immediately.
- If run is timeout-heavy/noisy: classify as noisy and rerun once before keep/revert.

## Strategy Notes
- Hard bottleneck: early opening coordination (spawn-stack / throughput), not basic validity.
- Expert bottleneck: 10-bot traffic coordination and deconfliction, not pickup legality.
- Favor traffic-first Expert changes over generic routing tweaks.

## Operational Guardrails
- Do not modify websocket/token/logging plumbing.
- Do not commit `.env` or `__pycache__`.
- Keep `run_medium.py` frozen (118 baseline) unless explicitly requested.
- Keep Easy unchanged unless explicitly requested.

## Repro Commands
From `solutions/grocerybot-trial-vs-code`:

```powershell
& ".venv\Scripts\python.exe" run_hard.py
& ".venv\Scripts\python.exe" run_expert.py
```

Validator from repo root:

```powershell
solutions\grocerybot-trial-vs-code\.venv\Scripts\python.exe solutions\grocerybot-simulator\validator.py <replay.jsonl>
```

