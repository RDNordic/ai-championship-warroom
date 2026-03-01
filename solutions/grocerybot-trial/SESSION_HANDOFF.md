# SESSION_HANDOFF.md

Date: 2026-03-01 (UTC)

## Current Objective
Push Easy score from 128 → 137+ to take first place. Then re-run Medium, Hard, Expert.

## Leaderboard
- **1st place: 137 points**
- **Our total: 128** (currently 2nd or lower)
- Gap to close: **9 points on Easy alone could win it**

## Current Best Scores
- Easy: **128** — primary optimization target
- Medium: **99** (stable, deterministic)
- Hard: **71** (stable, deterministic)
- Expert: **60** (first run, likely improvable)
- **Current leaderboard total: ~358** (Easy + Medium + Hard + Expert)

## Exact Artifact References
- Core logic: `run_bot.py` (~1244 lines)
- **Per-difficulty runners** (new):
  - `run_easy.py` → reads `GROCERY_BOT_TOKEN_EASY` from `.env`
  - `run_medium.py` → reads `GROCERY_BOT_TOKEN_MEDIUM` from `.env`
  - `run_hard.py` → reads `GROCERY_BOT_TOKEN_HARD` from `.env`
  - `run_expert.py` → reads `GROCERY_BOT_TOKEN_EXPERT` from `.env`
- Run history: `logs/run_history.csv`
- Memory state: `logs/memory.json`
- Human run notes: `logs/TRIAL_MEMORY.md`
- Game API docs: `past-championships-data/Grocery-bot-Game-AI-documentation-2026.txt`

## Difficulty Specs
| Level  | Grid  | Bots | Aisles | Item Types | Order Size |
|--------|-------|------|--------|------------|------------|
| Easy   | 12x10 | 1   | 2      | 4          | 3-4        |
| Medium | 16x12 | 3   | 3      | 8          | 3-5        |
| Hard   | 22x14 | 5   | 4      | 12         | 3-5        |
| Expert | 28x18 | 10  | 5      | 16         | 4-6        |

## What Is Proven
- Bot scales from 1 to 10 bots without code changes.
- Expert (10 bots) scored 60 on first run — drop-off congestion and 851 waits suggest room to improve.
- Safety guards active: token expiry, planner exception fallback, 1.8s timeout fallback, action sanitization.
- Deterministic runs: same seed + same code = same score (confirmed on Hard).
- Logging: replay jsonl + CSV + memory json + markdown log.

## Key Architecture (run_bot.py, ~1244 lines)
- Single-file, class `TrialBot`, entry point `decide(state)`.
- `_allocate_delivery_slots`: prevents duplicate delivery chasing (bot ID order).
- `_build_greedy_assignments`: global item-to-bot matching by distance.
- `_decide_one`: per-bot priority chain: drop_off → clearance → preview → adjacent pickup → delivery detour → drop_off queuing → item targeting → staging → wait/nudge.
- 2-bot drop-off queue pipeline (leader delivers, runner-up stages adjacent).
- Preview duty system: up to `min(bots-1, 3)` bots pre-pick next order items.
- Light late-game: detour pickups stop after round 250; idle bots stop after round 270.
- Anti-deadlock: random nudge after 3 consecutive waits at same position.

## Easy-Mode Optimization Ideas (128 → 137+)
Easy = 1 bot, 12x10 grid, 2 aisles, 4 item types, orders of 3-4 items.
With only 1 bot, multi-bot features (delivery slots, preview duty, queue pipeline) are effectively disabled. Optimization should focus on:
1. **Pathing efficiency** — minimize BFS steps per item; consider if greedy nearest-item is leaving points on the table.
2. **Order completion speed** — faster drop-offs = more orders = more score.
3. **Late-game cutoffs** — round 250/270 cutoffs may be too conservative for 1-bot easy mode.
4. **Item pickup order** — optimal TSP-like ordering for 3-4 items per order on a small grid.
5. **Drop-off timing** — with 1 bot there's no queue contention, so drop-off should be immediate.

## Run Commands (per difficulty)
```bash
# Easy
& ".venv\Scripts\python.exe" run_easy.py

# Medium
& ".venv\Scripts\python.exe" run_medium.py

# Hard
& ".venv\Scripts\python.exe" run_hard.py

# Expert
& ".venv\Scripts\python.exe" run_expert.py

# Generic (uses GROCERY_BOT_TOKEN directly)
& ".venv\Scripts\python.exe" run_bot.py
```

## Token Setup (per difficulty)
1. Go to app.ainm.no/challenge, select the difficulty, click **Play**.
2. Save token to `.env` under the matching variable:
   - `GROCERY_BOT_TOKEN_EASY=<token>`
   - `GROCERY_BOT_TOKEN_MEDIUM=<token>`
   - `GROCERY_BOT_TOKEN_HARD=<token>`
   - `GROCERY_BOT_TOKEN_EXPERT=<token>`
3. Run the corresponding `run_<difficulty>.py` script.

## Run History Summary
| Run | Difficulty | Score | Items | Orders | Key observation |
|-----|-----------|-------|-------|--------|-----------------|
| 1-5 | Medium | 2→19 | 2→9 | 0→2 | Early iterations |
| 6   | Medium | **99** | 44 | 11 | Current best, 9 waits only |
| 7   | Hard   | 64  | 29 | 7  | Baseline |
| 8   | Hard   | 18  | 8  | 2  | Round 250 cutoff regression |
| 9-10| Hard   | **71** | 31 | 8  | Current best, deterministic |
| 11  | Expert | **60** | 30 | 6  | First run, 851 waits |

## Next Steps
1. **Get fresh Easy token** → paste into `GROCERY_BOT_TOKEN_EASY` in `.env`.
2. **Run `run_easy.py`** → establish baseline with current code.
3. **Analyze Easy replay** → identify where the 1 bot is wasting moves.
4. **Optimize for Easy** → target 137+ points.
5. Re-run Medium, Hard, Expert with any improvements.
