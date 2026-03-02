# RUNBOOK.md

## Quick Resume (Per Difficulty)

Each difficulty has its own fully independent bot file. You can tune one without affecting the others.

## Active Window
- Focus now: `Easy` challenge in a new experiment window.
- Keep `run_medium.py` frozen at the 118-capable build.
- Keep `run_hard.py` unchanged unless explicitly switching focus back to Hard.

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
# Easy (best: 119)
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

# Last 10 easy runs only
Import-Csv .\logs\run_history.csv | Where-Object { $_.difficulty -eq 'easy' } | Select-Object -Last 10

# Best score per difficulty
Import-Csv .\logs\run_history.csv | Group-Object difficulty | ForEach-Object {
  $_.Group | Sort-Object {[int]$_.score} -Descending | Select-Object -First 1
} | Format-Table difficulty,score,run_id,replay_file -AutoSize
```

## Current Easy Notes (Active)
- Best easy replay: `logs/game_20260302_125953.jsonl` (119, 14 orders).
- Recent regressions (reverted experimental tweaks):
  - `logs/game_20260302_130323.jsonl` (93)
  - `logs/game_20260302_130504.jsonl` (95)
- Keep current `run_easy.py` baseline patch:
  - Solo `useful_inventory` branch uses active-order-only demand (`active_needed`) for item collection decisions.
  - This prevents route lookahead from including preview demand while carrying active-order cargo.
- Next step: test one new Easy change at a time and validate quickly against the 119 baseline before keeping.

## Current Medium Notes (Frozen)
- Verified high runs on current medium build:
  - `logs/game_20260302_105543.jsonl` (118)
  - `logs/game_20260302_105659.jsonl` (118)
  - `logs/game_20260302_110631.jsonl` (118)
- Medium commits to keep:
  - `d704c3d` (late-game preview pivot guard + earlier detour cutoff)
  - `6b24f2c` (drop-off ring fallback staging)
- Do not modify `run_medium.py` during Easy tuning unless explicitly switching focus.

## Current Hard Notes (Paused)
- Best hard replay: `logs/game_20260301_223438.jsonl` (99).
- Near-best hard replay: `logs/game_20260301_225157.jsonl` (98).
- Hard tuning is paused while Easy experiments are active.
