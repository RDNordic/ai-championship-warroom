# SESSION_HANDOFF.md

## Checkpoint

M3 v2 traffic control is complete (persistent intents, parking, delivery right-of-way). Easy mode optimization was explored but no net changes to memory_solo.py — baseline score is map-dependent (~119-128).

## Latest Work

- Implemented v2 persistent intents in `greedy.py`: pick/deliver/park/idle intents survive across ticks
- Added `BotIntent`, `IntentManager`, `ParkingManager` to `planner.py`
- `TaskAssigner.assign()` now accepts `claimed` parameter; full-inventory bots only get `drop_off` when items match ACTIVE order
- `CollisionResolver.resolve()` accepts `priority_bots` for delivery right-of-way
- Fixed blocker detection: non-delivery bots always vacate the drop-off cell (`dist_to_drop == 0`)
- Added anti-stall nudge: stuck bots step to free neighbor after 3 blocked ticks
- Updated `test_planner.py` with new tests for active-only drop-off and blocker behavior
- Added `scripts/analyze_replay.py` and `scripts/analyze_deep.py` for replay analysis
- Easy mode analysis: memory_solo.py pipeline already works well (88% full-inventory drop-offs, auto-delivery on order transitions). Score variance is map-dependent.
- All 114 tests pass, ruff clean

## Known Issues

- Easy mode score varies by day (map changes at midnight UTC). No code changes improved score on today's map.
- Medium mode not re-benchmarked after v2 changes in this session.

## Next Steps

1. **Easy mode: multi-trip lookahead planning** — Plan 2 trips together for 4-item orders (which require 2 pickup trips). After completing trip 1 and dropping off, recalculate trip 2 using newly available info (completed order may reveal new preview order). Key insight: order completion changes available information, so the second trip should be planned AFTER the first drop-off, not before.

2. **Easy mode: test "always full inventory" policy** — Currently the bot sometimes drops off with <3 items (12% of drop-offs). Test requiring exactly 3 items before drop-off. Tradeoff: extra detour distance for the 3rd item vs saving a future round-trip. On the 12×10 Easy grid, average item distance is ~5-6 steps, so grabbing one extra item costs ~10 steps but saves ~16 steps (a full future trip). Worth testing.

3. **Easy mode: preview item selection quality** — When filling inventory with preview items, choose items that are closest to the drop-off path (minimize detour) rather than cheapest absolute distance. The current `PREVIEW_DETOUR_BUDGET=2` is conservative but safe.

4. **Medium mode: re-benchmark** with v2 traffic control and measure improvement over v1 score of 19.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. Easy mode optimization is next. Start with multi-trip lookahead planning in memory_solo.py: for 4-item orders, plan both pickup trips together to minimize total rounds. Key mechanic: after trip 1 drop-off completes an order, a new preview order appears — so trip 2 should be recalculated post-drop-off. Also test "always fill to 3 items before drop-off" policy. Current Easy baseline is ~119-128 depending on map.
```
