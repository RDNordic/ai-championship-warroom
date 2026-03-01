# RUNBOOK.md

## Quick Resume (Per Difficulty)

### 1. Get a fresh token
Go to `app.ainm.no/challenge` → select difficulty → click **Play**.

### 2. Save token to `.env`
```
GROCERY_BOT_TOKEN_EASY=<token>
GROCERY_BOT_TOKEN_MEDIUM=<token>
GROCERY_BOT_TOKEN_HARD=<token>
GROCERY_BOT_TOKEN_EXPERT=<token>
```

### 3. Run the matching script
```powershell
# Easy (target: beat 137 for 1st place)
& ".venv\Scripts\python.exe" run_easy.py

# Medium (current best: 99)
& ".venv\Scripts\python.exe" run_medium.py

# Hard (current best: 71)
& ".venv\Scripts\python.exe" run_hard.py

# Expert (current best: 60)
& ".venv\Scripts\python.exe" run_expert.py

# Generic fallback (uses GROCERY_BOT_TOKEN directly)
& ".venv\Scripts\python.exe" run_bot.py
```

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
4. Planner timeout fallback (`>1.8s`) → all-wait.
5. Planner exception fallback → all-wait.
6. Token expiry checked before connect.

## Analysis One-Liner
```powershell
Get-Content .\logs\run_history.csv | Select-Object -Last 5
```
