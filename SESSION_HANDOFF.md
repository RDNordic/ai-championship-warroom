# SESSION_HANDOFF.md

## Checkpoint

Easy mode `memory_solo.py` has 2-trip lookahead, stale-shelf fix, and endgame heuristic. Score: 113 on today's map (baseline was 119 — regression from 2-trip changes). Offline optimizer is planned but not yet implemented.

## Latest Work

- Added 2-trip lookahead (`_choose_best_two_trip_candidate`) for 4-item orders: evaluates trip1_cost + trip2_cost across all splits, picks minimum total. Tie-breaks by cheaper trip-1.
- Fixed stale `_type_to_adjs` bug: now rebuilt from `state.items` each tick so route planner never targets depleted shelves. This was a latent bug exposed by different preview pickup patterns.
- Added endgame heuristic: suppress preview items when ≤25 rounds remain — bot focuses on finishing active order only.
- Stored `self._drop_off` position for trip-2 cost computation.
- All 114 tests pass, ruff clean.

## Known Issues

- Easy mode score is 113 vs baseline 119 (6-point regression). The 2-trip lookahead makes different trip-1 splits that may cascade into worse preview pipeline outcomes. Needs investigation or may be addressed by the offline optimizer approach.
- The 2-trip code only helps when `len(needed_active) > space` (mainly 4-item orders with empty inventory).

## Next Steps

1. **Offline game optimizer** (`scripts/optimize.py`) — TOP PRIORITY. Full plan in `.claude/plans/whimsical-sparking-fountain.md`. Key points:
   - Load daily snapshot (grid, items, orders) from `data/{level}_{date}.json`
   - Simulate optimal bot actions for all known orders: enumerate trip splits for >3 item orders, use exact route planning (A*/BFS from grid.py)
   - Output step-by-step action list + JSON plan file (`data/{level}_{date}_plan.json`)
   - Show rounds saved vs current 300-tick run
   - Purpose: bot replays optimal actions for known orders, then falls back to heuristics for unknown ones. Each run discovers more orders → feed back into optimizer.
   - Items are endless (don't deplete between orders).

2. **Replay strategy**: Build a strategy that reads the plan JSON and replays actions for known rounds, then delegates to `memory_solo` for remaining rounds.

3. **Test "always full inventory" policy** — never drop off with <3 items.

4. **Medium mode re-benchmark** with v2 traffic control.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. Build the offline game optimizer (scripts/optimize.py). Full plan is in .claude/plans/whimsical-sparking-fountain.md. Load daily snapshot, simulate optimal actions for all known orders using exact route planning, output step-by-step action list and JSON plan. Show rounds saved vs current run. Items are endless. Bot spawn is at [10,8] for Easy.
```
