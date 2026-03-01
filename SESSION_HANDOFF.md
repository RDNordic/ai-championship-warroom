# SESSION_HANDOFF.md

## Checkpoint

M3 greedy multi-bot strategy is implemented and fully tested locally, but Medium live run is still stuck at score 2 (300 rounds, 2 items, 0 orders).

## Latest Work

- Implemented `planner.py` with `OrderTracker`, `LocalTripPlanner`, `TaskAssigner`, `CollisionResolver`.
- Added `strategies/greedy.py` and registered strategy in `strategies/__init__.py`.
- Added/updated tests in `tests/test_planner.py` and `tests/test_greedy.py`.
- Fixed collision semantics to match protocol: occupied-cell moves are blocked (drop-off included; spawn exempt).
- Added deadlock-avoidance behavior near drop-off (bots step aside when they are blocking pending deliveries).
- Revalidated quality gates:
  - `python -m pytest` -> 110 passed
  - `python -m ruff check` -> clean
  - `python -m mypy src/grocerybot/planner.py src/grocerybot/strategies/greedy.py` -> clean
- Analyzed replay `game_20260301_113118.jsonl`:
  - score changes only at rounds 17 and 29 (`pasta`, then `milk`)
  - end state still needs `cream, cream`
  - bot 2 ends with `["cream", "cream", "cream"]` but repeatedly receives `wait`

## Known Issues

- Medium throughput regression unresolved: live score remains 2 despite collision fixes.
- Strong theory: `TaskAssigner` is ID-sequential and allows early bots to reserve active needs via planned pickups before later bots with already-carried matching items are considered. This can starve immediate drop-off tasks.
- Secondary theory: blocked-set/claim interaction can over-constrain movement and produce long wait streaks once assignments drift.
- `scripts/replay.py` is still TODO.

## Next Steps

1. Add round-level debug trace for assignment decisions: `remaining_active` before/after each bot, matched inventory, and final task.
2. Confirm from trace that carried active items are being pre-empted by earlier pickup reservations.
3. Refactor assignment to two phases:
   - phase A: reserve carried active items and assign drop-off first (all bots)
   - phase B: assign new pickups only for still-uncovered active needs
4. Re-run Medium (`--strategy greedy`) and compare replay against `game_20260301_113118.jsonl`.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. M3 greedy strategy exists and tests pass, but Medium still scores 2. Start by instrumenting TaskAssigner to log per-bot remaining_active transitions and verify whether early ID bots reserve active needs before later bots carrying those items. Then implement two-phase assignment (carried-item drop-off first, pickups second), rerun medium, and inspect replay deltas.
```
