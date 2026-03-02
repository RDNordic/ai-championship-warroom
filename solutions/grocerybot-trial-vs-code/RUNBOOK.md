# RUNBOOK.md

## Quick Resume (Per Difficulty)

Each difficulty has its own fully independent bot file. You can tune one without affecting the others.

## Active Window
- Focus now: `Hard` challenge in a fresh tuning window.
- Keep `run_medium.py` frozen at the current 118-capable build while tuning Hard.

### 1. Get a fresh token
Go to `app.ainm.no/challenge` -> select difficulty -> click **Play**.

### 2. Save token to `.env`
```dotenv
GROCERY_BOT_TOKEN_EASY=<token>
GROCERY_BOT_TOKEN_MEDIUM=<token>
GROCERY_BOT_TOKEN_HARD=<token>
GROCERY_BOT_TOKEN_EXPERT=<token>
```

### 3. Run the matching script
```powershell
# Easy (best: 110)
& ".venv\Scripts\python.exe" run_easy.py

# Medium (best: 118)
& ".venv\Scripts\python.exe" run_medium.py

# Hard (best: 99)
& ".venv\Scripts\python.exe" run_hard.py

# Expert (best: 71)
& ".venv\Scripts\python.exe" run_expert.py

# Generic fallback (uses GROCERY_BOT_TOKEN directly)
& ".venv\Scripts\python.exe" run_bot.py
```

### File Independence
Each `run_*.py` is a complete self-contained copy of bot logic.

## Expected Output
- Progress lines every 25 rounds.
- `Game over: {...}`
- `Run logged: {...}`

## Where Results Go
- Replay: `logs/game_YYYYMMDD_HHMMSS.jsonl`
- History table: `logs/run_history.csv`
- Rolling memory: `logs/memory.json`
- Human-readable log: `logs/TRIAL_MEMORY.md`

## Rate Limits (manual tracking)
- 60s cooldown between runs
- 40 runs/hour
- 300 runs/day

## Compliance Checklist
1. Uses `wss://game.ainm.no/ws?token=...`
2. Sends one action per bot per round.
3. Action names constrained to allowed protocol actions.
4. Planner timeout fallback (`>1.8s`) -> all-wait.
5. Planner exception fallback -> all-wait.
6. Token expiry checked before connect.

## Analysis One-Liners
```powershell
# Last 10 runs across all difficulties
Get-Content .\logs\run_history.csv | Select-Object -Last 10

# Last 10 hard runs only
Import-Csv .\logs\run_history.csv | Where-Object { $_.difficulty -eq 'hard' } | Select-Object -Last 10
```

## Current Medium Notes (Frozen)
- Verified high runs on current medium build:
  - `logs/game_20260302_105543.jsonl` (118)
  - `logs/game_20260302_105659.jsonl` (118)
  - `logs/game_20260302_110631.jsonl` (118)
- Medium commits to keep:
  - `d704c3d` (late-game preview pivot guard + earlier detour cutoff)
  - `6b24f2c` (drop-off ring fallback staging)
- Do not modify `run_medium.py` during Hard tuning unless explicitly switching focus.

## Current Hard Notes (Active)
- Best hard replay: `logs/game_20260301_223438.jsonl` (99).
- Near-best hard replay: `logs/game_20260301_225157.jsonl` (98).
- Fresh-window baseline (2026-03-02):
  - `logs/game_20260302_112639.jsonl` (20)
  - `logs/game_20260302_112818.jsonl` (91)
  - `logs/game_20260302_112945.jsonl` (20)
  - Baseline summary: min=20, median=20, max=91
- Hard has high variance and collapse risk, so test in 3-run batches and keep one-change increments.
- Immediate next step: apply one low-risk stability change to `run_hard.py` and re-test in 3 runs.
