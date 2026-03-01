# RUNBOOK.md

## Quick Resume
1. Open Medium map and click `Play` to get a fresh token.
2. Save token to `C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\.env`:
`GROCERY_BOT_TOKEN=<raw_jwt_or_full_ws_url>`
3. Run:
`& "C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\.venv\Scripts\python.exe" "C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\run_bot.py"`

## Expected Output
- Progress lines every 25 rounds.
- `Game over: {...}`
- `Run logged: {...}`

## Where Results Go
- Replay: `logs\game_YYYYMMDD_HHMMSS.jsonl`
- History table: `logs\run_history.csv`
- Rolling memory: `logs\memory.json`
- Human-readable log: `logs\TRIAL_MEMORY.md`

## Compliance Checklist
1. Uses `wss://game.ainm.no/ws?token=...`
2. Sends one action per bot per round.
3. Action names constrained to allowed protocol actions.
4. Planner timeout fallback (`>1.8s`) -> all-wait.
5. Planner exception fallback -> all-wait.
6. Token expiry checked before connect.
7. Team-level cooldown/rate limits are still manual:
`60s cooldown`, `40/hour`, `300/day`.

## Analysis One-Liner
- Best score so far in this folder:
`Get-Content .\logs\run_history.csv | Select-Object -Last 5`

