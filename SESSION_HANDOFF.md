# SESSION_HANDOFF.md

## Checkpoint

M3 two-phase TaskAssigner fix implemented and tested. Medium score improved 2→11 (300 rounds, 6 items, 1 order). Further bottleneck analysis needed.

## Latest Work

- Confirmed Easy theoretical max = 118; memory_solo already optimal (no room to improve via memory).
- Diagnosed M3 TaskAssigner starvation bug: single-pass bot-ID-order assignment let empty bots "reserve" active items via pickup before bots already carrying those items were evaluated.
- Implemented two-phase assignment in `planner.py` `TaskAssigner.assign()`:
  - Phase A: scan ALL bots for carried active items → assign `drop_off` first
  - Phase B: assign pickups for remaining uncovered active needs (bot-ID order)
- Added test `test_carried_active_items_get_dropoff_regardless_of_id` verifying Bot 2 with matching items gets `drop_off` even though Bot 0/1 are processed first.
- Quality gates: 110 tests pass, ruff clean.

## Known Issues

- Medium score = 11 (was 2) — still very low. Latest replay: `game_20260301_115034.jsonl`.
- Preview items not yet assigned in Phase B (only active needs covered).
- Possible remaining bottlenecks: excessive wait assignments, collision-resolver over-constraining movement, inefficient pickup routing.

## Next Steps

1. Analyze replay `game_20260301_115034.jsonl` for remaining bottlenecks:
   - Wait ratio per bot (how many rounds wasted)
   - Whether bots get stuck in long wait streaks
   - Whether collision resolver is downgrading too many moves to waits
   - Whether pickup routing is inefficient (long paths when shorter exist)
2. Add preview pickup assignment in Phase B for bots with no active work.
3. Consider whether `OrderTracker.snapshot()` should account for bot inventories when computing `active_needed` (currently it doesn't — `TaskAssigner` handles it).
4. Re-run Medium and iterate on score.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. M3 greedy strategy scores 11 on Medium after two-phase TaskAssigner fix. Analyze replay game_20260301_115034.jsonl to find remaining bottlenecks (wait ratios, stuck periods, collision downgrades, routing inefficiency). Then implement fixes and re-run.
```
