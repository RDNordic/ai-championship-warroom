# RUNBOOK.md

## Quick Resume (Per Difficulty)

Each difficulty has its own fully independent bot file. Tune one without affecting others.

## Active Window
- Focus now: `Hard` optimization.
- Current Hard benchmark: `99`.
- Keep `run_medium.py` frozen at the 118 build.
- Do not touch websocket/token/logging plumbing.

## Scoreboard (Current Top)
- Easy: 137 (KO reference run)
- Medium: 118
- Hard: 99
- Expert: 71
- Total best: 425

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
# Easy (best overall: 137 from KO; local best: 119)
& ".venv\Scripts\python.exe" run_easy.py

# Medium (best: 118)
& ".venv\Scripts\python.exe" run_medium.py

# Hard (benchmark: 99)
& ".venv\Scripts\python.exe" run_hard.py

# Expert (best: 71)
& ".venv\Scripts\python.exe" run_expert.py
```

### File Independence
Each `run_*.py` is self-contained bot logic.

## Expected Output
- Progress every 25 rounds
- `Game over: {...}`
- `Run logged: {...}`

## Where Results Go
- Replay: `logs/game_YYYYMMDD_HHMMSS.jsonl`
- Run table: `logs/run_history.csv`
- Memory: `logs/memory.json`
- Notes: `logs/TRIAL_MEMORY.md`

## Rate Limits
- 60s cooldown between runs
- 40 runs/hour
- 300 runs/day

## Hard Commit Gate (Strict)
1. Apply exactly one Hard behavior change.
2. Run Hard with fresh token.
3. Compare score to benchmark `99`.
4. If score is `> 99`: keep and commit.
5. If score is `<= 99`: revert that change (no commit).

## Analysis One-Liners
```powershell
# Last 10 runs
Get-Content .\logs\run_history.csv | Select-Object -Last 10

# Last 10 hard runs
Import-Csv .\logs\run_history.csv | Where-Object { $_.difficulty -eq 'hard' } | Select-Object -Last 10
```

## Current Hard Notes (Active)
- Best hard replay: `logs/game_hard_99_20260301_223438.jsonl` (99).
- Latest validation with current `run_hard.py`: `logs/game_20260302_142137.jsonl` (99).
- Current Hard code includes Option A surplus preview pipeline (`preview_priority_bots`).
- Simulator-backed findings:
  - Top Hard runs already have near-zero blocked moves and failed pickups.
  - Main remaining inefficiency is early spawn-stack waiting in opening rounds.
  - Late cutoff (`round > 285`) is lower impact on Hard than on Expert.
- Next change candidate: startup anti-stack fan-out for empty non-useful bots (single change only).

## Medium Notes (Frozen)
- Keep as-is:
  - `d704c3d`
  - `6b24f2c`

## Easy/Expert Notes
- Easy overall top 137 is from KO logs (external reference).
- Expert best in workspace logs: `game_expert_71_20260301_224548.jsonl`.
