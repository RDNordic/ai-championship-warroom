# SESSION_HANDOFF.md

Date: 2026-03-01 (UTC)

## Current Objective
Run Expert (10 bots, 28x18) for first score — the only remaining map.

## Current Best Scores
- Easy: **128**
- Medium: **99** (stable, deterministic)
- Hard: **71** (stable, deterministic — runs 9 & 10 identical)
- Expert: not yet attempted (10 bots, 28x18)
- **Current leaderboard total: 298** (rank 40, Easy + Medium + Hard)

## Exact Artifact References
- Code: `C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\run_bot.py`
- Run history: `C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\logs\run_history.csv`
- Memory state: `C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\logs\memory.json`
- Human run notes: `C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\logs\TRIAL_MEMORY.md`
- Game API docs: `C:\Users\John Brown\ai-championship-warroom\past-championships-data\Grocery-bot-Game-AI-documentation-2026.txt`

## Difficulty Specs
| Level  | Grid  | Bots | Aisles | Item Types | Order Size |
|--------|-------|------|--------|------------|------------|
| Easy   | 12x10 | 1   | 2      | 4          | 3-4        |
| Medium | 16x12 | 3   | 3      | 8          | 3-5        |
| Hard   | 22x14 | 5   | 4      | 12         | 3-5        |
| Expert | 28x18 | 10  | 5      | 16         | 4-6        |

## What Is Proven
- Bot scales from 1 to 5 bots without code changes (Medium 3 bots, Hard 5 bots).
- Expert (10 bots) is untested — potential issues: drop-off congestion, BFS timing, coordination overhead.
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

## Expert-Specific Concerns
1. **Drop-off bottleneck**: 10 bots, 1 drop-off cell. Current 2-bot queue may not scale.
2. **BFS performance**: 28x18 grid with 10 bots — should stay well under 1.8s but watch timing.
3. **Coordination overhead**: `preview_duty_cap = min(bots-1, 3)` = 3 preview bots. Remaining 7 do active order work.
4. **Order size 4-6**: larger orders may need more delivery throughput.

## Hard Run History (for reference)
- Run 7: score 64, delivered 29, pickups 53, waits 39 (original baseline).
- Run 8: score 18, delivered 8, pickups 47, waits 201 (round 250 cutoff — reverted).
- Run 9: score 71, delivered 31, pickups 32, waits 146 (cutoff reverted, new best).
- Run 10: score 71, delivered 31, pickups 32, waits 146 (identical, deterministic confirmation).

## Next Steps
1. **Run Expert** — get first score, observe action counts and bottlenecks.
2. Analyze Expert replay if score is low — likely drop-off congestion with 10 bots.
3. If Expert bottlenecked: consider increasing queue size from 2 to 3, or reducing staging congestion.
4. Optimize across all maps once Expert baseline is established.

## Repro Command
`& "C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\.venv\Scripts\python.exe" "C:\Users\John Brown\ai-championship-warroom\solutions\grocerybot-trial\run_bot.py"`

## Token Setup
1. Go to app.ainm.no/challenge, select **Expert** map, click **Play**.
2. Save token to `.env`: `GROCERY_BOT_TOKEN=<token>`
3. Run the repro command above.
