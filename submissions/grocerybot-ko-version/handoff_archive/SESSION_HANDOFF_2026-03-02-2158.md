# SESSION_HANDOFF.md

## Checkpoint

Medium strategy work is active: `medium_v2` and `medium_v3` exist, diagnostics are integrated, and `medium_v3` has hotfixes for drop-off deadlocks but performance is still variable.

## Latest Work

- Added replay filename level tagging (`game_<level>_yyyymmdd_hhmmss.jsonl`) via:
  - `src/grocerybot/util/logger.py`
  - `src/grocerybot/client.py`
  - `scripts/run.py`
- Added `medium_v2` strategy:
  - `src/grocerybot/strategies/medium_v2.py`
  - min-cost-ish greedy assignment + candidate-based traffic resolution
- Added strategy diagnostics pipeline:
  - strategy hook in `src/grocerybot/strategies/base.py`
  - replay write in `src/grocerybot/client.py`
  - analyzer support in `scripts/analyze_replay.py` and `scripts/analyze_deep.py`
- Added `medium_v3` strategy:
  - `src/grocerybot/strategies/medium_v3.py`
  - greedy active allocation, reservation traffic, delivery leader, stricter preview gate
- `medium_v3` was patched twice:
  1. Decongestion/anti-oscillation patch improved one run to score 36
  2. Over-constrained patch caused hard deadlock (score 18) and was hotfixed
- Added/updated tests:
  - `tests/test_medium_v2.py`
  - `tests/test_medium_v3.py`
  - includes drop-off clearance and diagnostics checks
- Strategy registry updated:
  - `src/grocerybot/strategies/__init__.py` now includes `medium_v2`, `medium_v3`

## Known Issues

- `medium_v3` remains unstable across runs (observed scores 36 and 18).
- Deadlock risk near drop-off corridor is reduced but not eliminated.
- Throughput still far below benchmark friend run (`104`) especially in order-cycle time.
- Existing analyzers parse native replay schema directly; friend log schema required ad-hoc adapter in session.

## Next Steps

1. Run 5 consecutive medium games with `medium_v3` and collect replay names.
2. For each replay, record:
   - score, items, orders
   - rounds with `traffic_blocks`
   - max stuck streak per bot
3. Identify dominant failure pattern across the 5 runs (not a single replay).
4. Patch `medium_v3` only on that dominant failure path:
   - prefer relaxed drop-off lane rules for pickers
   - allow controlled delivery sidestep with bounded retries
5. Re-run the same 5-game batch and compare mean/median score.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. Continue Medium optimization on `medium_v3` using a 5-replay batch evaluation. Run five medium games, analyze each replay (score, items, orders, traffic_blocks, stuck streaks), identify the dominant failure mode, patch only that path, and rerun the same 5-game batch to compare mean/median score.
```
